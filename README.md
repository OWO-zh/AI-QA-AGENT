# AI PDF智能问答与 Agent 系统

本项目包含两个核心 AI 应用，展示了基于大模型的 RAG（检索增强生成）和 Agent（智能体）开发能力。

## 📁 项目结构
- `rag_web.py`：PDF 智能问答网页应用
- `agent_demo.py`：联网搜索智能体（基于 LangGraph）
- `15data/`：存放待分析的 PDF 文件
- `faiss_index/`：向量数据库存储目录(运行后生成)

## 📚 项目一：PDF 智能问答系统 (RAG)

上传 PDF 文档，系统自动构建知识库，支持基于文档内容的智能问答。
- **优化**: RAG 项目加入 “混合检索 (向量 + BM25) + BGE-Reranker 重排序”，提升模糊查询准确率
- **技术栈**：LangChain + FAISS + Streamlit + 阿里云百炼（qwen-plus）
- **核心功能**：PDF 加载、文本分块、向量化存储、相似度检索、RAG 增强生成

### 运行方式
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
streamlit run rag_web.py

## 📚 项目二：联网搜索 Agent

智能体可自主判断是否需要联网搜索，获取最新信息后生成回答.
- **优化**: Agent 项目加入 “SQL 数据库查询工具”，工作流升级为 “可循环调用的多工具 ReAct 智能体”
- **技术栈**：LangGraph + Tavily Search API + 阿里云百炼（qwen-plus）
- **核心功能**：Function Calling、多节点工作流编排、工具调用

### 运行方式
```bash
python agent_demo.py