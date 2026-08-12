"""
rag_utils.py — 混合检索知识库模块
=================================
基于 "向量检索 + 关键词检索 + 重排序" 三级流水线实现文档问答。

检索策略：
    1. FAISS 向量检索（语义相似度）── 召回 Top-10
    2. BM25 关键词检索（精确匹配）── 召回 Top-10
    3. 合并去重 → BGE-Reranker 精排 → 取 Top-K

安全机制：
    - 文件名校验（防路径遍历）
    - 类型白名单（仅 .txt / .pdf）
    - 大小限制（单文件 10MB）
    - 数量限制（最多 5 个）

核心类：
    RAGManager: 懒加载 Embedding + Reranker 模型，提供 add_documents / search 接口
"""

import os
import tempfile
import traceback
import logging
from typing import Tuple

# Hugging Face 国内镜像加速 全局生效
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "300"  # 大模型下载超时设为5分钟

# 统一缓存路径，使用项目目录避免C盘占用
_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hf_cache")
os.environ["HF_HOME"] = _CACHE_DIR
os.environ["TRANSFORMERS_CACHE"] = os.path.join(_CACHE_DIR, "transformers")

import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

# ========== 全局配置常量 ==========
ALLOWED_FILE_TYPES = [".txt", ".pdf"]
MAX_FILE_SIZE_MB = 10
MAX_FILE_COUNT = 5
EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"  # 轻量中文嵌入模型，仅90MB，替代text2vec(400MB)
RERANKER_MODEL = "BAAI/bge-reranker-base"

logger = logging.getLogger("RAGManager")


class RAGManager:
    def __init__(self, reranker_model: str = None):
        """初始化管理器，不加载模型，所有组件采用懒加载。

        参数:
            reranker_model: 可选，自定义重排序模型名。不传则使用默认 BAAI/bge-reranker-base。
                           可通过 config.yaml 或 Streamlit Secrets 中的 reranker_model 配置。
        """
        self.vector_store = None
        self.is_initialized = False
        self._embeddings = None
        self._reranker = None
        self._reranker_model = reranker_model
        self.bm25_index = None
        self.corpus_texts = None
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=100,
            separators=["\n\n", "\n", "。", "！", "？", " ", ""]
        )

    @property
    def embeddings(self):
        """获取 Embedding 模型，若未初始化则自动加载。"""
        if self._embeddings is None:
            self._embeddings = HuggingFaceEmbeddings(
                model_name=EMBEDDING_MODEL,
                model_kwargs={'local_files_only': False}
            )
        return self._embeddings

    @property
    def reranker(self):
        """获取 Reranker 模型，若未初始化则自动加载。

        优先使用外部注入的模型名，未注入则回退到默认常量。
        """
        if self._reranker is None:
            model_name = self._reranker_model or RERANKER_MODEL
            self._reranker = CrossEncoder(model_name, max_length=512)
        return self._reranker

    # ========== 文件安全校验 ==========
    def _validate_file(self, filename: str, file_size: int) -> Tuple[bool, str]:
        """校验上传文件的安全性。

        对单个文件执行三层检查：
            1. 文件名安全：防止路径遍历攻击（如 ../etc/passwd）
            2. 类型白名单：仅允许 .txt 和 .pdf 后缀
            3. 大小限制：不超过 MAX_FILE_SIZE_MB

        参数:
            filename: 原始文件名
            file_size: 文件字节数

        返回:
            (是否通过, 原因说明) 元组
        """
        safe_name = os.path.basename(filename)
        if safe_name != filename:
            return False, "文件名包含非法字符"
        ext = os.path.splitext(safe_name)[1].lower()
        if ext not in ALLOWED_FILE_TYPES:
            return False, f"仅支持 {ALLOWED_FILE_TYPES}"
        if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
            return False, f"文件超过 {MAX_FILE_SIZE_MB}MB"
        return True, "校验通过"

    # ========== 文档添加与索引构建 ==========
    def add_documents(self, uploaded_files: list) -> Tuple[bool, str]:
        """处理上传文件并构建混合索引。

        对上传文件列表执行完整流水线：
            1. 数量检查 → 2. 安全校验 → 3. 写入临时文件
            → 4. 文档加载 → 5. 文本分割 → 6. 清理临时文件
            → 7. 构建 FAISS 向量索引 → 8. 构建 BM25 关键词索引

        参数:
            uploaded_files: Streamlit UploadedFile 对象列表

        返回:
            (是否成功, 结果说明) 元组
        """
        # 1. 文件数量检查
        if len(uploaded_files) > MAX_FILE_COUNT:
            return False, f"最多上传 {MAX_FILE_COUNT} 个文件"

        all_docs = []
        fail_msg_list = []  # 收集解析失败的文件提示，最后统一返回

        for file_obj in uploaded_files:
            # 2. 单个文件安全校验
            is_safe, msg = self._validate_file(file_obj.name, file_obj.size)
            if not is_safe:
                return False, f"{file_obj.name} 校验失败: {msg}"

            suffix = os.path.splitext(file_obj.name)[1]
            tmp_path = None  # 避免 finally 块中 NameError
            try:
                # 3. 将上传文件内容写入临时文件，因为 loader 需要文件路径
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(file_obj.getvalue())
                    tmp_path = tmp.name

                loader = PyPDFLoader(tmp_path) if suffix.lower() == ".pdf" else TextLoader(tmp_path, encoding="utf-8")
                docs = loader.load()
                # 4. 为每个文档块标注来源文件名
                for doc in docs:
                    doc.metadata["source"] = file_obj.name

                # 5. 文本分割
                split_docs = self.text_splitter.split_documents(docs)
                all_docs.extend(split_docs)
                logger.info(f"文件 {file_obj.name} 解析成功，新增 {len(split_docs)} 个分片")

            except Exception as e:
                # 捕获单个文件所有异常：加密PDF、损坏PDF、编码错误、IO错误等
                err_info = f"{file_obj.name} 解析失败（疑似加密/损坏文件）：{str(e)}"
                logger.error(err_info)
                fail_msg_list.append(err_info)
                continue  # 跳过当前坏文件，继续循环下一个
            finally:
                # 6. 清理临时文件
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        # 循环结束后判断结果
        if not all_docs:
            err_tip = "所有文件均未提取到有效文本"
            if fail_msg_list:
                err_tip += "\n" + "\n".join(fail_msg_list)
            return False, err_tip

        # 7. 构建 FAISS 向量库（基于 Embedding 向量）
        self.vector_store = FAISS.from_documents(all_docs, self.embeddings)
        # 8. 构建 BM25 关键词索引
        self.corpus_texts = [doc.page_content for doc in all_docs]
        tokenized_corpus = [text.split() for text in self.corpus_texts]
        self.bm25_index = BM25Okapi(tokenized_corpus)
        self.is_initialized = True

        # 拼接最终返回信息（附带失败文件提醒）
        success_tip = f"知识库构建完成，共 {len(all_docs)} 个文本块（向量 + BM25 双索引）"
        if fail_msg_list:
            success_tip += "\n⚠️ 部分文件跳过：\n" + "\n".join(fail_msg_list)

        logger.info(success_tip)
        return True, success_tip

    # ========== 混合检索核心 ==========
    def _hybrid_retrieve(self, query: str, top_k: int = 3) -> list:
        """混合检索核心：向量检索 + BM25 关键词检索 + Reranker 精排。

        流程：
            1. FAISS 向量检索召回 10 个候选
            2. BM25 关键词检索召回 10 个候选
            3. 文本去重合并
            4. BGE-Reranker 计算相关性分数，降序取 top_k

        参数:
            query: 用户查询文本
            top_k: 最终返回的文本块数量

        返回:
            按相关性降序排列的文本块列表，无结果时返回空列表
        """
        if not self.vector_store or not self.bm25_index:
            return []

        # 向量检索
        vector_docs = self.vector_store.similarity_search(query, k=10)
        vector_texts = [doc.page_content for doc in vector_docs]

        # BM25 关键词检索
        tokenized_query = query.split()
        bm25_top_texts = self.bm25_index.get_top_n(tokenized_query, self.corpus_texts, n=10)

        # 合并去重（用文本内容去重，保证同一个文本块只出现一次）
        seen = set()
        candidates = []
        for text in vector_texts + bm25_top_texts:
            if text not in seen:
                seen.add(text)
                candidates.append(text)

        if not candidates:
            return []

        # 重排序：计算每个候选与 query 的相关性分数
        reranker = self.reranker
        pairs = [[query, cand] for cand in candidates]
        scores = reranker.predict(pairs)
        # 按分数降序排列，取 top_k
        sorted_indices = np.argsort(scores)[::-1]
        top_indices = sorted_indices[:top_k]
        return [candidates[i] for i in top_indices]

    # ========== 对外检索接口 ==========
    def search(self, query: str, top_k: int = 3) -> str:
        """混合检索 + 来源多样性，带完整异常报告。

        在混合检索基础上增加：
            - 来源多样性选择：优先让结果覆盖不同文档
            - 来源追溯：每个文本块标注所属文档名

        参数:
            query: 用户查询文本
            top_k: 最终返回的文本块数量

        返回:
            格式化后的检索结果，含序号、来源和内容
        """
        if not self.is_initialized:
            return "知识库未初始化，请先上传文档。"

        # 1. 先召回更多的候选（top_k * 3），为后续来源多样性和筛选留空间
        try:
            candidates = self._hybrid_retrieve(query, top_k=top_k * 3)
        except Exception as e:
            logger.error(f"混合检索异常: {type(e).__name__} - {str(e)}")
            traceback.print_exc()
            return f"知识库检索异常（混合检索阶段）: {type(e).__name__} - {str(e)}"

        if not candidates:
            return "未检索到相关内容。"

        # 2. 为每个候选文本块匹配其来源文档名
        chunk_sources = []
        for chunk_text in candidates:
            if not chunk_text or not chunk_text.strip():
                continue
            source = "知识库文档"
            try:
                # 通过向量库反向查找最相似的文档，获取其 metadata 中的 source
                if self.vector_store:
                    matched = self.vector_store.similarity_search(chunk_text, k=1)
                    if matched:
                        source = matched[0].metadata.get("source", "知识库文档")
            except Exception as e:
                logger.error(f"来源匹配异常: {type(e).__name__} - {str(e)}")
            chunk_sources.append((chunk_text, source))

        if not chunk_sources:
            return "未检索到有效内容。"

        # 3. 来源多样性选择：尽量让最终结果覆盖不同文档
        selected = []
        seen_sources = set()
        for chunk, src in chunk_sources:
            if src not in seen_sources:
                selected.append((chunk, src))
                seen_sources.add(src)
            if len(selected) == top_k:
                break
        # 如果多样性选择后还不够 top_k，再按原始顺序补足
        if len(selected) < top_k:
            for chunk, src in chunk_sources:
                if (chunk, src) not in selected:
                    selected.append((chunk, src))
                if len(selected) == top_k:
                    break

        # 4. 格式化输出，包含序号、来源和内容
        parts = []
        for idx, (chunk_text, source) in enumerate(selected, 1):
            parts.append(f"[{idx}] 来源：{source}\n    内容：{chunk_text}")
        return "\n\n".join(parts)
