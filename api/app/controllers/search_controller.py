"""全局搜索路由：联合检索文档/图片/记忆，分组返回。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.services.search_service import SearchService

router = APIRouter(tags=["search"])


@router.get("/search")
async def global_search(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    top_k: int = Query(default=8, ge=1, le=20),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    data = await SearchService(session).search_all(user.id, q, top_k)
    return success(data)
