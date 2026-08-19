"""FastAPI 应用入口"""

# torch.compile 在 Windows + 中文区域下加载 mm_grouped 模板时会用 gbk 解码 UTF-8 文件
# 直接抛 UnicodeDecodeError。这里关掉 torch.compile，CPU 场景下用 eager 模式足矣，
# 完全绕开有问题的 _inductor 导入链。
import torch  # noqa: E402

torch._dynamo.config.disable = True
torch._dynamo.config.suppress_errors = True

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.api.error_handlers import register_error_handlers  # noqa: E402
from app.api.routes import health, documents, chat  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.core.observability import configure_observability


def create_app() -> FastAPI:
    configure_logging()
    configure_observability()
    logger = get_logger(__name__)


    app = FastAPI(title=settings.app_name)

    # 跨域配置
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)
    app.include_router(health.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")

    logger.info("app initialized: %s", settings.app_name)
    return app

app = create_app()
