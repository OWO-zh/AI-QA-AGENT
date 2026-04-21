from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

pdf_path = "./15data/15th_plan.pdf"

# 加载PDF
loader = PyPDFLoader(pdf_path)
documents = loader.load()

# 切分文本
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000,chunk_overlap=100)
chunks = text_splitter.split_documents(documents)
print(f"共{len(chunks)}个文本块")

#向量化（使用本地Embedding模型）
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True}
)

#存入FAISS向量数据库
vector_store = FAISS.from_documents(chunks, embeddings)
print("向量库构建完成!")

#保存到本地（下次可直接加载，不用重新处理PDF）
vector_store.save_local("./faiss_index")
print("向量库已保存到 ./faiss_index")