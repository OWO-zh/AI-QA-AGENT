import streamlit as st
import uuid
import sys
import os

# ---------- 页面配置 ----------
st.set_page_config(
    page_title="企业智能信息助手",
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
    /* 全局字体与基础色 */
    * {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
    }
    html, body, [class*="css"] {
        color: #1e293b;
        background-color: #ffffff;
    }
    
    /* 主内容区留白 */
    .main .block-container {
        padding: 2rem 3rem 1rem 3rem;
        max-width: 1200px;
    }
    
    /* 标题弱化 */
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
    
    /* 侧边栏 - 浅灰底，窄化间距 */
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
    
    /* 按钮 - 统一圆角、浅蓝点缀 */
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
    
    /* 文件上传组件 */
    [data-testid="stFileUploader"] section {
        border: 2px dashed #cbd5e1;
        border-radius: 12px;
        background-color: #f9fafb;
        transition: border-color 0.2s;
    }
    [data-testid="stFileUploader"]:hover section {
        border-color: #3b82f6;
    }
    
    /* 聊天消息气泡 */
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
    /* 用户消息微微蓝背景 */
    [data-testid="stChatMessage"] [data-testid="chatAvatarIcon-user"] ~ div {
        background-color: #eff6ff;
    }
    
    /* 输入框圆角 + 聚焦动画 */
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
    
    /* 折叠面板 (expander) */
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
    
    /* 代码块 */
    .stCodeBlock {
        border-radius: 8px;
        background-color: #f1f5f9 !important;
    }
    
    /* 成功/警告提示圆角 */
    .stSuccess, .stWarning, .stError {
        border-radius: 10px;
    }
    
    /* 分割线弱化 */
    hr {
        border-color: #f1f5f9;
        margin: 1.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

# ---------- 导入模块 ----------
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent import agent, set_rag_manager, logger
from rag_utils import RAGManager

# ---------- 会话初始化 ----------
def init_session():
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "messages" not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant",
            "content": "你好！我是企业智能信息助手，支持内部数据库查询、联网搜索、私有知识库问答。"
        }]
    if "rag_manager" not in st.session_state:
        st.session_state.rag_manager = RAGManager()
    if "agent_state" not in st.session_state:
        st.session_state.agent_state = {
            "messages": [],
            "final_answer": "",
            "retry_count": 0,
            "tool_result_status": "",
            "has_sql_error": False,
            "error_message": ""
        }

init_session()
set_rag_manager(st.session_state.rag_manager)

# ---------- 侧边栏 ----------
with st.sidebar:
    st.markdown("## ⚙️ 控制面板")
    st.markdown("#### 📁 知识库")
    uploaded = st.file_uploader("上传 PDF / TXT，单文件 ≤10MB", type=["txt", "pdf"],
                                accept_multiple_files=True, key="uploader")
    if st.button("🔄 构建知识库", use_container_width=True):
        if not uploaded:
            st.warning("请上传文件")
        else:
            with st.spinner("解析文档、构建索引..."):
                ok, msg = st.session_state.rag_manager.add_documents(uploaded)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    if st.session_state.rag_manager.is_initialized:
        st.caption("✅ 知识库已就绪")
    else:
        st.caption("⏳ 未上传文档")
    st.divider()

    st.markdown("#### 💡 能力")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("🏢 **数据库**  \n<small>员工薪资/部门</small>", unsafe_allow_html=True)
        st.markdown("🌐 **搜索**  \n<small>实时政策/新闻</small>", unsafe_allow_html=True)
    with col2:
        st.markdown("📚 **知识库**  \n<small>上传文档问答</small>", unsafe_allow_html=True)
        st.markdown("🔄 **协同**  \n<small>自动调度/整合</small>", unsafe_allow_html=True)
    st.divider()

    if st.button("🗑️ 清空对话", use_container_width=True):
        st.session_state.messages = [{"role": "assistant", "content": "对话已清空。"}]
        st.session_state.agent_state["messages"] = []
        st.rerun()

# ---------- 主界面 ----------
st.markdown("# 🤖 企业智能信息助手")
st.markdown("<span class='caption'>LangGraph + RAG + Function Calling · 三源信息整合</span>", unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

# 历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 用户输入
if prompt := st.chat_input("输入问题，例如：研发部薪资最高的是谁？同时查下2026年AI政策"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("分析中..."):
            try:
                st.session_state.agent_state.update({
                    "retry_count": 0, "has_sql_error": False,
                    "error_message": "", "tool_result_status": ""
                })
                st.session_state.agent_state["messages"].append({"role": "user", "content": prompt})
                new_state = agent.invoke(st.session_state.agent_state)
                st.session_state.agent_state = new_state
                answer = new_state["final_answer"]

                # 提取本轮工具消息
                tools = []
                for m in reversed(new_state["messages"]):
                    if m.get("role") == "tool":
                        tools.append((m.get("name", "工具"), m.get("content", "")))
                    elif m.get("role") in ("user", "assistant"):
                        break
                tools.reverse()

                st.markdown(answer)
                if tools:
                    with st.expander("🔍 查看工具调用详情"):
                        for tn, tc in tools:
                            st.markdown(f"**`{tn}`**")
                            st.code(tc[:300] + ("..." if len(tc) > 300 else ""), language="text")

                st.session_state.messages.append({"role": "assistant", "content": answer})
                logger.info(f"会话 {st.session_state.session_id} 完成一轮对话")
            except Exception as e:
                logger.error(str(e))
                st.error(f"系统异常：{e}")
                st.session_state.messages.append({"role": "assistant", "content": "抱歉，系统暂时不可用。"})