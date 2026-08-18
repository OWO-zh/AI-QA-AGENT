"""
app.py — Streamlit 可视化界面
=============================
企业智能信息助手的 Web 入口，基于 Streamlit 构建聊天界面。

功能：
    - 首页欢迎引导：功能说明 + 一键测试按钮，面试官无需摸索
    - 预设问题：20 条测试用例按分类编排，点击即可体验
    - 侧边栏：文件上传、知识库构建、能力展示、对话清空
    - 主区域：聊天消息流，支持工具调用详情展开
    - 会话管理：基于 st.session_state 的多轮对话状态保持

架构：
    app.py (UI 层) → agent.py (Agent 逻辑) → rag_utils.py (知识库检索)
"""

import os
import sys
import time
import uuid

import streamlit as st

# 确保项目根目录在导入路径中
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent import agent, set_rag_manager, logger, config, is_cloud
from rag_utils import RAGManager

# ---------- 页面配置 ----------
st.set_page_config(
    page_title="企业智能信息助手 | Agent演示",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': "企业级多工具协同Agent · 内部系统"
    }
)

# ---------- 科技蓝简约主题 CSS ----------
st.markdown("""
<style>
    * {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
    }
    html, body, [class*="css"] {
        color: #1e293b;
        background-color: #ffffff;
    }
    .main .block-container {
        padding: 2rem 3rem 1rem 3rem;
        max-width: 1200px;
    }
    h1 {
        font-weight: 600;
        font-size: 2rem;
        color: #0f172a;
        margin-bottom: 0.25rem;
    }
    .caption {
        color: #64748b;
        font-size: 0.9rem;
    }
    [data-testid="stSidebar"] {
        background-color: #f8fafc;
        border-right: 1px solid #e2e8f0;
    }
    [data-testid="stSidebar"] .block-container {
        padding: 1.5rem 1rem;
    }
    [data-testid="stSidebar"] hr {
        margin: 1.2rem 0;
        border-color: #e2e8f0;
    }
    .stButton > button {
        border-radius: 8px;
        border: 1px solid #cbd5e1;
        background-color: white;
        color: #334155;
        font-weight: 500;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        border-color: #3b82f6;
        background-color: #eff6ff;
        color: #1e40af;
        box-shadow: 0 1px 3px rgba(59,130,246,0.1);
    }
    .stButton > button:active {
        transform: scale(0.98);
    }
    [data-testid="stFileUploader"] section {
        border: 2px dashed #cbd5e1;
        border-radius: 12px;
        background-color: #f9fafb;
        transition: border-color 0.2s;
    }
    [data-testid="stFileUploader"]:hover section {
        border-color: #3b82f6;
    }
    [data-testid="stChatMessage"] {
        border-radius: 14px;
        padding: 0.8rem 1.2rem;
        margin-bottom: 0.8rem;
        background-color: #ffffff;
        border: 1px solid #f1f5f9;
        transition: box-shadow 0.2s;
    }
    [data-testid="stChatMessage"]:hover {
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    [data-testid="stChatMessage"] [data-testid="chatAvatarIcon-user"] ~ div {
        background-color: #eff6ff;
    }
    [data-testid="stChatInput"] textarea {
        border-radius: 16px !important;
        border: 1px solid #e2e8f0 !important;
        background-color: #ffffff;
        transition: border-color 0.25s, box-shadow 0.25s;
    }
    [data-testid="stChatInput"] textarea:focus {
        border-color: #3b82f6 !important;
        box-shadow: 0 0 0 3px rgba(59,130,246,0.15) !important;
    }
    [data-testid="stExpander"] {
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        background-color: #f8fafc;
        overflow: hidden;
        transition: all 0.2s;
    }
    [data-testid="stExpander"]:hover {
        border-color: #cbd5e1;
    }
    .stCodeBlock {
        border-radius: 8px;
        background-color: #f1f5f9 !important;
    }
    .stSuccess, .stWarning, .stError {
        border-radius: 10px;
    }
    hr {
        border-color: #f1f5f9;
        margin: 1.5rem 0;
    }
    /* 预设问题按钮 */
    .preset-btn button {
        font-size: 0.85rem !important;
        padding: 0.3rem 0.8rem !important;
        border-radius: 20px !important;
        border: 1px solid #e2e8f0 !important;
        background: #f8fafc !important;
        text-align: left !important;
        width: 100% !important;
        white-space: normal !important;
        min-height: unset !important;
    }
    .preset-btn button:hover {
        border-color: #3b82f6 !important;
        background: #eff6ff !important;
    }
    /* 欢迎区域 */
    .welcome-card {
        background: linear-gradient(135deg, #eff6ff 0%, #f0f9ff 100%);
        border: 1px solid #bfdbfe;
        border-radius: 16px;
        padding: 2rem;
        margin-bottom: 1.5rem;
    }
    .feature-pill {
        display: inline-block;
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 24px;
        padding: 0.5rem 1.2rem;
        margin: 0.25rem;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)


# ===== 20条预设测试用例 =====
PRESET_QUESTIONS = {
    "📚 知识库检索（5条）": [
        "上传的 PDF 里讲了什么？",
        "PDF 中提到的“XX 计划”具体包括哪些？",
        "PDF 里有没有提到火星殖民计划？",
        "两份文档都涉及什么主题？",
        "那个文档里关于安全的部分怎么说？",
    ],
    "🏢 数据库查询（5条）": [
        "张三的工资是多少？",
        "研发部平均工资是多少？",
        "公司有叫'特朗普'的员工吗？",
        "谁在 2025 年入职？",
        "工资最高的三个人是谁？",
    ],
    "🌐 联网搜索（5条）": [
        "2026 年人工智能有哪些新政策？",
        "英伟达今天的股价是多少？",
        "最近科技圈发生了什么大事？",
        "搜一下：量子纠缠最新突破",
        "2026 年太空探索最新进展",
    ],
    "🔄 多工具混合（5条）": [
        "研发部工资最高的是谁？再对比一下行业平均薪资",
        "根据 PDF 里的战略，结合最新行业新闻，我们的方向对吗？",
        "PDF 中提到的技术规范，公司里哪些人负责相关领域？",
        "查一下公司研发部的平均工资，同时搜一下 2026 年 AI 工程师的薪酬报告，再参考内部制度里关于调薪的规定",
        "网上说 AI 会取代很多岗位，我们 PDF 里的人力规划有对策吗？",
    ],
}

# ===== 欢迎引导文案 =====
WELCOME_HTML = """
<div class="welcome-card">
<h2 style="margin-top:0;">👋 欢迎体验企业智能信息助手</h2>
<p style="color:#64748b;font-size:1.05rem;">
基于 <b>LangGraph + RAG + Function Calling</b> 构建的多工具协同 Agent。
上传 PDF 文档后，您可以向它提问关于文档内容、公司数据、外部资讯的任何问题——
Agent 会<b>自动识别意图、自主调度工具、整合多源信息</b>给出带溯源的精准回答。
</p>
<div style="margin-top:1rem;">
<span class="feature-pill">📚 私有知识库问答</span>
<span class="feature-pill">🏢 SQL 数据库查询</span>
<span class="feature-pill">🌐 联网实时搜索</span>
<span class="feature-pill">🔄 多工具协同调度</span>
<span class="feature-pill">🛡️ SQL 安全校验</span>
<span class="feature-pill">🔁 四级容错降级</span>
</div>
</div>
"""


# ===== 云端演示防护配置（仅 is_cloud 时生效，本地开发不受限制）=====
MAX_QUESTIONS = 25   # 每个会话最多提问次数（覆盖 20 条用例 + 5 次余量）
MIN_INTERVAL = 8     # 两次提问最小间隔（秒），防脚本刷量

# ---------- 模型缓存（Streamlit Cloud 休眠重启不重复下载）----------
@st.cache_resource(show_spinner="正在加载 AI 模型（首次需下载 Embedding + Reranker，约 1.1GB，请耐心等待）...")
def create_rag_manager(reranker_model: str):
    """缓存 RAGManager 实例。

    @st.cache_resource 确保模型在 Streamlit Server 级别只加载一次：
      - 同一用户多次 rerun → 命中缓存，秒级响应
      - 多用户并发访问 → 共享同一份模型内存
      - 云端休眠唤醒后 → 首次访问重新加载，后续命中缓存

    参数:
        reranker_model: 重排序模型名，作为缓存 key 的一部分
    """
    return RAGManager(reranker_model=reranker_model)


# ---------- 会话初始化 ----------
def init_session():
    """初始化 Streamlit 会话状态。"""
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "messages" not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant",
            "content": "你好！我是企业智能信息助手，支持内部数据库查询、联网搜索、私有知识库问答。\n\n💡 **快速体验**：在左侧边栏点击任意预设问题，即可一键测试。"
        }]
    if "rag_manager" not in st.session_state:
        st.session_state.rag_manager = create_rag_manager(
            reranker_model=config.get("reranker_model", "BAAI/bge-reranker-base")
        )
    if "agent_state" not in st.session_state:
        st.session_state.agent_state = {
            "messages": [],
            "final_answer": "",
            "retry_count": 0,
            "tool_result_status": "",
            "has_sql_error": False,
            "error_message": ""
        }
    if "pending_question" not in st.session_state:
        st.session_state.pending_question = None
    if "authed" not in st.session_state:
        st.session_state.authed = False
    if "question_count" not in st.session_state:
        st.session_state.question_count = 0
    if "last_question_time" not in st.session_state:
        st.session_state.last_question_time = 0.0


init_session()
set_rag_manager(st.session_state.rag_manager)

# ---------- 云端访问保护：密码门（仅云端生效，本地开发直接跳过）----------
if is_cloud:
    demo_pwd = config.get("demo_password", "")
    if not st.session_state.authed:
        if not demo_pwd:
            st.error("演示密码未配置，请联系管理员。")
            st.stop()
        st.markdown("# 🤖 企业智能信息助手")
        st.markdown("本演示为邀请制访问，请输入访问密码后进入。")
        with st.form("auth_form"):
            pwd_input = st.text_input("访问密码", type="password")
            submitted = st.form_submit_button("进入演示")
        if submitted:
            if pwd_input == demo_pwd:
                st.session_state.authed = True
                st.rerun()
            else:
                st.error("密码错误，请重试")
        st.stop()  # 未通过验证前，不渲染页面其余部分


# ===== 云端防护：提问额度检查（本地开发始终放行）=====
def try_consume_quota() -> bool:
    """检查并消耗一次提问额度。

    云端（is_cloud）执行两道限制：
        1. 间隔限制：两次提问至少间隔 MIN_INTERVAL 秒，防脚本连发
        2. 次数限制：每个会话最多 MAX_QUESTIONS 次提问

    返回:
        True 表示允许提问（并已消耗额度），False 表示被拦截
    """
    if not is_cloud:
        return True
    now = time.time()
    if now - st.session_state.last_question_time < MIN_INTERVAL:
        wait = int(MIN_INTERVAL - (now - st.session_state.last_question_time)) + 1
        st.warning(f"提问过于频繁，请等待 {wait} 秒后再试。")
        return False
    if st.session_state.question_count >= MAX_QUESTIONS:
        st.warning(f"演示提问次数已达上限（{MAX_QUESTIONS} 次），感谢体验！")
        return False
    st.session_state.question_count += 1
    st.session_state.last_question_time = now
    return True


# ===== 处理预设问题的函数 =====
def process_message(prompt: str):
    """处理用户消息（来自预设按钮或聊天输入），调用 Agent 并更新状态。"""
    st.session_state.messages.append({"role": "user", "content": prompt})

    st.session_state.agent_state.update({
        "retry_count": 0, "has_sql_error": False,
        "error_message": "", "tool_result_status": ""
    })
    st.session_state.agent_state["messages"].append({"role": "user", "content": prompt})

    with st.spinner("分析中..."):
        try:
            new_state = agent.invoke(st.session_state.agent_state)
            st.session_state.agent_state = new_state
            answer = new_state["final_answer"]

            st.session_state.messages.append({"role": "assistant", "content": answer})
            logger.info(f"会话 {st.session_state.session_id} 完成一轮对话")
        except Exception as e:
            logger.error(f"Agent 调用异常: {str(e)}")
            st.session_state.messages.append({
                "role": "assistant",
                "content": "抱歉，系统暂时无法处理您的请求，请稍后重试或简化提问。"
            })
            st.session_state.last_tools = []


# ---------- 侧边栏 ----------
with st.sidebar:
    st.markdown("## ⚙️ 控制面板")
    if is_cloud:
        remaining = max(0, MAX_QUESTIONS - st.session_state.question_count)
        st.caption(f"🔒 演示模式：剩余 {remaining}/{MAX_QUESTIONS} 次提问")

    # ── 预设问题区 ──
    st.markdown("#### 💡 一键测试")
    for category, questions in PRESET_QUESTIONS.items():
        with st.expander(category):
            for i, q in enumerate(questions):
                btn_key = f"preset_{category}_{i}"
                if st.button(q, key=btn_key, use_container_width=True):
                    st.session_state.pending_question = q

    st.divider()

    # ── 知识库上传 ──
    st.markdown("#### 📁 知识库")
    uploaded = st.file_uploader(
        "上传 PDF / TXT，单文件 ≤10MB", type=["txt", "pdf"],
        accept_multiple_files=True, key="uploader"
)

    # 无文件时禁用按钮，防止空点击
    disable_build = uploaded is None or len(uploaded) == 0
    if st.button("🔄 构建知识库", use_container_width=True, disabled=disable_build):
        with st.spinner("正在解析文档、文本切片、构建FAISS+BM25双索引..."):
            # 调用后端，接收后端拼接好的完整提示（含损坏文件警告）
            ok, msg = st.session_state.rag_manager.add_documents(uploaded)
            if ok:
                # 直接打印后端返回的完整信息，包含：总分片数 + 跳过的坏文件提醒
                st.success(msg)
                st.rerun()
            else:
                st.error(f"❌ 知识库构建失败：{msg}")

    # 展示加载分片数量（修复：你原来的 .documents 不存在）
    if st.session_state.rag_manager.is_initialized:
        # corpus_texts 就是所有文本分片列表
        chunk_count = len(st.session_state.rag_manager.corpus_texts)
        st.caption(f"✅ 知识库已就绪，共 {chunk_count} 个文本分片")
    else:
        st.caption("⏳ 未上传文档，知识库类问题将提示上传文件")

    st.divider()



    # ── 能力展示 ──
    st.markdown("#### 💡 能力")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("🏢 **数据库**\n<small>员工薪资/部门</small>", unsafe_allow_html=True)
        st.markdown("🌐 **搜索**\n<small>实时政策/新闻</small>", unsafe_allow_html=True)
    with col2:
        st.markdown("📚 **知识库**\n<small>上传文档问答</small>", unsafe_allow_html=True)
        st.markdown("🔄 **协同**\n<small>自动调度/整合</small>", unsafe_allow_html=True)
    st.divider()

    if st.button("🗑️ 清空对话", use_container_width=True):
        st.session_state.messages = [{
            "role": "assistant",
            "content": "对话已清空。输入新问题或点击左侧预设问题开始测试。"
        }]
        st.session_state.agent_state["messages"] = []
        st.rerun()


# ---------- 主界面 ----------
st.markdown("# 🤖 企业智能信息助手")
st.markdown(
    "<span class='caption'>LangGraph + RAG + Function Calling · 三源信息整合 · 四级容错降级</span>",
    unsafe_allow_html=True
)

# 欢迎引导（仅首次访问时显示）
if len(st.session_state.messages) <= 1:
    st.markdown(WELCOME_HTML, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 历史消息
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        # 仅最后一条助手消息展示日志面板
        if msg["role"] == "assistant" and i == len(st.session_state.messages) - 1:
            last_tools = st.session_state.get("last_tools", [])
            with st.expander("🔍 查看 AI 工具调用完整执行日志", expanded=False):
                if last_tools:
                    st.caption(f"本轮共调用 {len(last_tools)} 个工具")
                    for idx, (tool_name, tool_content) in enumerate(last_tools, 1):
                        icon_map = {
                            "search_web": "🌐 联网搜索",
                            "query_database": "🏢 数据库查询",
                            "search_knowledge_base": "📚 知识库检索"
                        }
                        display_name = icon_map.get(tool_name, f"🔧 {tool_name}")
                        st.markdown(f"**{idx}. {display_name}**")
                        # 超长内容截断防止页面溢出
                        show_text = tool_content[:600]
                        if len(tool_content) > 600:
                            show_text += "\n......（内容过长已截断）"
                        st.code(show_text, language="text")
                        if idx < len(last_tools):
                            st.divider()
                else:
                    st.info("本轮未调用任何工具，由大模型直接生成回答")


# 处理预设问题触发
if st.session_state.pending_question:
    prompt = st.session_state.pending_question
    st.session_state.pending_question = None
    if try_consume_quota():
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            process_message(prompt)
        st.rerun()

# 用户输入
if prompt := st.chat_input("输入问题，或点击左侧边栏的预设问题一键测试："):
    if try_consume_quota():
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            process_message(prompt)
        st.rerun()

# ---------- 页脚 ----------
st.divider()
f1, f2, f3 = st.columns([2, 1, 1])
with f1:
    st.caption("🤖 企业智能信息助手 · 多工具协同 Agent Demo | 个人技术作品")
with f2:
    st.caption("v1.0 · Streamlit Cloud 部署")
with f3:
    st.caption("Powered by LangGraph + Qwen")
