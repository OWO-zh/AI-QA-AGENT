import os
import json
import yaml
from tavily import TavilyClient
from openai import OpenAI

# 1. 从 config.yaml 读取配置
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# 2. 初始化客户端
client = OpenAI(
    api_key=config["aliyun_api_key"],
    base_url=config["aliyun_base_url"]
)
tavily_client = TavilyClient(api_key=config["tavily_api_key"])

# 3. 定义搜索函数 (供 Agent 调用)
# Tavily 官方文档推荐的 function calling 搜索函数[reference:6]
def tavily_search(query: str, **kwargs):
    """ 使用 Tavily API 搜索网络 """
    print(f"正在调用 Tavily 搜索工具，查询内容: '{query}'...")
    response = tavily_client.search(query, max_results=5)
    return json.dumps(response) # 将搜索结果转换为 JSON 字符串返回

# 4. 在 OpenAI Function Calling 中定义工具
tools = [
    {
        "type": "function",
        "function": {
            "name": "tavily_search",
            "description": "当需要最新信息、实时数据或具体事实时，使用此工具搜索互联网。它返回结构化的搜索结果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要搜索的关键词或自然语言问题",
                    }
                },
                "required": ["query"],
            },
        },
    }
]

# 5. 定义 Agent 运行函数
def run_agent(user_query):
    messages = [{"role": "user", "content": user_query}]

    # 第一轮：让模型决定是否需要搜索
    response = client.chat.completions.create(
        model="qwen-plus",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )

    msg = response.choices[0].message

    # 如果模型决定调用工具
    if msg.tool_calls:
        tool_call = msg.tool_calls[0]
        if tool_call.function.name == "tavily_search":
            # 解析参数并调用搜索函数
            args = json.loads(tool_call.function.arguments)
            search_result = tavily_search(**args)

            # 将工具调用信息和结果添加到消息历史
            messages.append(msg)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": search_result
            })

            # 第二轮：基于搜索结果生成最终回答
            final_response = client.chat.completions.create(
                model="qwen-plus",
                messages=messages
            )
            return final_response.choices[0].message.content, search_result

    return msg.content, None

# 6. 测试运行
if __name__ == "__main__":
    question = "2026年十五五规划中关于AI的最新政策是什么？"
    print("=" * 50)
    print(f"🧠 问题：{question}")
    print("=" * 50)
    answer, _ = run_agent(question)
    print(f"🤖 回答：{answer}")