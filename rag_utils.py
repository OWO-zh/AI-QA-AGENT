import os
import tempfile
from typing import List, Tuple
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.document_loaders import PyPDFLoader, TextLoader

# ==================== 安全配置 ====================
ALLOWED_FILE_TYPES = [".txt", ".pdf"]
MAX_FILE_SIZE_MB = 10
MAX_FILE_COUNT = 5
# 中文轻量 Embedding，本地运行，若有 GPU 可换 faster 版本
EMBEDDING_MODEL = "shibing624/text2vec-base-chinese"

class RAGManager:
    """
    会话级 RAG 知识库管理器
    - 每个 Streamlit 会话一个实例，数据隔离
    - 涵盖文件校验、文档加载、分块、向量化、检索
    """

    def __init__(self):
        self.vector_store = None
        self.is_initialized = False
        self.embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
        # 中文优先的分隔符
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=100,
            separators=["\n\n", "\n", "。", "！", "？", " ", ""]
        )

    def _validate_file(self, filename: str, file_size: int) -> Tuple[bool, str]:
        """安全校验：路径穿越、后缀白名单、文件大小"""
        safe_name = os.path.basename(filename)
        if safe_name != filename:
            return False, "文件名包含非法字符"
        ext = os.path.splitext(safe_name)[1].lower()
        if ext not in ALLOWED_FILE_TYPES:
            return False, f"仅支持 {ALLOWED_FILE_TYPES}"
        if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
            return False, f"文件超过 {MAX_FILE_SIZE_MB}MB"
        return True, "校验通过"

    def add_documents(self, uploaded_files: list) -> Tuple[bool, str]:
        """批量上传文件，构建向量库"""
        if len(uploaded_files) > MAX_FILE_COUNT:
            return False, f"最多上传 {MAX_FILE_COUNT} 个文件"

        all_docs = []
        for file_obj in uploaded_files:
            is_safe, msg = self._validate_file(file_obj.name, file_obj.size)
            if not is_safe:
                return False, f"{file_obj.name} 校验失败: {msg}"

            suffix = os.path.splitext(file_obj.name)[1]
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(file_obj.getvalue())
                    tmp_path = tmp.name

                # 选择加载器
                loader = PyPDFLoader(tmp_path) if suffix.lower() == ".pdf" else TextLoader(tmp_path, encoding="utf-8")
                docs = loader.load()

                # 来源标记为用户原文件名，方便检索时溯源
                for doc in docs:
                    doc.metadata["source"] = file_obj.name

                # 分块
                split_docs = self.text_splitter.split_documents(docs)
                all_docs.extend(split_docs)
            except Exception as e:
                return False, f"处理 {file_obj.name} 出错: {str(e)}"
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        if not all_docs:
            return False, "未提取到有效文本"

        self.vector_store = FAISS.from_documents(all_docs, self.embeddings)
        self.is_initialized = True
        return True, f"知识库构建完成，共 {len(all_docs)} 个文本块"

    def search(self, query: str, top_k: int = 3) -> str:
        """相似度检索，返回格式化结果（含来源）"""
        if not self.is_initialized or not self.vector_store:
            return "知识库未初始化，请先上传文档。"

        docs = self.vector_store.similarity_search(query, k=top_k)
        if not docs:
            return "未检索到相关内容。"

        parts = []
        for idx, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "未知文档")
            parts.append(f"[{idx}] 来源：{source}\n    内容：{doc.page_content}")
        return "\n\n".join(parts)