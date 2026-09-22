## 常用命令
   - 本地运行:streamlit run app.py
   - 测试:pytest tests/ -v
   - 冒烟:python smoke_test.py

## 关键文件地图
- agent.py:核心编排文件——LangGraph 三节点图(decide→tools→answer)、AgentState、
  配置加载(顶部双轨:st.secrets / config.yaml)、三个工具函数、validate_sql_safety
  SQL 三层校验、TOOLS 定义、日志配置、命令行测试入口(python agent.py)
- rag_utils.py:RAGManager 类——jieba 分词(_tokenize)、add_documents(文档校验与
  FAISS+BM25 双索引构建)、_hybrid_retrieve(混合检索)、search(来源多样性+溯源)、
  模型共享单例(_get_shared_embeddings/_get_shared_reranker 懒加载+双检锁)
- app.py:Streamlit 入口——页面配置与 CSS、20 条预设问题、会话初始化、云端密码门
  与额度限制、侧边栏、聊天 UI、工具调用日志展示、build_sample_rag() 示例知识库
  构建(@st.cache_resource 服务器级共享只读缓存)、会话级 RAGManager 隔离、
  get_active_rag()/refresh_agent_rag() 激活切换、「恢复示例库」按钮、st.pills
  快速提问 chips、底部「关于本项目」expander(原 WELCOME_HTML 欢迎大卡已移除)
- config.yaml:本地配置(含 API 密钥,禁止提交);云端等价物为 .streamlit/secrets.toml
- company.db:SQLite 演示数据库(employees 表)
- agent_run.log:运行日志(项目根)
- .hf_cache/:HuggingFace 模型本地缓存(仅本地环境,云端不生成)

## Git 纪律
- 每个任务开始前,必须先运行 git status --short 并汇报;若存在未提交改动,提醒我先处理(提交或 stash),禁止在脏工作区上叠加新改动
- 禁止主动执行 git commit / git push / git reset --hard / git clean,除非我在本轮指令中明确要求
- 任务完成后:输出建议的 commit message(Conventional Commits 风格,如 feat(rag): xxx),由我人工确认后提交
- 每次只做一个逻辑变更;若任务涉及多个独立改动,建议我分多次 commit

## 禁止触碰
- .env / .streamlit/secrets.toml:密钥文件,任何情况下不得读取内容或写入代码
- agent_run.log:禁止读取历史日志、删除或清空；程序运行时追加写入不受限；排查问题时由我人工摘录片段提供
- .hf_cache/:HuggingFace 模型缓存,禁止手动修改内容,禁止提交到 git
- config.yaml:含 API 密钥,禁止读取/打印内容,禁止写入代码或 commit message;代码通过 config 加载区引用即可
- company.db:演示数据库,禁止写入、修改或删除数据及表结构;如任务确实需要改动,先征得我同意

## 任务完成报告格式
每次任务结束输出:
1. 变更清单(文件 + 行数)
2. 影响面(可能受牵连的模块)
3. 测试/冒烟结果
4. 建议 commit message
5. 遗留风险(若有)

## 工程纪律
1. **技术栈固定**：优先使用 LangGraph、LangChain 组件、FAISS、rank_bm25、sentence_transformers、Streamlit、SQLite，不随意引入额外第三方依赖。

2. **状态设计**：LangGraph 代码遵循现有 AgentState 结构；新增控制字段必须注释说明用途；状态修改必须考虑新会话的轮次清零与初始化逻辑，Streamlit session_state 中的 Agent 状态在会话开始时必须干净初始化。

3. **RAG 流水线**：严格遵循「双路召回→文本去重→Reranker 精排→来源多样性筛选」四层结构；文档处理必须做单文件故障隔离（单文件解析失败跳过并记 WARNING，不中断整批）；临时文件必须在 finally 块清理。

4. **前端交互**：Streamlit 耗时操作必须加 spinner 文案提示；用户可见错误必须友好，内部错误详情只写入日志文件；SQLite 写操作用 with 事务块，设置 timeout 参数防多会话并发下的 database is locked。

5. **兼容约定**：jieba 分词为可选依赖，未安装时自动降级回空格分词并记 WARNING；所有新增功能保持向下兼容。

6. **工具安全**：Agent 工具入参全部二次校验（含 LLM 生成的 SQL——参数化之外表名字段过白名单）；知识库/联网搜索结果注入 prompt 前做长度截断，防检索内容中夹带的注入指令劫持 Agent 行为。
