"""
app.py — Streamlit 可视化界面
=============================
企业智能信息助手的 Web 入口，基于 Streamlit 构建聊天界面。

功能：
    - 示例知识库自动加载：访客开箱即问，无需上传（服务器级缓存共享只读）
    - 建议问题 chips + 20 条预设问题：一键测试，面试官无需摸索
    - 侧边栏：文件上传、知识库构建、恢复示例库、能力展示、对话清空
    - 主区域：聊天消息流，支持工具调用详情展开
    - 会话管理：基于 st.session_state 的多轮对话状态保持（会话索引与示例库隔离）

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
    /* 功能徽章（副标题下一行小徽章） */
    .feature-pill {
        display: inline-block;
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 24px;
        padding: 0.3rem 0.85rem;
        margin: 0.2rem 0.25rem 0.2rem 0;
        font-size: 0.78rem;
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

# ===== 输入框上方建议问题 chips（知识库/数据库/联网各 1 条） =====
SUGGESTED_QUESTIONS = [
    "知识库里有什么内容？",
    "研发部平均工资是多少？",
    "2026 年 AI 有哪些新政策？",
]


# ===== 云端演示防护配置（仅 is_cloud 时生效，本地开发不受限制）=====
MAX_QUESTIONS = 25   # 每个会话最多提问次数（覆盖 20 条用例 + 5 次余量）
MIN_INTERVAL = 8     # 两次提问最小间隔（秒），防脚本刷量

# ---------- 示例知识库（服务器级缓存，所有会话共享只读） ----------
SAMPLE_DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_docs")


class _SampleDocFile:
    """把本地示例文档包装成与 Streamlit UploadedFile 相同的最小接口。

    复用 rag_utils.add_documents 的校验与解析流程（含跳过清单展示），
    不引入新的文件解析逻辑。
    """

    def __init__(self, path: str):
        self.name = os.path.basename(path)
        self.size = os.path.getsize(path)
        self._path = path

    def getvalue(self):
        """读取文件字节内容（add_documents 通过此方法取内容）。"""
        with open(self._path, "rb") as f:
            return f.read()


@st.cache_resource
def build_sample_rag():
    """构建示例知识库索引（服务器级缓存，命中后秒开）。

    首次调用时解析 sample_docs/ 下全部 .txt 并构建 FAISS+BM25 双索引，
    之后所有会话共享同一份只读索引；模型内存由 rag_utils 模块级共享
    单例控制，与用户会话索引不重复加载。
    冷启动提示由调用处（init_session 外层 st.spinner）统一提供，此处不再
    嵌套 spinner 文案，避免双重提示。

    返回:
        (RAGManager 示例库实例, add_documents 结构化构建结果)
    """
    names = sorted(f for f in os.listdir(SAMPLE_DOCS_DIR) if f.lower().endswith(".txt"))
    files = [_SampleDocFile(os.path.join(SAMPLE_DOCS_DIR, name)) for name in names]
    sample_rag = RAGManager()
    result = sample_rag.add_documents(files)
    return sample_rag, result


# ---------- 激活知识库选择（示例库 / 会话索引） ----------
def get_active_rag():
    """返回当前生效的知识库：会话已上传构建→会话索引，否则→示例库索引。"""
    return (st.session_state.rag_manager if st.session_state.rag_manager.is_initialized
            else st.session_state.sample_rag)


def refresh_agent_rag():
    """把当前生效的知识库注入 Agent（初始化 / 构建成功 / 恢复示例库后调用）。"""
    set_rag_manager(get_active_rag())


# ---------- 会话初始化 ----------
def init_session():
    """初始化 Streamlit 会话状态。"""
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "messages" not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant",
            "content": "你好！我是企业智能信息助手。点击下方推荐问题或左侧预设即可体验，也可直接输入任意问题。"
        }]
    if "rag_manager" not in st.session_state:
        # 会话级用户索引：每会话独立，上传构建只影响本会话，不污染示例库缓存
        st.session_state.rag_manager = RAGManager(
            reranker_model=config.get("reranker_model", "BAAI/bge-reranker-base")
        )
    if "sample_rag" not in st.session_state:
        # 示例知识库：服务器级缓存共享只读（首次构建约 12s，命中后秒开）
        st.session_state.sample_rag, st.session_state.sample_result = build_sample_rag()
    if "sample_result_shown" not in st.session_state:
        st.session_state.sample_result_shown = False
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


# 冷启动提示：耗时初始化（示例库构建/模型加载）统一包 spinner，
# 缓存命中时瞬间通过，不出现长时间 spinner（CLAUDE.md 工程纪律 4）
with st.spinner("🚀 应用初始化中，首次访问需加载 AI 模型，约 10~30 秒，请稍候…"):
    init_session()
    refresh_agent_rag()

# ---------- 云端访问保护：密码门（仅云端生效，本地开发直接跳过）----------
if is_cloud:
    demo_pwd = config.get("demo_password", "")
    if not st.session_state.authed:
        if not demo_pwd:
            st.error("演示密码未配置，请联系管理员。")
            st.stop()
        st.markdown("# 🤖 企业智能信息助手")
        st.markdown("本演示为公开访问，请输入体验密码后进入。")
        with st.form("auth_form"):
            pwd_input = st.text_input("访问密码", type="password")
            submitted = st.form_submit_button("进入演示")
        # 密码公开化：登录页直接展示体验密码（防滥用软门槛，非隐私保护）。
        # 仅云端且 demo_password 已配置时才会走到这里；本地开发无密码门。
        st.caption(f"💡 体验密码：{demo_pwd}（本项目为公开演示，密码已开放）")
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
            try:
                # 后端返回结构化结果：success_chunks 分片数 + skipped 跳过清单 + message 汇总
                result = st.session_state.rag_manager.add_documents(uploaded)
            except Exception as e:
                # 未捕获异常兜底：界面只给友好提示，细节进日志，不裸抛 traceback
                logger.error(f"知识库构建未捕获异常: {type(e).__name__} - {str(e)}", exc_info=True)
                st.error("知识库构建失败：系统内部异常，请重试或更换文件（详情已记录日志）。")
            else:
                if result["success_chunks"] > 0:
                    # 构建成功：绿色提示（含入库分片数），并切换 Agent 到会话索引
                    st.success(result["message"])
                    refresh_agent_rag()
                else:
                    # 全部文件失败：红色提示，明确索引未更新
                    st.error(f"❌ 知识库构建失败：{result['message']}")
                # 逐文件展示跳过警告（成功/失败分支都可能存在；无跳过则不显示）
                for item in result["skipped"]:
                    st.warning(f"⚠️ 已跳过「{item['file']}」：{item['reason']}")
                # 注意：这里不再 st.rerun()——之前提示刚显示就被重跑冲掉，导致用户看不到任何反馈

    # 示例库构建异常/跳过警告：每会话只展示一次（不静默失败）
    if not st.session_state.sample_result_shown:
        st.session_state.sample_result_shown = True
        sample_result = st.session_state.sample_result
        if sample_result["success_chunks"] == 0:
            st.error(f"示例知识库加载失败：{sample_result['message']}")
        for item in sample_result["skipped"]:
            st.warning(f"⚠️ 示例文档「{item['file']}」加载跳过：{item['reason']}")

    # 当前知识库状态
    if st.session_state.rag_manager.is_initialized:
        # corpus_texts 就是所有文本分片列表
        chunk_count = len(st.session_state.rag_manager.corpus_texts)
        st.caption(f"✅ 已使用你上传的文档（共 {chunk_count} 个分片）")
        # 已上传过文档时，提供切回示例库的入口
        if st.button("↩️ 恢复示例库", use_container_width=True):
            # 清空会话用户索引，回到示例库（对话记录保留）
            st.session_state.rag_manager = RAGManager(
                reranker_model=config.get("reranker_model", "BAAI/bge-reranker-base")
            )
            refresh_agent_rag()
            st.rerun()
    else:
        st.caption("📦 示例库已就绪，可直接提问，也可上传文档替换")

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

# 功能徽章（副标题下一行小徽章；详细技术叙事见页面底部「关于本项目」）
st.markdown(
    "<div style='margin-top:0.4rem;'>"
    "<span class='feature-pill'>📚 私有知识库</span>"
    "<span class='feature-pill'>🏢 SQL 数据库</span>"
    "<span class='feature-pill'>🌐 联网搜索</span>"
    "<span class='feature-pill'>🔄 多工具协同</span>"
    "<span class='feature-pill'>🛡️ SQL 安全校验</span>"
    "<span class='feature-pill'>🔁 四级容错</span>"
    "</div>",
    unsafe_allow_html=True
)

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

# 建议问题 chips（点击走与预设按钮相同的提问链路）
st.markdown(
    "<span class='caption'>💡 快速提问</span>",
    unsafe_allow_html=True
)
if selected := st.pills("快速提问", SUGGESTED_QUESTIONS, key="quick_pills", label_visibility="collapsed"):
    st.session_state.quick_pills = None  # 立即重置选中值，保证同一 chip 可重复点击
    st.session_state.pending_question = selected

# 用户输入
if prompt := st.chat_input("输入问题，或点击左侧边栏的预设问题一键测试："):
    if try_consume_quota():
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            process_message(prompt)
        st.rerun()

# ---------- 关于本项目（原欢迎大卡的技术叙事，信息分层到此处） ----------
with st.expander("📖 关于本项目"):
    st.markdown("""
**企业智能信息助手** 是基于 **LangGraph + RAG + Function Calling** 构建的多工具协同 Agent。

- **LangGraph 三节点状态图**：decide（意图识别）→ tools（工具执行）→ answer（答案生成），含 SQL 错误回传自纠错
- **混合检索 RAG**：FAISS 向量 + BM25（jieba 中文分词）双路召回，BGE-Reranker 精排，来源多样性保证多文档覆盖
- **Function Calling 工具调度**：自主决策调用内部数据库、私有知识库、联网搜索，支持多工具协同
- **四级容错降级**：工具重试 → 关键词扩展/SQL 自纠错 → LLM 异常兜底 → 全局兜底，静默失败率 0%
- **企业级安全**：SQL 三层校验、文件上传白名单、云端演示密码门与额度限流

上传 PDF/TXT 文档即可体验私有知识库问答；左侧「技术架构」页面含完整流程图与技术设计。
""")

# ---------- 页脚 ----------
st.divider()
f1, f2, f3 = st.columns([2, 1, 1])
with f1:
    st.caption("🤖 企业智能信息助手 · 多工具协同 Agent Demo | 个人技术作品")
with f2:
    st.caption("v1.0 · Streamlit Cloud 部署")
with f3:
    st.caption("Powered by LangGraph + Qwen")
