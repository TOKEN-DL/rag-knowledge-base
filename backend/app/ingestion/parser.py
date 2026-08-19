import asyncio
import io
from pathlib import Path

from docling.datamodel.base_models import DocumentStream
from docling.document_converter import DocumentConverter
from langchain_core.documents import Document

from app.core.exceptions import AppException
from app.core.logging import get_logger

logger = get_logger(__name__)

class DocumentParserError(AppException):
    code = "document_parser_error"
    message = "文档解析失败"
    http_status = 400



_converter: DocumentConverter | None = None


def _get_converter() -> DocumentConverter:
    """单例文档转化器，一次调用多次使用"""
    global _converter
    if _converter is None:
        _converter = DocumentConverter()
    return _converter

def _convert_sync(filename: str, content: bytes) -> str:
    """把文本数据转化成markdown文件"""
    source = DocumentStream(name=filename, stream=io.BytesIO(content))
    result = _get_converter().convert(source)
    return result.document.export_to_markdown()

# markdown/纯文本本身就是目标格式，过 Docling 往返会损坏链接与表格
_PASSTHROUGH_SUFFIXES = {".md", ".markdown", ".txt"}

async def parse(filename: str, content: bytes) -> list[Document]:
    """解析并转化成langchain的Document列表"""
    # 解析错误更正
    if Path(filename).suffix.lower() in _PASSTHROUGH_SUFFIXES:
        markdown = content.decode("utf-8", errors="replace")
    else:
        try:
            markdown = await asyncio.to_thread(_convert_sync, filename,  content)
        except Exception as exc:
            logger.exception("docling parser failed %s", filename)
            raise DocumentParserError(f"Docling解析失败：{exc}") from exc

    if not markdown.strip():
        raise DocumentParserError("解析结果为空，文档可能损坏或者不支持")

    return [Document(
        page_content=markdown,
        metadata={"source": filename},
        )
    ]
