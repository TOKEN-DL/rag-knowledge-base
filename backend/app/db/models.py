from enum import Enum


class DocumentStatus(str, Enum):
    """文档生命周期状态

    uploading: 已写入 COS、 入库前
    parsing: Docling解析中
    indexing： 切缝 + 向量化 + 写 chunks 中
    ready: 可被检索
    faild： 任意阶段失败
    """

    UPLOADING = "uploading"
    PARSING = "parsing"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


from datetime import datetime
from uuid import UUID, uuid4

from  pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    DateTime,
    Column,
    Computed,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB,TSVECTOR, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base


class Document(Base):
    """文档表"""
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True),primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    # sha256 十六进制串长度 64；唯一约束保证文件级幂等
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="cos")

    # cos相关
    cos_bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    cos_object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    cos_region: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        String(32), nullable=False, default=DocumentStatus.UPLOADING
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 创建时间更新时间，标配
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )

from sqlalchemy import Index

class DocumentChunk(Base):
    """文档块表"""
    __tablename__ = "document_chunks"

    __table_args__ = (
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index(
            "ix_document_chunks_content_tsv",
            "content_tsv",
            postgresql_using="gin",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
    PGUUID(as_uuid=True),
    ForeignKey("documents.id", ondelete="CASCADE"),
    nullable=False,
    index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 维度由 settings.embedding_dim 控制，迁移时同步固化
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim), nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # md5(content)，第 12 章增量索引依据
    chunk_hash: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    extra_metadata: Mapped[dict] = mapped_column(
    "metadata", JSONB, nullable=False, default=dict
    )
    # 中文全文检索索引列。
    # GENERATED ALWAYS 由 PostgreSQL 根据 content 自动维护，应用层不写、只读。
    # SQLAlchemy 看到 Computed(persisted=True) 会自动从 INSERT/UPDATE 中排除该列。
    content_tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_vector('chinese_zh',content)", persisted=True),
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    document: Mapped[Document] = relationship(back_populates="chunks")

class MessageRole(str, Enum):
    """消息角色。"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Conversation(Base):
    """会话表"""
    __tablename__ = "conversations"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="新对话")
    # user_id 后面引入用户体系时再加列


    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.created_at",
    )



class Message(Base):
    """消息表"""
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    # 关联会话表
    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # model / token / latency 等后续章节扩展信息
    extra_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # 关联
    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    citations: Mapped[list["AnswerCitation"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AnswerCitation.ordinal",
    )



class AnswerCitation(Base):
    """assistant 消息引用的 chunk 快照。
    冗余 page_no / quote 作用：原 chunk 后续可能被增量索引覆盖或文档被删除，
    历史会话仍要能展示当时的引用原文。
    """
    __tablename__ = "answer_citations"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    message_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # prompt 中给 LLM 看到的「片段 N」编号，从 1 开始
    # 持久化下来才能保证刷新后引用顺序与 LLM 当时看到的一致（id 是随机 UUID 不能用来排序）
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    # 原 chunk / 文档可能被删除，所以 ON DELETE SET NULL，保留快照
    document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    chunk_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_name: Mapped[str] = mapped_column(String(512), nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote: Mapped[str] = mapped_column(Text, nullable=False)

    message: Mapped[Message] = relationship(back_populates="citations")
    # 混合检索调试元数据：sources / vector_rank / keyword_rank / *_score / rrf_score
    # 用 JSONB 而非拆列，后续 reranker 章节会继续往里加字段，schema 不稳定时更友好
    retrieval_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)



from sqlalchemy import (
Boolean,
Float,
)

class EvaluationRunStatus(str, Enum):
    """评测 run 生命周期：BackgroundTasks 跑完前 RUNNING；正常结束 COMPLETED；
    主流程异常（不是单条 case 异常）置 FAILED 并写 error_message。"""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"



class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[EvaluationRunStatus] = mapped_column(String(16), nullable=False)
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_relevancy: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    citation_hit_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    refusal_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 首 token 延迟，rerank / 检索链路慢时这里会先涨；拒答 case 不计入
    avg_first_token_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    items: Mapped[list["EvaluationItem"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )




class EvaluationItem(Base):
    """单条 case 的输入快照 + 实际输出 + 指标 + Bad Case 归因。
    输入字段（question / expected_*）从 jsonl 复制过来，不再外键回评测集文件，
    这样评测集 jsonl 后续迭代不会污染历史 run 的对比基线。
    """
    __tablename__ = "evaluation_items"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    case_id: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False)
    expected_document_names: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    expected_keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    should_refuse: Mapped[bool] = mapped_column(Boolean, nullable=False)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    actual_answer: Mapped[str] = mapped_column(Text, nullable=False, default="")


    actual_refused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    retrieved_chunks_meta: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    query_route: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    agent_steps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    verify_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_token_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 指标：RAGAS 4 项任一异常会落 None，前端按缺失隐藏对应单元格
    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_relevancy: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    # citation_hit：should_refuse=True 时 NULL（拒答 case 不参与命中率分母）
    citation_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    refusal_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Bad Case 归因：规则自动初判 + 前端 PATCH 覆盖
    is_bad_case: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bad_case_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bad_case_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped[EvaluationRun] = relationship(back_populates="items")