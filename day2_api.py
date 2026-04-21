import yaml
from openai import OpenAI

# 从 config.yaml 读取配置
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# 替换成API Key
client = OpenAI(
    api_key=config["aliyun_api_key"],
    base_url=config["aliyun_base_url"]
)

# 发送请求
response = client.chat.completions.create(
    model="qwen-plus",
    messages=[
        {"role": "user","content": "用一句话介绍十五五规划"}
    ]
)

# 打印回复
print(response.choices[0].message.content)