# 企业智能信息助手 · 多工具协同Agent系统

基于 LangGraph + RAG + Function Calling 构建的企业级三源信息整合系统。Agent 自主识别用户意图，协同调度私有知识库、内部数据库与联网搜索三类工具，输出带溯源信息的精准回答，内置完整的安全校验、容错降级与可视化交互能力。

## 🖥️ 演示
<p align="center">
  <img src="assets/demogif.gif" alt="演示动画" width="85%">
</p>

## ✨ 核心特性
- **三源信息协同**：打通私有文档知识库、业务数据库、公网实时资讯，支持单工具与多工具混合调用
- **智能意图路由**：基于大模型推理自动匹配最优信息源，无需人工指定工具类型
- **高可靠 RAG 问答**：递归字符分块 + 置信度拒答双重机制，答案可溯源至原始文档片段
- **企业级安全防护**：SQL 白名单校验、文件格式白名单、会话级数据隔离，敏感数据不出域
- **多级容错降级**：自动重试、关键词扩展检索、结果兜底三级机制，系统静默失败率 < 1%
- **可视化交互界面**：基于 Streamlit 构建，支持多轮对话、工具调用详情全链路展示

## 🛠️ 技术栈
| 分类 | 技术选型 |
|------|----------|
| Agent框架 | LangGraph（状态图、条件边、自动重试）|
| RAG 引擎 | LangChain + FAISS + BM25 + BGE-Reranker + HuggingFace Embeddings(懒加载) |
| 大模型 | qwen-plus(兼容 OpenAI API) |
| 搜索引擎 | Tavily Search API |
| 前端 | Streamlit(自定义css主题) |
| 语言 | Python 3.10+ |
| 工程能力 | 全链路日志、会话状态管理、异常重试机制 |

## 🏗️ 整体架构
系统基于 LangGraph 构建三节点状态机工作流，形成完整的决策-执行-生成闭环：
1. **决策节点**：接收用户问题，分析意图并决策调用工具类型，支持单工具与多工具并行调度
2. **执行节点**：按决策结果执行对应工具，返回结构化结果；调用失败自动触发容错重试
3. **生成节点**：整合多工具返回结果，基于上下文生成带溯源信息的最终回答

## 🚀 快速开始
### 环境要求
- Python 3.10+
- 阿里云百炼 API Key（或其他 OpenAI 兼容大模型服务）
- Tavily Search API Key（联网搜索功能）

### 安装与启动
1. 克隆仓库
```bash
git clone https://github.com/OWO-zh/ai-qa-agent.git
cd ai-qa-agent
```
2. 安装与依赖
```bash
pip install -r requirements.txt
```
3. 初始化数据库
```bash
python init_db.py
```
4. 准备配置文件

在项目根目录创建 `config.yaml`（已加入 .gitignore，不会上传）：
```yaml
aliyun_api_key: "你的阿里云百炼API密钥"
aliyun_base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
tavily_api_key: "你的Tavily搜索密钥"
```
4. 设置 HuggingFace 镜像（国内用户）
```bash
# Windows
set HF_ENDPOINT=https://hf-mirror.com

# Mac/Linux
export HF_ENDPOINT=https://hf-mirror.com
```
5. 启动Web界面
```bash
streamlit run app.py
```
启动后浏览器自动访问 http://localhost:8501 即可使用。


## 📁 项目目录结构
```plaintext
ai-qa-agent/
├── app.py              # Streamlit 前端界面
├── agent.py            # Agent 核心逻辑（LangGraph 三节点状态图）
├── rag_utils.py        # RAG 知识库管理器（懒加载 Embedding，文件校验）
├── init_db.py          # 数据库初始化脚本（含测试员工数据）
├── config.yaml.example # 配置文件模板（复制为 config.yaml 并填入真实密钥）
├── requirements.txt    # 精简核心依赖（已锁定版本）
├── assets/
│   └── demogif.gif     # 演示动画
└── docs/
    └── TECHNICAL.md    # 详细技术文档
```
## 📊 效果指标
- **工具调度准确率**：100%(20/20)
- **复杂查询平均工具调用次数**：< 2 次
- **RAG 知识范围内回答准确率**：90%+
- **无匹配内容拒答准确率**：96%
- **系统静默失败率**：< 1%
- **多工具复杂查询**:10-15s
- **SQL自纠错**:2/2成功

## 🛤️ 后续规划

- 接入更多工具类型（计算器、代码执行、图表生成）
- 支持多用户权限体系与工具访问范围管控
- 接入 Redis 实现会话状态持久化
- 增加 Prompt 注入防护与输出内容审核

## 📖 详细文档
参阅 [技术文档](docs/TECHNICAL.md) 了解架构设计、模块细节和安全策略。

## 📝 许可证
MIT License

## 📞 联系方式
- 邮箱：[YASK2025@163.com](mailto:YASK2025@163.com)

## 声明
本项目为个人技术 Demo，用于展示 AI 应用工程能力。若需用于生产环境，建议进行安全审计、性能优化和多用户适配。