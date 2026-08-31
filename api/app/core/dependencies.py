"""通用依赖：从 JWT 解析当前用户（数据隔离基础）。"""
import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.security import decode_token
from app.db.postgres import get_session
from app.models.user_model import User
from app.repositories.user_repository import UserRepository

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise BizError("未提供认证令牌", code=1010, status_code=401)
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise BizError("认证令牌无效或已过期", code=1011, status_code=401)
    user = await UserRepository(session).get_by_id(uuid.UUID(payload["sub"]))
    if not user:
        raise BizError("用户不存在", code=1012, status_code=401)
    return user
