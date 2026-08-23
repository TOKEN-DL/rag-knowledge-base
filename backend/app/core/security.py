from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedError  # 后续补充

# 密码部分

def hash_password(plain: str) -> str:
    """利用bcrypt工具：把密码进行哈希存储"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """确认密码：登录时进行检验"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False

# JWT Token部分

def create_access_token(subject:str) -> str:
    """signed JWT。subject 约定放 user_id 字符串"""
    if not settings.jwt_secret:
        # 启动期已经打过 ERROR；这里再兜一道，避免空 secret 签出"任何人都能伪造"的 token
        raise UnauthorizedError("服务端未配置JWT secret，无法签发token")
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token:str) -> str:
    """返回 token 中 sub 字段（user_id 字符串）；任何失败都转 UnauthorizedError。"""
    if not settings.jwt_secret:
        raise UnauthorizedError("服务端未配置 JWT Secret ")
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("登录已经过期，请重新登录") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("无效访问凭证") from exc

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise UnauthorizedError("无效的访问凭证")
    return subject

