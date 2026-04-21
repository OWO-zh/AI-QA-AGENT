import streamlit as st
import yaml
from openai import OpenAI

# 从 config.yaml 读取配置
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

st.set_page_config(page_title="AI助手", page_icon="🤖")
st.title("🤖 十五五规划问答助手")

# 初始化客户端
client = OpenAI(
    api_key=config["aliyun_api_key"],
    base_url=config["aliyun_base_url"]
)

# 初始化聊天历史
if "messages" not in st.session_state:
    st.session_state.messages = []

# 显示历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 用户输入
if prompt := st.chat_input("请输入你的问题"):
    # 1. 先添加用户消息到历史
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. 调用 API
    with st.chat_message("assistant"):
        with st.spinner("思考中..."):
            response = client.chat.completions.create(
                model="qwen-plus",
                messages=st.session_state.messages
            )
            reply = response.choices[0].message.content
            st.markdown(reply)

    # 3. 将助手回复存入历史
    st.session_state.messages.append({"role": "assistant", "content": reply})