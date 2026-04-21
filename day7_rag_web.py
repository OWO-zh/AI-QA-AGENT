import streamlit as st
import os
import tempfile
import yaml
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from openai import OpenAI

# 1. 从 config.yaml 读取配置
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

st.set_page_config(page_title="PDF智能问答", page_icon="📚")
st.title("📚 PDF 智能问答系统")

# 2. 初始化
if "vector_store" not in st.session_state:
    st.session_state.vector_store = None
if "messages" not in st.session_state:
    st.session_state.messages = []

# 3.侧边栏：上传 PDF
with st.sidebar:
    st.header("📁 上传文档")
    uploaded_file = st.file_uploader("选择 PDF 文件", type="pdf")

    if uploaded_file and st.button("开始处理"):
        with st.spinner("正在处理 PDF..."):
            # 保存临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name

            # 加载并处理
            loader = PyPDFLoader(tmp_path)
            docs = loader.load()
            splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
            chunks = splitter.split_documents(docs)

            embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': True}
            )
            st.session_state.vector_store = FAISS.from_documents(chunks, embeddings)

            os.unlink(tmp_path)  # 删除临时文件

        st.success(f"✅ 处理完成！共生成 {len(chunks)} 个文本块")
        st.session_state.messages = []  # 清空对话历史

# 4.主界面：聊天
client = OpenAI(
    api_key=config["aliyun_api_key"],
    base_url=config["aliyun_base_url"]
)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("输入你的问题"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        if st.session_state.vector_store is None:
            reply = "请先上传 PDF 文件"
        else:
            # RAG 检索
            docs = st.session_state.vector_store.similarity_search(prompt, k=3)
            context = "\n\n".join([d.page_content for d in docs])

            full_prompt = f"""根据以下资料回答问题。如果资料中没有答案，请回答"根据现有资料暂时无法回答"。

资料:
{context}

问题: {prompt}

回答: """

            response = client.chat.completions.create(
                model="qwen-plus",
                messages=[{"role": "user", "content": full_prompt}],
                stream=False
            )
            reply = response.choices[0].message.content

        st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})