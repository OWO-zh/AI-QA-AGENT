"""
agent.py — LangGraph 多工具协同 Agent 核心
==========================================
基于 LangGraph 构建三节点 Agent，通过 Function Calling 自主调度三类工具。

架构：
    decide ──→ tools ──→ answer
      ↑          │          │
      └──(SQL错误重试)──────┘

节点说明：
    decide_node:       分析用户意图，决策调用哪些工具（或直接回答）
    tool_execute_node: 并发执行工具调用（search_web / query_database / search_knowledge_base）
    answer_node:       整合多源信息，生成带溯源的最终回答

容错机制：
    - 配置双轨降级：Streamlit Secrets → config.yaml
    - SQL 执行四级容错：安全校验 → 自动重试 → LLM异常兜底 → 全局兜底回答
    - 搜索自动扩展：结果不足时自动加宽检索词重试
    - LLM 调用保护：decide/answer 节点异常时返回友好兜底，不暴露内部错误

安全策略：
    - SQL 白名单：仅允许 SELECT，限定表名，禁用 DROP/DELETE 等危险关键字
    - 文件校验：路径穿越防护、类型白名单、大小限制
"""

import json
import os
import re
import sqlite3
import logging
import time

import yaml
import streamlit as st
from typing import TypedDict, Literal, Annotated
from langgraph.graph import StateGraph, END
from tavily import TavilyClient
from openai import OpenAI

# ==================== 配置加载（本地优先，云端自动降级） ====================
config = {}
is_cloud = False  # 是否运行在 Streamlit Cloud（用于环境相关配置的自动切换）

# 优先尝试从环境变量或 Streamlit Secrets 读取
try:
    # 如果在 Streamlit Cloud 环境，从 secrets 读取
    config["aliyun_api_key"] = st.secrets["aliyun_api_key"]
    config["aliyun_base_url"] = st.secrets["aliyun_base_url"]
    config["tavily_api_key"] = st.secrets["tavily_api_key"]
    config["llm_model"] = st.secrets.get("llm_model", "qwen-plus")
    config["reranker_model"] = st.secrets.get("reranker_model", "BAAI/bge-reranker-base")
    config["max_retries"] = int(st.secrets.get("max_retries", "2"))
    is_cloud = True  # 全部 secrets 读取成功才判定为云端
except Exception:
    # 本地开发时从 config.yaml 读取
    is_cloud = False
    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            yaml_config = yaml.safe_load(f)
        config.update(yaml_config)
    except FileNotFoundError:
        raise RuntimeError("未找到 config.yaml 或 Streamlit Secrets，请配置其中一种")

# ==================== HuggingFace 下载配置（须在导入 rag_utils 之前设置）====================
# hf_transfer 存在时才启用加速，避免依赖缺失导致下载崩溃
try:
    import hf_transfer  # noqa: F401
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
except ImportError:
    pass
os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "300"  # 大模型下载超时设为5分钟

if is_cloud:
    # 云端：使用默认缓存目录（/home/adminuser/.cache，保证可写），
    # 直连 HuggingFace（美国服务器速度最快），不设置 HF_HOME
    pass
else:
    # 本地：启用国内镜像 + 项目内缓存目录（避免占用C盘）
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    _CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hf_cache")
    os.environ["HF_HOME"] = _CACHE_DIR
    os.environ["TRANSFORMERS_CACHE"] = os.path.join(_CACHE_DIR, "transformers")

from rag_utils import RAGManager

openai_client = OpenAI(api_key=config["aliyun_api_key"], base_url=config["aliyun_base_url"])
tavily_client = TavilyClient(api_key=config["tavily_api_key"])

ALLOWED_SQL_TABLES = ["employees", "departments", "salary"]
FORBIDDEN_SQL_KEYWORDS = ["drop", "delete", "update", "insert", "alter", "create", "truncate"]
MAX_RETRY_TIMES = int(config.get("max_retries", 2))

# ==================== 日志配置 ====================
logger = logging.getLogger("Agent")
logger.setLevel(logging.INFO)
# 避免重复添加 handler
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger.addHandler(console_handler)
    file_handler = logging.FileHandler("agent_run.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(file_handler)

# ==================== 消息辅助函数 ====================
def concat_messages(existing: list, new: list) -> list:
    """LangGraph 自定义 reducer：将新旧消息列表拼接。

    不使用默认的消息叠加行为，而是直接拼接 dict 列表。
    这样保持消息格式统一（全部为 dict），避免 LangGraph 内部的 Message 对象转换。

    参数:
        existing: 已有消息列表（可能为空）
        new:      本轮新增消息列表

    返回:
        拼接后的完整消息列表
    """
    return existing + new

# ==================== 状态定义 ====================
class AgentState(TypedDict):
    """Agent 运行时状态字典。

    字段说明:
        messages:           对话历史，使用 concat_messages reducer 累加
        final_answer:       最终生成的回答文本
        retry_count:        SQL 错误重试计数（上限由 MAX_RETRY_TIMES 控制）
        tool_result_status: 工具执行状态（"success" / "partial"）
        has_sql_error:      是否存在 SQL 执行错误
        error_message:      最近一次错误信息（用于重试时传给 LLM 修正）
    """
    messages: Annotated[list, concat_messages]
    final_answer: str
    retry_count: int
    tool_result_status: str
    has_sql_error: bool
    error_message: str

# ==================== 工具函数 ====================
def validate_sql_safety(sql: str) -> tuple:
    """SQL 三层安全检查。

    1. 语句类型：仅允许 SELECT 开头
    2. 关键字黑名单：禁止 DROP / DELETE / UPDATE / INSERT / ALTER / CREATE / TRUNCATE
    3. 表名白名单：仅允许访问 employees / departments / salary

    参数:
        sql: 待执行的 SQL 语句

    返回:
        (是否通过, 原因说明) 元组
    """
    sql_lower = sql.lower().strip()
    if not sql_lower.startswith("select"):
        return False, "仅允许 SELECT 查询"
    for kw in FORBIDDEN_SQL_KEYWORDS:
        if kw in sql_lower:
            return False, f"禁止关键字: {kw}"
    match = re.search(r"from\s+(\w+)", sql_lower)
    if match and match.group(1) not in ALLOWED_SQL_TABLES:
        return False, f"无权访问表: {match.group(1)}"
    return True, "校验通过"

def search_web(query: str, retry: bool = False) -> str:
    """联网搜索，含自动扩展重试。

    使用 Tavily API 进行互联网搜索，结果不足时自动用更宽泛的关键词重试一次。
    重试逻辑使用循环而非递归，避免栈溢出风险。

    参数:
        query: 搜索关键词，建议包含时效词（如"2026年"）
        retry: 是否为二次重试（内部参数，外部调用无需关注）

    返回:
        格式化后的搜索结果文本，或错误提示
    """
    logger.info(f"[搜索] 查询: {query} | 重试: {retry}")
    current_query = query
    is_retry = retry

    while True:
        start = time.time()
        try:
            resp = tavily_client.search(current_query, max_results=5, search_depth="advanced", time_range="month")
            results = resp.get("results", [])
            cost = round(time.time() - start, 2)

            if len(results) < 2 and not is_retry:
                current_query = " ".join(current_query.split()[:3])
                is_retry = True
                logger.info("[搜索] 结果不足，尝试宽泛查询")
                continue

            if not results:
                return "未检索到相关信息，请尝试更换关键词。"

            logger.info(f"[搜索] 返回 {len(results)} 条，耗时 {cost}s")
            formatted = []
            for i, item in enumerate(results, 1):
                formatted.append(f"[{i}] 标题：{item.get('title')}\n    内容：{item.get('content')}\n    来源：{item.get('url')}")
            return "\n\n".join(formatted)
        except Exception as e:
            logger.error(f"[搜索] 异常: {str(e)}")
            return f"搜索服务异常: {str(e)}"

def query_database(query_str: str) -> str:
    """执行 SQL 查询（带安全校验与异常保护）。

    执行流程：
        1. validate_sql_safety 安全校验
        2. 连接 company.db 并执行查询
        3. 返回格式化结果或错误信息
        4. finally 确保连接关闭

    参数:
        query_str: SQL SELECT 语句

    返回:
        查询结果字符串，含 "查询成功，结果：" 或 "SQL执行错误:" 前缀
    """
    is_safe, msg = validate_sql_safety(query_str)
    if not is_safe:
        logger.warning(f"[SQL] 校验失败: {msg}")
        return f"SQL执行被拦截：{msg}"

    logger.info(f"[SQL] 执行: {query_str}")
    start = time.time()
    conn = None
    try:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'company.db')
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(query_str)
        rows = cur.fetchall()
        cost = round(time.time() - start, 3)
        if not rows:
            logger.info(f"[SQL] 结果为空，耗时 {cost}s")
            return "查询结果为空"
        logger.info(f"[SQL] 返回 {len(rows)} 行，耗时 {cost}s")
        return f"查询成功，结果：\n{str(rows)}"
    except Exception as e:
        logger.error(f"[SQL] 错误: {str(e)}")
        return f"SQL执行错误: {str(e)}"
    finally:
        if conn:
            conn.close()

# RAG 工具（通过全局注入，演示环境可接受）
_current_rag: RAGManager = None

def set_rag_manager(rag: RAGManager):
    """注入知识库管理器实例。

    Agent 通过全局变量 _current_rag 访问知识库。
    该函数在 app.py 会话初始化时调用，确保每个会话有独立的知识库引用。

    参数:
        rag: 已初始化的 RAGManager 实例，或 None（禁用知识库功能）
    """
    global _current_rag
    _current_rag = rag

def search_knowledge_base(query: str) -> str:
    """检索本地知识库。

    通过全局注入的 RAGManager 实例执行混合检索。
    若知识库未初始化（用户未上传文档），返回提示信息。

    参数:
        query: 检索查询文本，直接使用用户原始提问

    返回:
        格式化后的检索结果，含来源标注和文本内容
    """
    logger.info(f"[知识库] 查询: {query}")
    if not _current_rag:
        return "知识库未启用，请先上传文档。"
    try:
        return _current_rag.search(query)
    except Exception as e:
        logger.error(f"[知识库] 异常: {str(e)}")
        return f"知识库检索异常: {str(e)}"

# 工具描述
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "搜索互联网实时信息。需要新闻、政策、行业动态时使用。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "搜索关键词，可加时间"}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_database",
            "description": "查询公司员工数据库，仅支持 SELECT。涉及员工信息、薪资、部门时使用。",
            "parameters": {
                "type": "object",
                "properties": {"query_str": {"type": "string", "description": "SQL SELECT 语句"}},
                "required": ["query_str"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "检索已上传的私有文档。只要用户提问涉及文档、PDF、内部资料，直接使用用户原始提问检索，不要拒绝。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "检索关键词,直接使用用户原话"}},
                "required": ["query"]
            }
        }
    }
]

# ==================== 节点定义 ====================
def decide_node(state: AgentState):
    """决策节点：分析用户意图，判断调用哪些工具或直接回答。

    根据用户问题内容和系统提示词，LLM 自主决策：
        - 调用单个或多个工具（search_web / query_database / search_knowledge_base）
        - 或直接基于常识回答

    LLM 调用异常时采用方案A（静默兜底）：返回友好提示引导用户重试，
    完整错误信息写入日志供排查。

    参数:
        state: 当前 AgentState，包含 messages 和可能的 SQL 错误上下文

    返回:
        包含 assistant 消息的 state 更新，消息中可能包含 tool_calls
    """
    logger.info(">>> 决策节点")
    start = time.time()
    messages = state["messages"]

    system_content = (
        "【全局最高强制规则，不可违背】\n"
        "1. 当前真实年份为2026年，所有联网搜索返回的2026年实时数据、政策、新闻具备最高优先级，**绝对不能以模型内置旧知识库否定外部搜索结果，不许说2026年尚未到来**。\n"
        "2. 若用户查询上市公司公开股价、财报、行业动态、市场客观资讯，正常调用search_web检索公开事实，仅陈述客观数据，不做投资涨跌预测、理财指导、风险评估，规避合规限制。\n"
        "3. 若用户提到文档、PDF、文件、上传的内容，必须立即调用 search_knowledge_base 工具，禁止拒绝或询问文件名。\n\n"
        "你是企业智能助手。根据问题选择工具：\n"
        "1. 员工信息/薪资/部门 → query_database\n"
        "2. 外部新闻/政策/行业/上市公司公开资讯 → search_web\n"
        "3. 内部文档/制度 → search_knowledge_base\n"
        "4. 常识直接回答\n"
        "5. 多源问题可同时调用多个工具。搜索时自动带上2026年时间关键词，保证时效性。\n"
        "员工表 employees：name, department, salary, hire_date"
    )
    if state.get("has_sql_error") and state.get("error_message"):
        system_content += f"\n\n【注意】上次 SQL 错误：{state['error_message']}\n请修正后重试。"

    system_msg = {"role": "system", "content": system_content}
    # 更新 system 消息
    has_system = any(m.get("role") == "system" for m in messages)
    if has_system:
        messages = [system_msg] + [m for m in messages if m.get("role") != "system"]
    else:
        messages = [system_msg] + messages

    try:
        resp = openai_client.chat.completions.create(
            model=config.get("llm_model", "qwen-plus"), messages=messages, tools=TOOLS, tool_choice="auto"
        )
    except Exception as e:
        logger.error(f"决策节点 LLM 调用异常: {str(e)}")
        # 方案A：静默兜底，返回直接回答的引导消息
        fallback = {
            "role": "assistant",
            "content": "抱歉，系统暂时无法分析您的问题，请稍后重试。"
        }
        logger.info(f"<<< 决策节点 异常兜底 耗时 {time.time() - start:.2f}s")
        return {"messages": [fallback]}

    msg = resp.choices[0].message

    if msg.tool_calls:
        logger.info(f"决策: 调用 {[tc.function.name for tc in msg.tool_calls]}")
    else:
        logger.info("决策: 直接回答")

    # 构建标准 dict 消息
    new_msg = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        new_msg["tool_calls"] = [
            {
                "id": tc.id, "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments}
            } for tc in msg.tool_calls
        ]

    logger.info(f"<<< 决策节点 耗时 {time.time() - start:.2f}s")
    return {"messages": [new_msg]}

def tool_execute_node(state: AgentState):
    """工具执行节点：依次执行 LLM 请求的工具调用。

    对每个 tool_call 解析参数并分发给对应的工具函数。
    执行过程中捕获各类异常（参数解析失败、工具执行异常），
    以 partial 状态继续流程，确保单工具失败不阻断整体回答。

    参数:
        state: 当前 AgentState，消息列表最后一条应包含 tool_calls

    返回:
        包含 tool 消息列表和状态标记的 state 更新
    """
    logger.info(">>> 工具执行节点")
    start = time.time()
    last_msg = state["messages"][-1]
    tool_calls = last_msg.get("tool_calls", [])

    results = []
    all_ok = True
    sql_err = False
    err_msg = ""
    retry = state.get("retry_count", 0)

    try:
        for tc in tool_calls:
            func_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                results.append({"role": "tool", "tool_call_id": tc["id"], "name": func_name,
                            "content": "参数解析失败"})
                all_ok = False
                continue

            if func_name == "search_web":
                content = search_web(args.get("query", ""))
            elif func_name == "query_database":
                content = query_database(args.get("query_str", ""))
                logger.info(f"[SQL] 返回结果长度: {len(content)}")
                if "SQL执行错误" in content or "SQL执行被拦截" in content:
                    sql_err = True
                    err_msg = content
                    all_ok = False
            elif func_name == "search_knowledge_base":
                content = search_knowledge_base(args.get("query", ""))
            else:
                content = f"未知工具: {func_name}"
                all_ok = False

            # 工具消息附带 name 字段，方便前端展示
            results.append({"role": "tool", "tool_call_id": tc["id"], "name": func_name, "content": content})

    except Exception as e:
        logger.error(f"工具执行节点整体异常: {str(e)}")
        results.append({
            "role": "tool",
            "tool_call_id": "error",
            "name": "unknown",
            "content": f"工具执行异常: {str(e)}"
            })
        all_ok = False

    status = "success" if all_ok else "partial"
    logger.info(f"<<< 工具执行 {status} 耗时 {time.time() - start:.2f}s")
    return {
        "messages": results,
        "tool_result_status": status,
        "retry_count": retry + 1 if sql_err else retry,
        "has_sql_error": sql_err,
        "error_message": err_msg
    }

def answer_node(state: AgentState):
    """答案生成节点：整合多源信息，生成带溯源的最终回答。

    将所有工具返回的结果和对话历史整合，由 LLM 生成面向用户的自然语言回答。
    要求标注信息来源，并对多份文档分别总结。

    LLM 调用异常时采用方案A（静默兜底）：返回通用错误提示，
    完整错误信息写入日志供排查。

    参数:
        state: 当前 AgentState，messages 中包含工具返回结果

    返回:
        包含 final_answer 和 assistant 消息的 state 更新
    """
    logger.info(">>> 答案生成")
    start = time.time()
    messages = state["messages"]
    sys_msg = {
        "role": "system",
        "content": (
            "【最高优先级兜底规则】\n"
            "1. 严格以工具（联网搜索/数据库/知识库）返回的内容为准，工具拿到的2026年实时信息为真实有效数据，不得质疑年份、不得否定搜索结果。\n"
            "2. 股票、上市公司类问题只客观转述搜索到的公开行情、新闻、财报内容，不做任何投资建议与风险分析。\n\n"

            "【输出格式硬性要求，必须严格遵守】\n"
            "请基于工具返回的信息生成最终回答，遵循以下原则：\n"
            "1. 结论先行：先用一句话直接回答用户的核心问题\n"
            "2. 分点展开：必要时列出关键细节，每条标注信息来源（如“据内部数据库”、“搜索结果显示”、“文档中提到”）\n"
            "3. 涉及多份文档时，逐一说明每份文档的核心内容，不可遗漏任何一份\n"
            "4. 信息不足或矛盾时诚实说明，严禁编造\n"
            "5. 语言专业简洁，字数控制在 300 字以内\n\n"

            "【核心规则】你现在处于最终答案生成阶段，禁止输出任何工具调用（tool_calls），直接给出自然语言回答。"
        )
    }
    # 组合消息
    all_msgs = [sys_msg] + messages

    try:
        resp = openai_client.chat.completions.create(model=config.get("llm_model", "qwen-plus"), messages=all_msgs)
        answer = resp.choices[0].message.content
    except Exception as e:
        logger.error(f"答案生成节点 LLM 调用异常: {str(e)}")
        answer = "抱歉，系统暂时无法整合信息，请稍后重试或者换一种问法。"
        logger.info(f"<<< 答案生成 异常兜底 耗时 {time.time() - start:.2f}s")

        # 异常分支也要清空上一轮工具日志，防止残留（非 Streamlit 静默跳过）
        try:
            st.session_state["last_tools"] = []
        except Exception:
            pass
        return {
            "final_answer": answer,
            "messages": [{"role": "assistant", "content": answer}]
        }

    # 如果答案为空，补上提示
    if not answer or answer.strip() == "":
        answer = "抱歉，系统暂时无法整合信息，请稍后重试或者换一种问法。"

    # 如果答案看起来像工具调用，则强制替换
    if answer.strip().startswith('{') and '"name"' in answer and '"arguments"' in answer:
        answer = "系统处理复杂查询时出现了内部错误，已自动重定向，请稍后重试或简化提问。"

    # ========== 收集本轮工具执行记录（只取当前轮次）==========
    tool_records = []
    for msg_item in reversed(state["messages"]):
        if msg_item.get("role") == "tool":
            tool_name = msg_item.get("name", "unknown_tool")
            tool_content = msg_item.get("content", "")
            tool_records.append((tool_name, tool_content))
        elif msg_item.get("role") in ("user", "assistant"):
            break  # 只收集本轮，遇到用户/助手消息即停止
    tool_records.reverse()  # 恢复时间顺序

    # 存入会话状态，前端直接读取（非 Streamlit 环境静默跳过）
    try:
        st.session_state["last_tools"] = tool_records
    except Exception:
        pass  # 命令行测试入口无 st.session_state，忽略
    # =====================================================

    logger.info(f"<<< 答案生成 耗时 {time.time() - start:.2f}s")
    return {
        "final_answer": answer,
        "messages": [{"role": "assistant", "content": answer}]
    }

# ==================== 路由 ====================
def route_after_decide(state: AgentState) -> Literal["tools", "answer"]:
    """决策后的条件路由。

    判断逻辑：
        - 决策节点输出了 tool_calls → 进入工具执行节点
        - 决策节点直接回答 → 跳过工具，进入答案生成节点

    参数:
        state: 当前 Agent 状态

    返回:
        "tools" 或 "answer"
    """
    last = state["messages"][-1]
    return "tools" if last.get("tool_calls") else "answer"

def route_after_tools(state: AgentState) -> Literal["decide", "answer"]:
    """工具执行后的条件路由（含 SQL 重试逻辑）。

    判断逻辑：
        - 存在 SQL 错误 且 重试次数 < MAX_RETRY_TIMES → 回到决策节点修正 SQL
        - 其他情况 → 进入答案生成节点

    这是四级容错中的第二级"自动重试"——将错误信息反馈给 LLM，让其修正 SQL 语句。

    参数:
        state: 当前 Agent 状态

    返回:
        "decide" 或 "answer"
    """
    if state.get("has_sql_error") and state["retry_count"] < MAX_RETRY_TIMES:
        logger.info(f"SQL 错误，重试 {state['retry_count']}/{MAX_RETRY_TIMES}")
        return "decide"
    return "answer"

# ==================== 构建图 ====================
workflow = StateGraph(AgentState)
workflow.add_node("decide", decide_node)
workflow.add_node("tools", tool_execute_node)
workflow.add_node("answer", answer_node)

workflow.set_entry_point("decide")
workflow.add_conditional_edges("decide", route_after_decide, {"tools": "tools", "answer": "answer"})
workflow.add_conditional_edges("tools", route_after_tools, {"decide": "decide", "answer": "answer"})
workflow.add_edge("answer", END)

agent = workflow.compile()

# ==================== 测试入口 ====================
if __name__ == "__main__":
    """命令行快速测试入口。

    直接运行 python agent.py 可在终端进行单轮对话测试。
    前提：config.yaml 存在且 company.db 已初始化。
    """
    query = "研发部最高工资的员工是谁？另外请搜索2026年关于AI应用的最新政策或新闻？"
    print("=" * 50)
    print(f"用户: {query}")
    result = agent.invoke({
        "messages": [{"role": "user", "content": query}],
        "final_answer": "", "retry_count": 0,
        "tool_result_status": "", "has_sql_error": False, "error_message": ""
    })
    print(f"助手: {result['final_answer']}")
