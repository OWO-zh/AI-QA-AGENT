import json
import yaml
from typing import TypedDict
from langgraph.graph import StateGraph, END
from tavily import TavilyClient
from openai import OpenAI

# 1. 从 config.yaml 读取配置
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# 2.初始化客户端
openai_client = OpenAI(
    api_key=config["aliyun_api_key"],
    base_url=config["aliyun_base_url"]
)
tavily_client = TavilyClient(api_key=config["tavily_api_key"])

# 3. 定义 LangGraph 状态
class AgentState(TypedDict):
    messages: list
    search_result: str
    final_answer: str

# 4. 定义搜索函数 (供 LangGraph 节点调用)
def search_web(query):
    """ 使用 Tavily 客户端执行搜索 """
    print(f"--- [LangGraph] 正在执行 Tavily 搜索: '{query}' ---")
    response = tavily_client.search(query, max_results=5)
    # 格式化搜索结果以便阅读
    formatted_results = []
    for item in response.get("results", []):
        formatted_results.append(f"标题：{item.get('title')}\n内容：{item.get('content')}\n来源：{item.get('url')}")
    return "\n\n".join(formatted_results)

# 5. LangGraph 节点函数
# 节点 1：决定是否需要搜索
def decide_node(state: AgentState):
    messages = state["messages"]
    tools = [{
        "type": "function",
        "function": {
            "name": "tavily_search",
            "description": "搜索互联网获取最新信息",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        }
    }]

    response = openai_client.chat.completions.create(
        model="qwen-plus",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )

    msg = response.choices[0].message
    if msg.tool_calls:
        # 如果需要搜索，将工具调用信息保存到状态中
        return {"messages": messages, "tool_call": msg.tool_calls[0]}
    else:
        # 如果不需要搜索，直接返回模型的最终答案
        return {"messages": messages, "final_answer": msg.content}

# 节点 2：执行搜索
def search_node(state: AgentState):
    tool_call = state.get("tool_call")
    if tool_call:
        args = json.loads(tool_call.function.arguments)
        result = search_web(args["query"])
        return {"search_result": result, "tool_call": tool_call}
    return {}

# 节点 3：生成最终回答
def answer_node(state: AgentState):
    messages = state["messages"]
    search_result = state.get("search_result", "")
    tool_call = state.get("tool_call")

    if tool_call and search_result:
        # 将搜索工具的结果添加到消息历史中
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": search_result
        })

    response = openai_client.chat.completions.create(
        model="qwen-plus",
        messages=messages
    )
    return {"final_answer": response.choices[0].message.content}

# 条件判断：是否需要搜索
def should_search(state: AgentState):
    if state.get("final_answer"):
        return "end"
    return "search"

# 6. 构建和运行 LangGraph 工作流
workflow = StateGraph(AgentState)

# 添加节点
workflow.add_node("decide", decide_node)
workflow.add_node("search", search_node)
workflow.add_node("answer", answer_node)

# 设置流程
workflow.set_entry_point("decide")
workflow.add_conditional_edges("decide", should_search, {"search": "search", "end": END})
workflow.add_edge("search", "answer")
workflow.add_edge("answer", END)

# 编译 Agent
agent = workflow.compile()

# 7. 测试运行
if __name__ == "__main__":
    user_query = "2026年十五五规划的最新动态"
    print("=" * 50)
    print(f"🧠 [LangGraph Agent] 问题：{user_query}")
    print("=" * 50)
    result = agent.invoke({"messages": [{"role": "user", "content": user_query}]})
    print(f"🤖 回答：{result['final_answer']}")