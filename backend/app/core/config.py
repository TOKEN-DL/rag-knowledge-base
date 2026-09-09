"""应用配置：从根目录 .env 读取环境变量并暴露 settings 单例"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

import os

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name : str = "rag-knowledge-base"
    log_level: str = "INFO"

    # 数据库设置

    database_url : str = "postgresql+asyncpg://rag:rag@localhost:5432/rag_kb"

    # COS设置
    cos_secret_id : str = os.getenv("COS_SECRET_ID")
    cos_secret_key : str = os.getenv("COS_SECRET_KEY")
    cos_region: str = "ap-guangzhou"
    cos_bucket : str = os.getenv("COS_BUCKET")

    cors_origins : str = os.getenv("CORS_ORIGINS")

    # ===== Embedding（DashScope OpenAI 兼容协议）=====
    embedding_api_key: str = os.getenv("EMBEDDING_API_KEY")
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_model: str = "text-embedding-v3"
    # 维度需与 alembic 迁移中 Vector(N) 保持一致；改维度需要重建表
    embedding_dim: int = 1024
    embedding_batch_size: int = 10
    # ===== 文档上传与切分 =====
    upload_max_size_mb: int = 50
    chunk_size: int = 600
    chunk_overlap: int = 60

    # ===== Chat 模型（DashScope OpenAI 兼容协议）=====
    # 默认与 embedding 同 base_url
    chat_api_key: str = os.getenv("CHAT_API_KEY")
    chat_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    chat_model: str = "qwen-plus"
    # ===== 检索与问答 =====
    retrieve_top_k: int = 5
    # 检索 Top-K：交给 LLM 的候选 chunk 数量
    retrieval_top_k: int = 5
    # 拒答阈值：cosine similarity（= 1 - cosine_distance）的下限
    # Top-K 中最高分仍低于此值，直接拒答，不调 LLM
    retrieval_min_score: float = 0.6
    # 多轮窗口：load_context 节点取最近多少轮塞进 prompt
    chat_history_window: int = 5

    # ===== Query 优化=====
    # 关掉后 route_query 节点强制走 original，方便对比有/无路由的效果
    query_route_enabled: bool = True
    # Multi-Query 策略生成的子查询数量，过大会增加 embedding 成本
    multi_query_count: int = 3

    # ===== 混合检索 =====
    # 每路（向量 / 关键词）召回数量；设计文档建议候选 20-50
    # 取 20 兼顾召回率与 RRF 融合开销
    retrieval_recall_top_k: int = 20
    # RRF 平滑常数，业界一般用 60；越小越偏向高排名条目
    rrf_k: int = 60

    # ===== Agentic RAG =====
    # 关掉后图退化为单轮检索，作为单轮 vs agent 循环的对比开关
    agent_loop_enabled: bool = True
    # 最大检索轮次（含首轮）。LLM 决策最多触发 max_rounds-1 次再检索，避免循环调用
    agent_max_rounds: int = 3

    # ===== Reranker（DashScope qwen3-rerank，第 8 章）=====
    # 关掉后 rerank 节点直接透传，作为有/无精排的对比开关
    rerank_enabled: bool = True
    # DashScope rerank 端点，不是标准 OpenAI API
    rerank_base_url: str = (
        "https://dashscope.aliyuncs.com/compatible-api/v1/reranks"
    )
    rerank_model: str = "qwen3-rerank"
    # 留空时复用 chat_api_key（同一份 DashScope key，避免重复配置）
    rerank_api_key: str = os.getenv("RERANK_API_KEY")
    # rerank Top1 相关度阈值；低于此值视为"上下文不足"由 judge_context 触发拒答
    # qwen3-rerank 输出 relevance_score ∈ [0, 1]，0.3 是经验值
    rerank_min_score: float = 0.3
    # 请求超时（秒），rerank 是同步调用主链路，超时要短一点避免拖慢回答
    rerank_timeout: float = 8.0
    # ===== 答案校验（第 8 章）=====
    # 关掉后跳过 verify_answer 调用，方便对比有/无引用支撑校验的效果
    verify_answer_enabled: bool = True

    # ===== LangSmith 可观测性 =====
    # 关掉后 @traceable / LangChain 自动 trace 全部降级为 no-op，trace_id 返回 None
    # 开发期不填 LangSmith key 不影响项目正常跑
    langsmith_tracing: bool = True
    langsmith_api_key: str = os.getenv("LANGSMITH_API_KEY")
    langsmith_project: str = "rag-knowledge-base"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    # LangSmith UI 私有 URL 前缀，形如 https://smith.langchain.com/o/{org}/projects/p/{project}
    # 包含 workspace/org 信息所以是私有的，配置后才下发跳转链接给前端
    langsmith_run_url_prefix: str = ""

    # ===== 认证 =====
    # JWT 签名密钥；为空时启动期打 ERROR 警告但不阻断（教学场景，避免学员忘配跑不起来）
    # 生产部署务必改成足够长的随机串
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    # token 默认 24 小时过期
    jwt_expire_minutes: int = 1440
    # 首次启动种子管理员账号；库内已有用户时跳过
    default_admin_username: str = "admin"
    default_admin_password: str = "admin"
    default_admin_display_name: str = "管理员"

    # ===== Redis（语义缓存 / 限流 / Celery broker，第 12 章引入）=====
    # 应用直接客户端，不同 db 索引让 Celery broker / backend 互不干扰
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ===== 语义缓存=====
    semantic_cache_enabled: bool = True
    semantic_cache_ttl_seconds: int = 3600
    # RedisVL 内部用「余弦距离 = 1 - 余弦相似度」做 KNN 查询，转换在 service 层完成
    semantic_cache_min_similarity: float = 0.92
    # ===== 滑动窗口限流=====
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60

    @property
    def observability_enabled(self) -> bool:
        """LangSmith 实际生效条件：开关打开 + key 已配置。任一缺失都视为关闭。"""
        return bool(self.langsmith_tracing and self.langsmith_api_key)



    # 校验COS的配置值是否都正确
    @property
    def cos_configured(self) -> bool:
        return bool(self.cos_secret_id and self.cos_secret_key and self.cos_bucket)

    @property
    def effective_rerank_api_key(self) -> str:
        """rerank_api_key 留空时回落到 chat_api_key，二者本来就是同一份 DashScope key。"""

        return self.rerank_api_key or self.chat_api_key

    # 跨域配置

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)   # 保证全局实例化一次
def get_settings() -> Settings:
    return Settings()





settings = get_settings()