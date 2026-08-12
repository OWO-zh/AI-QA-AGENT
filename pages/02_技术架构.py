"""
02_技术架构.py — 技术架构展示页
===============================
Streamlit 多页面应用的第二页，面向面试官展示完整技术设计。
包含：Mermaid 架构图、技术栈清单、容错机制、核心特性。
"""

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="技术架构 | 企业智能信息助手", page_icon="📐", layout="wide")

# ===== Mermaid 渲染工具（优化CDN国内加载更快）=====
def render_mermaid(code: str, height: int = 500) -> None:
    """使用 Mermaid CDN 在 Streamlit 中渲染架构图。

    通过 iframe 加载 Mermaid JS 库，将传入的 flowchart 代码渲染为 SVG 矢量图。
    缩放采用 transform: scale()（全浏览器支持），同步补偿容器宽高使滚动条正确适配。
    若 CDN 加载失败，用户可展开下方代码块查看原始 Mermaid 源码。

    参数:
        code: Mermaid flowchart 代码（不含 ```mermaid 标记）
        height: iframe 高度（像素）
    """
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    body {{
        margin: 0; padding: 12px; background: #fff;
        font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    }}
    /* 关键：禁止 SVG 收缩到容器宽度，保持自然尺寸 */
    .mermaid svg {{
        width: auto !important;
        max-width: none !important;
    }}
    /* 缩放工具栏（sticky 悬浮在顶部） */
    .zoom-bar {{
        position: sticky; top: 0; z-index: 10;
        display: flex; align-items: center; gap: 8px;
        padding: 6px 10px; background: #f8fafc;
        border: 1px solid #e2e8f0; border-radius: 8px;
        margin-bottom: 10px;
    }}
    .zoom-bar button {{
        padding: 4px 14px; border: 1px solid #cbd5e1;
        border-radius: 6px; background: #fff; cursor: pointer;
        font-size: 14px; color: #334155;
    }}
    .zoom-bar button:hover {{ background: #eff6ff; border-color: #3b82f6; color: #1e40af; }}
    .zoom-bar .tip {{ font-size: 13px; color: #64748b; margin-left: auto; }}
    /* 缩放目标：transform-origin 从左上角开始放大 */
    #diagram-wrap .mermaid {{ transform-origin: 0 0; }}
</style>
</head>
<body>
<div class="zoom-bar">
    <button onclick="setZoom(0.75)">－ 缩小</button>
    <button onclick="setZoom(1)">100%</button>
    <button onclick="setZoom(1.5)">＋ 放大</button>
    <button onclick="setZoom(2)">＋＋ 两倍</button>
    <span class="tip">横向滚动查看完整流程</span>
</div>
<div id="diagram-wrap">
<pre class="mermaid">
{code}
</pre>
</div>
<script src="https://unpkg.com/mermaid@10/dist/mermaid.min.js"></script>
<script>
    mermaid.initialize({{
        startOnLoad: false,
        theme: 'base',
        securityLevel: 'strict',
        themeVariables: {{ fontSize: '17px' }}
    }});

    var wrap = document.getElementById('diagram-wrap');
    var naturalW = 0, naturalH = 0;

    function measureNatural() {{
        var el = document.querySelector('.mermaid');
        if (!el) return;
        naturalW = el.scrollWidth;
        naturalH = el.scrollHeight;
    }}

    function setZoom(z) {{
        var el = document.querySelector('.mermaid');
        if (!el) return;
        if (naturalW === 0) measureNatural();
        if (z === 1) {{
            el.style.transform = 'none';
            wrap.style.width = '';
            wrap.style.height = '';
        }} else {{
            // transform 缩放不改变布局尺寸，手动补偿容器宽高使滚动条生效
            el.style.transform = 'scale(' + z + ')';
            wrap.style.width = Math.ceil(naturalW * z) + 'px';
            wrap.style.height = Math.ceil(naturalH * z) + 'px';
        }}
    }}

    // 渲染完成后自动量取自然尺寸
    mermaid.run({{
        nodes: document.querySelectorAll('.mermaid'),
        suppressErrors: false
    }}).then(function() {{
        measureNatural();
    }});
</script>
</body>
</html>"""
    components.html(html, height=height, scrolling=True)


# ===== 1. 替换为README里的Agent三节点完整流程图 =====
AGENT_FLOW = """flowchart LR
    %% ========== 样式定义（两张图完全统一） ==========
    classDef entry fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
    classDef decide fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#0d47a1
    classDef tool fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#bf360c
    classDef generate fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#4a148c
    classDef error fill:#ffebee,stroke:#c62828,stroke-width:2px,color:#b71c1c
    classDef fallback fill:#fce4ec,stroke:#ad1457,stroke-width:1px,color:#880e4f,stroke-dasharray: 5 5
    classDef process fill:#fafafa,stroke:#90a4ae,stroke-width:1px,color:#37474f
    classDef subgraph_box fill:none,stroke:#cfd8dc,stroke-width:1px

    %% ========== 入口与配置加载（修复：删除未定义CONFIG_BOX） ==========
    START[用户输入问题]:::entry --> CONFIG

    subgraph config["配置加载"]
        CONFIG{Secrets 可用?}:::decide
        SECRETS[读取 Secrets 密钥]:::process
        YAML_TRY{config.yaml 存在?}:::decide
        YAML[读取 YAML 配置]:::process
        FATAL[❌ 启动失败]:::error
    end
    class config subgraph_box

    CONFIG -- 是 --> SECRETS
    CONFIG -- 否 --> YAML_TRY
    YAML_TRY -- 是 --> YAML
    YAML_TRY -- 否 --> FATAL

    %% ========== ① 决策节点 ==========
    SECRETS & YAML --> DECIDE
    DECIDE[① decide_node 意图识别<br/>LLM Function Calling 自主决策工具]:::decide
    DECIDE -.->|LLM异常| DECIDE_FB[静默兜底提示]:::fallback

    DECIDE --> ROUTE_D{需要调用工具?}:::decide
    ROUTE_D -- 否 --> ANSWER
    ROUTE_D -- 是 --> TOOLS

    %% ========== ② 工具执行节点 ==========
    TOOLS[② tool_execute_node 工具执行<br/>解析参数、分发执行]:::tool

    subgraph tools["三类工具"]
        WEB[search_web<br/>Tavily 联网搜索]:::tool
        DB[query_database<br/>SQL 安全校验查询]:::tool
        KB[search_knowledge_base<br/>RAG 混合检索]:::tool
    end
    class tools subgraph_box

    TOOLS --> WEB & DB & KB
    WEB & DB & KB --> COLLECT[汇总结果 标记状态]:::process

    COLLECT --> SQL_RETRY{SQL错误 且 重试<2?}:::decide
    SQL_RETRY -- 是 --> RETRY[🔄 带回错误修正SQL]:::fallback --> DECIDE
    SQL_RETRY -- 否 --> ANSWER

    %% ========== ③ 答案生成节点 ==========
    ANSWER[③ answer_node 结果整合<br/>分点展开 + 标注来源]:::generate
    ANSWER -.->|生成异常| ANSWER_FB[兜底话术替换]:::fallback

    ANSWER --> CHECK{答案合法非空?}:::decide
    CHECK -- 否 --> EMPTY_FB[替换为兜底回答]:::fallback
    CHECK -- 是 --> DONE

    DECIDE_FB & ANSWER_FB & EMPTY_FB --> DONE
    DONE[📤 返回 final_answer]:::entry
"""

# ===== 2. 替换为README里完整RAG混合检索流程图 =====
RAG_FLOW = """flowchart LR
    %% 样式定义 - 与Agent流程图配色体系对齐
    classDef entry fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
    classDef decide fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#0d47a1
    classDef tool fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#bf360c
    classDef generate fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#4a148c
    classDef error fill:#ffebee,stroke:#c62828,stroke-width:2px,color:#b71c1c
    classDef process fill:#fafafa,stroke:#90a4ae,stroke-width:1px,color:#37474f
    classDef subgraph_box fill:none,stroke:#cfd8dc,stroke-width:1px

    %% ========== 索引构建链路 ==========
    subgraph idx["索引构建 add_documents"]
        direction LR
        U1["上传文件"]:::entry
        U2{"数量≤5 校验通过?"}:::decide
        U3["拒绝上传<br/>提示文件数量超限"]:::error
        U4["文本预处理<br/>清洗格式/去噪/归一化"]:::process
        U5["文本分片<br/>chunk=500 overlap=100"]:::process
        U6["Embedding 模型向量化"]:::process
        U7["FAISS 向量索引构建"]:::decide
        U8["BM25 关键词索引构建"]:::tool
        U9["双索引落库持久化"]:::entry

        U1 --> U2
        U2 -- "否" --> U3
        U2 -- "是" --> U4 --> U5 --> U6 --> U7
        U5 --> U8
        U7 --> U9
        U8 --> U9
    end
    class idx subgraph_box

    %% ========== 查询检索链路 ==========
    Q["用户查询"]:::entry

    subgraph recall["双路召回层"]
        direction TB
        S1["FAISS 语义检索<br/>向量相似度匹配"]:::decide
        S2["BM25 关键词检索<br/>词法精确匹配"]:::tool
    end
    class recall subgraph_box

    S3["去重合并候选片段"]:::process
    S4{"召回结果是否为空?"}:::decide
    S5["构造 Query-段落 配对"]:::process

    subgraph rerank["BGE 精排层"]
        direction TB
        S6["CrossEncoder 相关性打分"]:::generate
        S7["按分数降序取 Top-K"]:::generate
    end
    class rerank subgraph_box

    S8{"是否达到相关性阈值?"}:::decide
    S9["低分片段过滤"]:::process
    S10["扩大候选池+跨文档去重"]:::process
    S11["优先覆盖不同来源文档"]:::process
    S12["格式化输出上下文"]:::process

    %% 兜底分支
    fallback1["召回为空<br/>触发兜底回复"]:::error
    fallback2["无高相关结果<br/>触发低置信度提示"]:::error

    OUTPUT["返回检索结果"]:::entry

    %% 连线逻辑
    Q --> S1
    Q --> S2
    S1 --> S3
    S2 --> S3
    S3 --> S4

    S4 -- "是" --> fallback1 --> OUTPUT
    S4 -- "否" --> S5 --> S6 --> S7 --> S8

    S8 -- "否" --> fallback2 --> OUTPUT
    S8 -- "是" --> S9 --> S10 --> S11 --> S12 --> OUTPUT
"""


# ===== 页面渲染主体（完全保留你原有排版）=====
st.markdown("# 📐 技术架构")
st.markdown("<span class='caption'>LangGraph 三节点 Agent · 混合检索 RAG · 四级容错降级</span>", unsafe_allow_html=True)
st.markdown("---")

# 两张架构图顺序展示
# （不用 tabs：隐藏标签页中的 iframe 渲染不稳定，会导致第二张图空白）
st.markdown("#### 🔄 Agent 三节点主流程")
st.markdown("Agent 决策-执行-生成闭环（含全部容错降级路径）")
st.caption("蓝色=决策层 · 橙色=工具层 · 紫色=生成层 · 红色=异常 · 粉色虚线=兜底")
render_mermaid(AGENT_FLOW, height=850)
with st.expander("📝 查看 Agent 流程图 Mermaid 源码"):
    st.code(AGENT_FLOW, language="mermaid")

st.markdown("---")
st.markdown("#### 🔍 RAG 混合检索流水线")
st.markdown("文档上传 → 双路召回 → BGE精排 → 来源多样性过滤")
st.caption("绿色=入口/出口 · 蓝色=向量检索 · 橙色=关键词检索 · 紫色=精排打分")
render_mermaid(RAG_FLOW, height=850)
with st.expander("📝 查看 RAG 流程图 Mermaid 源码"):
    st.code(RAG_FLOW, language="mermaid")

st.markdown("---")

# ── 技术栈模块（原样保留）──
st.markdown("## 🛠️ 技术栈")
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    **Agent 框架**
    - LangGraph（状态图 + 条件边）
    - Function Calling 自动路由
    - TypedDict 类型安全状态

    **RAG 引擎**
    - FAISS 向量存储
    - BM25 关键词索引
    - BGE-Reranker 精排
    - bge-small-zh-v1.5 嵌入
    """)

with col2:
    st.markdown("""
    **LLM & 搜索**
    - qwen-plus（阿里云百炼）
    - Tavily Search API
    - OpenAI 兼容接口

    **前端**
    - Streamlit 可视化
    - 自定义 CSS 主题
    - 会话状态管理
    """)

with col3:
    st.markdown("""
    **工程化**
    - 全链路结构化日志
    - 配置双轨降级
    - SQL 安全白名单
    - 临时文件自动清理

    **语言 & 环境**
    - Python 3.10+
    - SQLite 本地数据库
    - HuggingFace 模型懒加载
    """)

st.markdown("---")

# ── 核心特性亮点 ──
st.markdown("## ✨ 核心技术亮点")

highlights = [
    ("🎯 智能意图路由",
     "基于 LLM Function Calling 自动识别用户意图，匹配最优信息源。支持单工具查询与多工具并行调度，工具调度准确率 100%（20/20 用例验证）。"),
    ("📚 混合检索 RAG",
     "FAISS 向量语义检索 + BM25 关键词检索双路召回，合并去重后经 BGE-Reranker 精排。引入来源多样性算法，避免多文档场景下的检索偏置问题。"),
    ("🛡️ 四级容错降级",
     "一级：工具失败自动重试 → 二级：关键词扩展 / SQL 错误回传 LLM 修正 → 三级：LLM 调用异常静默兜底 → 四级：全局兜底回答，系统静默失败率 0%。"),
    ("🔒 企业级安全",
     "SQL 三层校验（SELECT 白名单 + 关键字黑名单 + 表名白名单）。文件上传防路径遍历、类型白名单、大小限制。API Key 通过 .gitignore 保护。"),
    ("📊 可观测性",
     "全链路分级日志（INFO/WARNING/ERROR），记录意图决策、工具调用、执行耗时。日志持久化至 agent_run.log，支持问题回溯。"),
    ("🔌 可扩展设计",
     "新增工具只需三步：添加 Function Calling 定义 → 实现工具函数 → 注册到 tool_execute_node。模型名、重排序模型均通过配置外部注入，零代码切换。"),
]

for title, desc in highlights:
    with st.expander(title):
        st.markdown(desc)

st.markdown("---")

# ── 验证量化指标 ──
st.markdown("## 📊 效果指标（20条用例验证）")
metrics = st.columns(4)
metrics[0].metric("工具调度准确率", "100%", "20/20")
metrics[1].metric("系统静默失败率", "0%", "全覆盖")
metrics[2].metric("SQL 自纠错", "2/2", "100%通过")
metrics[3].metric("多文档覆盖", "✅ 通过", "无遗漏")

st.markdown("---")
# 修正尾部跳转，避免404
st.caption("📖 更详细的技术设计说明请参阅 TECHNICAL.md | 在线体验请返回首页")
