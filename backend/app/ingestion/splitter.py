import hashlib


from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings

def _build_splitter() -> RecursiveCharacterTextSplitter:
    """定义切分器，设置好一些默认参数"""
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", "。","!", "?", ";", "，", " ", ""],
        length_function=len,
        is_separator_regex=False,
    )

def split(documents: list[Document]) ->list[Document]:
    """切分操作：输入文档列表，对每个文档进行切缝并补齐chunk级metadata"""
    # 调用文档进行切分成块
    splitter = _build_splitter()
    chunks = splitter.split_documents(documents)

    for index, chunk in enumerate(chunks):
        # chunk_index 用于排序和定位；chunk_hash给后续增量索引比对
        chunk.metadata["chunk_index"] = index
        chunk.metadata["chunk_hash"] = (hashlib.md5(
            chunk.page_content.encode("utf-8"))
            .hexdigest())

    return chunks


