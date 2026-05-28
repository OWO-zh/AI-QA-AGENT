import json
import yaml
import sqlite3
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from tavily import TavilyClient
from openai import OpenAI

# --- 1. 配置 ---
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

openai_client = OpenAI(api_key=config["aliyun_api_key"], base_url=config["aliyun_base_url"])
tavily_client = TavilyClient(api_key=config["tavily_api_key"])

# --- 2. 状态定义 ---
class AgentState(TypedDict):
    messages: list          # 对话历史，包含 user/assistant/tool 消息
    final_answer: str       # 最终回答（提取后展示）

# --- 3. 工具函数 ---
def search_web(query: str) -> str:
    """联网搜索"""
    print(f"--- 正在搜索: {query} ---")
    response = tavily_client.search(query, max_results=5, search_depth="advanced", time_range="month")
    results = []
    for item in response.get("results", []):
        results.append(f"标题：{item.get('title')}\n内容：{item.get('content')}\n来源：{item.get('url')}")
    return "\n\n".join(results)

def query_database(query_str: str) -> str:
    """执行 SQL 查询"""
    print(f"--- 正在执行SQL: {query_str} ---")
    conn = sqlite3.connect('company.db')
    cursor = conn.cursor()
    try:
        cursor.execute(query_str)
        results = cursor.fetchall()
        return str(results)
    except Exception as e:
        return f"SQL错误: {e}"
    finally:
        conn.close()

# 工具列表 (Function Calling 定义)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "搜索互联网获取最新信息。当需要实时数据、新闻或未知事实时使用。",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_database",
            "description": "查询公司员工数据库，输入为标准的 SQL SELECT 语句。",
            "parameters": {"type": "object", "properties": {"query_str": {"type": "string"}}, "required": ["query_str"]}
        }
    }
]

# --- 4. Agent 节点 ---
def call_model(state: AgentState):
    messages = state["messages"]
    # 添加系统提示，引导模型生成更好的搜索词
    if not any(m.get("role") == "system" for m in messages):
        messages = [{"role": "system", "content": "你是一个信息检索专家。当需要搜索时，务必在查询词中加上'2026年'或'最新'等时效性关键词。"}] + messages
    response = openai_client.chat.completions.create(
        model="qwen-plus",
        messages=messages,
        tools=TOOLS,
        tool_choice="auto"
    )
    msg = response.choices[0].message
    new_messages = [msg]  # 只追加 assistant 消息
    return {"messages": new_messages, "final_answer": msg.content if not msg.tool_calls else ""}

def call_tools(state: AgentState):
    """执行工具调用，返回 ToolMessage"""
    last_msg = state["messages"][-1]
    tool_calls = last_msg.tool_calls
    tool_messages = []
    for tc in tool_calls:
        func_name = tc.function.name
        args = json.loads(tc.function.arguments)
        if func_name == "search_web":
            result = search_web(args["query"])
        elif func_name == "query_database":
            result = query_database(args["query_str"])
        else:
            result = f"未知工具: {func_name}"
        tool_messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": result
        })
    return {"messages": tool_messages}

# --- 5. 条件边 ---
def should_continue(state: AgentState) -> Literal["tools", "end"]:
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"
    return "end"

# --- 6. 构建图 ---
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", call_tools)

workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
workflow.add_edge("tools", "agent")          # 工具执行后返回 agent

agent = workflow.compile()

# --- 7. 测试运行 ---
if __name__ == "__main__":
    # 示例问题：需要同时搜索 + 查库
    query = "研发部最高工资的员工是谁？另外请搜索2026年关于AI应用的最新政策或新闻？"
    print("=" * 50)
    print(f"🧠 问题：{query}")
    result = agent.invoke({"messages": [{"role": "user", "content": query}]})
    # 提取最终回答（最后一条 assistant 消息的内容）
    final_msg = result["messages"][-1]
    answer = final_msg.content if hasattr(final_msg, "content") else "未能生成回答"
    print(f"🤖 回答：{answer}")