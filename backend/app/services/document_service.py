import hashlib
from pathlib import PurePath
from urllib.parse import unquote
from uuid import UUID

# from fastapi import BackgroundTasks, UploadFile
from fastapi import UploadFile
from numpy.random.mtrand import Sequence
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import Document, DocumentChunk, DocumentStatus, IngestionTaskType, IngestionTask
from app.db.repositories.chunk_repo import (
    ChunkStats,
    DocumentChunkRepository,
)
from app.db.repositories.document_repo import DocumentRepository
from app.ingestion.pipeline import ingest_document
from app.services.role_service import _normalize_tags
from app.storage.file_service import FileService, get_file_service

from app.db.repositories.ingestion_task_repo import IngestionTaskRepository
from app.ingestion.tasks import ingest_document_task, reindex_document_task

# 受支持的 MIME 类型。
_ACCEPTED_MIME_TYPES: dict[str, str] = {
"application/pdf": ".pdf",
"application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
"text/markdown": ".md",
"text/x-markdown": ".md",
"text/html": ".html",
"application/xhtml+xml": ".html",
}

_ACCEPTED_SUFFIXES: dict[str, str] = {
".pdf": "application/pdf",
".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
".md": "text/markdown",
".markdown": "text/markdown",
".html": "text/html",
".htm": "text/html",
}

# 对上传的文件做校验
def _resolve_mime_and_suffix(file: UploadFile) -> tuple[str, str]:
    """根据上传文件file的content_type和拓展名一起判定上传的文件
    浏览器上传 .md 时常给 application/octet-stream，所以扩展名优先级更高
    """
    suffix = PurePath(file.filename or "").suffix.lower()
    if suffix in _ACCEPTED_SUFFIXES:
        return _ACCEPTED_SUFFIXES[suffix], suffix

    mime = file.content_type or ""
    if mime in _ACCEPTED_MIME_TYPES:
        return mime, _ACCEPTED_MIME_TYPES[mime]

    raise ValidationError(
        f"不支持的文件类型： {file.filename} ({mime or '未知'})。当前仅支持PDF、DOCX、Markdown、HTML"

    )

# 删除允许的状态： 在ready，failed， uploading 状态下的数据才允许可以删除
# parsing和indexing状态不允许删除，这时候正在写入数据，创建和删除会冲突
_DELETABLE_STATUSES = frozenset(
    {DocumentStatus.READY, DocumentStatus.FAILED, DocumentStatus.UPLOADING}
)


logger = get_logger(__name__)



# 通过给Document的管理方法添加上permission_tags
# 实现有相关权限的用户才能访问
class DocumentService:
    def __init__(self, session: AsyncSession, file_service: FileService | None = None) -> None:
        self.session = session
        self.repo = DocumentRepository(session)
        self.chunk_repo = DocumentChunkRepository(session)
        self.task_repo = IngestionTaskRepository(session)
        self.file_service = file_service or get_file_service()


    async def upload(
            self,
            file: UploadFile,
            #background_tasks: BackgroundTasks,
            *,
            create_by: UUID | None = None,
            permission_tags: Sequence[str] | None = None,
    ) -> Document:
        """上传文件操作
        1.MIME / 大小检验
        2.计算sha246(content)作为file_hash
        3.用file_hash查现有记录，命中直接返回，实现幂等
        4.上传到COS
        5.存入documents表
        6.commit后再度后台任务，因为后台任务用的是独立session，必须等当前事务commit后才能查到这条记录
        """
        # 对文件类型进行校验
        mime_type, suffix = _resolve_mime_and_suffix(file)
        # 获取文件内容
        content = await file.read()
        # 设置上床文件大小上限
        max_bytes = settings.upload_max_size_mb * 1024 * 1024
        # 对文件内容做校验
        if len(content) == 0:
            raise ValidationError("上床文件为空")
        if len(content) > max_bytes:
            raise ValidationError(f"文件超过 {settings.upload_max_size_mb} MB上限")

        # 哈希化
        file_hash = hashlib.sha256(content).hexdigest()

        # 判断上传的文件是否在数据库内已经存在
        existing = await self.repo.get_by_hash(file_hash)
        if existing is not None:
            # 已经存在就返回存在的文件，不存在就继续操作
            logger.info(f"file_hash hit , reuse document： %s", existing.id)
            return existing

        # 上传到cos，返回key
        object_key = await self.file_service.upload(
            content=content,
            file_hash=file_hash,
            mime_type=mime_type,
            suffix=suffix,
        )

        # 构造文件
        # 前端会用 encodeURIComponent 把中文文件名转成纯 ASCII 避免 multipart 解码乱码；
        # 这里反向 unquote 还原；非 ASCII 时 unquote 是 no-op。
        raw_filename = file.filename or f"{file_hash}{suffix}"
        name = unquote(raw_filename)
        document = Document(
            name=name,
            file_hash=file_hash,
            mime_type=mime_type,
            size=len(content),
            storage_provider="cos",
            cos_bucket=self.file_service.bucket,
            cos_object_key=object_key,
            cos_region=self.file_service.region,
            status=DocumentStatus.UPLOADING,
            permission_tags=_normalize_tags(permission_tags), #F
            created_by=create_by,
        )
        # 操作数据库，文件增加
        await self.repo.add(document)
        task = await self.task_repo.create(document.id, IngestionTaskType.INGEST)
        # 提交
        await self.session.commit()
        #刷新
        await self.session.refresh(document)

        # background_tasks.add_task(ingest_document, document.id)

        # commit 之后 Celery worker 用独立 session 才能查到刚落库的 document / task
        ingest_document_task.delay(str(document.id), str(task.id))

        return document


    async def update_permission_tags(
            self,
            document_id: UUID,
            tags: Sequence[str] | None = None,
    ) ->Document:
        """admin 修改文档可见性标签。"""
        doc = await self.repo.get_by_id(document_id)
        if doc is None:
            raise NotFoundError("文档不存在")
        doc.permission_tags = _normalize_tags(tags)
        await self.session.commit()
        await self.session.refresh(doc)
        return doc


    async def get(self, document_id: UUID, * , permission_tags: list[str] | None = None,) -> Document:
        """获取文档"""
        doc = await self.repo.get_by_id(document_id, permission_tags=permission_tags)
        if doc is None:
            raise NotFoundError("文档不存在")
        return doc

    async def list_documents(
            self,
            page: int,
            page_size: int,
            *,
            status: DocumentStatus | None = None,
            permission_tags: list[str] | None = None
    ) -> tuple[list[Document], int]:
        """获取文档列表"""
        return await self.repo.list_paginated(
            page, page_size, status=status, permission_tags=permission_tags
        )


    async def delete(self, document_id: UUID) -> None:
        """删除文档
        先删除DB行再删COS object，COS删除失败打waring
        避免出现DB还在 用户以为删了
        """
        # 校验文档是否存在，是否处于可删除状态
        doc = await self.repo.get_by_id(document_id)
        if doc is None:
            raise NotFoundError("文档不存在")

        if doc.status not in _DELETABLE_STATUSES:
            raise ValidationError("文档处理中，请等待完成后或失败后再删除")

        object_key = doc.cos_object_key
        await self.repo.delete(doc)
        await self.session.commit()
        await self.file_service.delete(object_key)
        logger.info("document delete: id=%s", document_id)

    async def retry(self, document_id: UUID) -> Document:
        """若是文件传输失败failed，则重新触发ingest"""
        doc = await self.repo.get_by_id(document_id)
        if doc is None:
            raise NotFoundError("文件不存在")
        if doc.status != DocumentStatus.FAILED:
            raise ValidationError("只有传输失败的文件支持重试")

        await self.chunk_repo.delete_by_document(document_id)
        doc.status = DocumentStatus.UPLOADING
        doc.error_message = None
        task = await self.task_repo.create(doc.id, IngestionTaskType.INGEST)
        await self.session.commit()
        await self.session.refresh(doc)


        # background_tasks.add_task(ingest_document, doc.id)
        # 把任务交给celery执行
        ingest_document_task.delay(str(document_id), str(task.id))
        logger.info("document retry schedule：id=%s", document_id)
        return doc

    async def list_chunks(
            self,
            document_id: UUID,
            page: int,
            page_size: int,
            *, permission_tags: list[str] | None = None
    ) -> tuple[list[DocumentChunk], int, ChunkStats | None]:
        """获取多个我chunk"""

        await self.get(document_id, permission_tags=permission_tags)
        # 根据id获取对应文档的chunk
        items, total = await self.chunk_repo.list_paginated_by_document(
            document_id, page, page_size
        )
        # 查看当前chunk的状态
        status = await self.chunk_repo.get_stats(document_id)
        return items, total, status

    async def get_chunk(self, document_id: UUID, chunk_id: UUID, * , permission_tags: list[str] | None = None)-> DocumentChunk:
        """获取单个chunk"""
        # 双重校验：先确保用户能看到 document，再校验 chunk 归属
        await self.get(document_id, permission_tags=permission_tags)
        chunk = await self.chunk_repo.get_by_document(document_id, chunk_id)
        if chunk is None:
            raise NotFoundError("Chunk不存在")
        return chunk

    from app.ingestion.tasks import reindex_document_task

    async def reindex(
            self,
            document_id: UUID,
            file: UploadFile,
    ) -> Document:
        """用新文件替换原文档并触发增量重建。

        - 只允许 READY / FAILED 状态触发，避免与正在进行的 ingest 抢资源
        - 文件 MIME 必须与原文档一致：避免「PDF 文档被 Markdown 覆盖」造成的
          预览 / 下载链路状态混乱
        - 新文件覆盖到 COS 的同一个 object_key，version+1 由 worker 在 reindex
          成功后才提交，避免失败的话用户列表里看到版本号但内容没变
        """
        doc = await self.repo.get_by_id(document_id)
        if doc is None:
            raise NotFoundError("文档不存在")
        if doc.status not in {DocumentStatus.READY, DocumentStatus.FAILED}:
            raise ValidationError("文档处理中，请等待完成或者失败后再重新索引")

        mime_type, suffix = _resolve_mime_and_suffix(file)   # 检验文档
        if mime_type != doc.mime_type:
            raise ValidationError(f"新版本文件类型与原文档一致（当前为 {doc.mime_type} ）")

        # 读取文件
        content = await file.read()
        max_bytes = settings.upload_max_size_mb * 1024 * 1024
        if len(content) == 0:
            raise ValidationError("上传文件为空")
        if len(content) > max_bytes:
            raise ValidationError(f"文件超过 {settings.upload_max_size_mb} MB上限")

        new_hash = hashlib.sha256(content).hexdigest()
        if new_hash == doc.file_hash:
            # 内容完全一致没有重建必要，避免学员误操作浪费 embedding 配额
            raise ValidationError("文件内容与现有版本一致， 无需重新索引")

        # 文件上传
        new_object_key = await self.file_service.upload(
            content=content,
            file_hash=new_hash,
            suffix=suffix,
            mime_type=mime_type,
        )

        doc.file_hash = new_hash
        doc.size = len(content)
        doc.cos_object_key = new_object_key
        doc.cos_bucket = self.file_service.bucket
        doc.cos_region = self.file_service.region
        doc.status = DocumentStatus.PARSING
        doc.error_message = None
        if file.filename:
            doc.name = file.filename

        # 异步任务创建
        task = await self.task_repo.create(doc.id, IngestionTaskType.REINDEX)
        await self.session.commit()
        await self.session.refresh(doc)

        # 重索引任务启动
        reindex_document_task.delay(str(document_id), str(task.id))
        logger.info("document reindex scheduled: id=%s", document_id)
        return doc



    async def get_latest_task(self, document_id: UUID) -> IngestionTask | None:
        return await self.task_repo.get_latest_by_document(document_id)















