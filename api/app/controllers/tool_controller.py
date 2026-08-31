"""工具配置路由：列出工具 + 启停。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.tool_schema import ToolToggle
from app.services.tool_service import ToolService

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
async def list_tools(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ToolService(session)
    return success(await service.list_tools(user.id))


@router.put("/{tool_key}")
async def toggle_tool(
    tool_key: str,
    body: ToolToggle,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ToolService(session)
    data = await service.set_enabled(user.id, tool_key, body.enabled)
    return success(data, "已保存")
