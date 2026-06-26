import json
import yaml
import sqlite3
import re
import logging
import time
from typing import TypedDict, Literal, Annotated
from langgraph.graph import StateGraph, END
from tavily import TavilyClient
from openai import OpenAI
from rag_utils import RAGManager

# ==================== 配置 ====================
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

openai_client = OpenAI(api_key=config["aliyun_api_key"], base_url=config["aliyun_base_url"])
tavily_client = TavilyClient(api_key=config["tavily_api_key"])

ALLOWED_SQL_TABLES = ["employees", "departments", "salary"]
FORBIDDEN_SQL_KEYWORDS = ["drop", "delete", "update", "insert", "alter", "create", "truncate"]
MAX_RETRY_TIMES = 2

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
    """自定义 reducer：纯列表拼接，不转换消息格式"""
    return existing + new

# ==================== 状态定义 ====================
class AgentState(TypedDict):
    messages: Annotated[list, concat_messages]  # 全部使用 dict
    final_answer: str
    retry_count: int
    tool_result_status: str
    has_sql_error: bool
    error_message: str

# ==================== 工具函数 ====================
def validate_sql_safety(sql: str) -> tuple:
    """SQL 安全检查：仅允许 SELECT，禁用危险关键字，限制表名"""
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
    """联网搜索，含自动扩展重试"""
    logger.info(f"[搜索] 查询: {query} | 重试: {retry}")
    start = time.time()
    try:
        resp = tavily_client.search(query, max_results=5, search_depth="advanced", time_range="month")
        results = resp.get("results", [])
        cost = round(time.time() - start, 2)

        if len(results) < 2 and not retry:
            simple = " ".join(query.split()[:3])
            logger.info("[搜索] 结果不足，尝试宽泛查询")
            return search_web(simple, retry=True)

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
    """执行 SQL 查询（带安全校验）"""
    is_safe, msg = validate_sql_safety(query_str)
    if not is_safe:
        logger.warning(f"[SQL] 校验失败: {msg}")
        return f"SQL执行被拦截：{msg}"

    logger.info(f"[SQL] 执行: {query_str}")
    start = time.time()
    conn = None
    try:
        conn = sqlite3.connect('company.db')
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
    global _current_rag
    _current_rag = rag

def search_knowledge_base(query: str) -> str:
    """检索本地知识库"""
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
    """决策节点：判断调用哪些工具或直接回答"""
    logger.info(">>> 决策节点")
    start = time.time()
    messages = state["messages"]

    system_content = (
        "【强制规则】若用户提到文档、PDF、文件、上传的内容，必须立即调用 search_knowledge_base 工具，禁止拒绝或询问文件名。\n\n"
        "你是企业智能助手。根据问题选择工具：\n"
        "1. 员工信息/薪资/部门 → query_database\n"
        "2. 外部新闻/政策 → search_web\n"
        "3. 内部文档/制度 → search_knowledge_base\n"
        "4. 常识直接回答\n"
        "5. 多源问题可同时调用多个工具。搜索时请加'2026年'等时效词。\n"
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

    resp = openai_client.chat.completions.create(
        model="qwen-plus", messages=messages, tools=TOOLS, tool_choice="auto"
    )
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
    """工具执行节点：依次调用工具，返回工具消息（包含工具名称）"""
    logger.info(">>> 工具执行节点")
    start = time.time()
    last_msg = state["messages"][-1]
    tool_calls = last_msg.get("tool_calls", [])  # 统一为 dict 列表

    results = []
    all_ok = True
    sql_err = False
    err_msg = ""
    retry = state.get("retry_count", 0)

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
    """答案生成节点：整合多源信息，给出带溯源的最终回答"""
    logger.info(">>> 答案生成")
    start = time.time()
    messages = state["messages"]
    sys_msg = {
        "role": "system",
        "content": (
            "请基于工具返回的信息生成最终回答：\n"
            "1. 整合数据库、搜索、知识库结果\n"
            "2. 标注信息来源（如“来自内部数据库”）\n"
            "3. 信息不足时明确说明，不编造\n"
            "4. 语言简洁专业"
        )
    }
    # 组合消息
    all_msgs = [sys_msg] + messages
    resp = openai_client.chat.completions.create(model="qwen-plus", messages=all_msgs)
    answer = resp.choices[0].message.content
    logger.info(f"<<< 答案生成 耗时 {time.time() - start:.2f}s")
    return {
        "final_answer": answer,
        "messages": [{"role": "assistant", "content": answer}]
    }

# ==================== 路由 ====================
def route_after_decide(state: AgentState) -> Literal["tools", "answer"]:
    """决策后的路由：有工具调用则执行工具，否则直接回答"""
    last = state["messages"][-1]
    return "tools" if last.get("tool_calls") else "answer"

def route_after_tools(state: AgentState) -> Literal["decide", "answer"]:
    """工具执行后的路由：SQL 错误且未达上限则重试决策，否则生成答案"""
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
    query = "研发部最高工资的员工是谁？另外请搜索2026年关于AI应用的最新政策或新闻？"
    print("=" * 50)
    print(f"用户: {query}")
    result = agent.invoke({
        "messages": [{"role": "user", "content": query}],
        "final_answer": "", "retry_count": 0,
        "tool_result_status": "", "has_sql_error": False, "error_message": ""
    })
    print(f"助手: {result['final_answer']}")