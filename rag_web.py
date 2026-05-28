import streamlit as st
import os
import tempfile
import yaml 
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from openai import OpenAI
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder   # 替换 FlagEmbedding
import numpy as np

# 1. 从 config.yaml 读取配置
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

st.set_page_config(page_title="PDF智能问答", page_icon="📚")
st.title("📚 PDF 智能问答系统")

# 重排序模型缓存加载（使用 sentence_transformers）
@st.cache_resource
def load_reranker():
    return CrossEncoder('BAAI/bge-reranker-base', max_length=512)

# 2. 初始化
if "vector_store" not in st.session_state:
    st.session_state.vector_store = None
if "messages" not in st.session_state:
    st.session_state.messages = []

# 3. 侧边栏：上传 PDF
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
            # 为混合检索保存 BM25 索引和文本
            all_chunks_text = [chunk.page_content for chunk in chunks]
            tokenized_chunks = [text.split() for text in all_chunks_text]
            st.session_state.bm25 = BM25Okapi(tokenized_chunks)
            st.session_state.all_chunks_text = all_chunks_text

            os.unlink(tmp_path)  # 删除临时文件

        st.success(f"✅ 处理完成！共生成 {len(chunks)} 个文本块")
        st.session_state.messages = []  # 清空对话历史

# 4. 主界面：聊天
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
            # ----- 混合检索 + 重排序 -----
            # 1. 向量检索
            vector_docs = st.session_state.vector_store.similarity_search(prompt, k=10)
            vector_texts = [doc.page_content for doc in vector_docs]

            # 2. BM25 关键词检索
            bm25 = st.session_state.bm25
            all_texts = st.session_state.all_chunks_text
            bm25_texts = bm25.get_top_n(prompt.split(), all_texts, n=10)

            # 3. 合并去重
            candidates = list(set(vector_texts + bm25_texts))

            # 4. 重排序取 Top-3（使用 CrossEncoder）
            reranker = load_reranker()
            pairs = [[prompt, cand] for cand in candidates]
            scores = reranker.predict(pairs)   # 关键修改：predict 替代 compute_score
            top_indices = np.argsort(scores)[::-1][:3]
            top_texts = [candidates[i] for i in top_indices]

            context = "\n\n".join(top_texts)

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