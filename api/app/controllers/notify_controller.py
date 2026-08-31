"""消息推送渠道路由：渠道 CRUD + 测试推送。"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.notify_schema import NotifyChannelCreate, NotifyChannelUpdate
from app.services.notify_service import NotifyService

router = APIRouter(prefix="/notify-channels", tags=["notify"])


@router.get("")
async def list_channels(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await NotifyService(session).list_channels(user.id))


@router.post("")
async def create_channel(
    body: NotifyChannelCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    ch = await NotifyService(session).create(user.id, body)
    return success(NotifyService.to_dict(ch), "已添加")


@router.put("/{ch_id}")
async def update_channel(
    ch_id: uuid.UUID,
    body: NotifyChannelUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    ch = await NotifyService(session).update(user.id, ch_id, body)
    return success(NotifyService.to_dict(ch), "已保存")


@router.post("/{ch_id}/test")
async def test_channel(
    ch_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await NotifyService(session).test_push(user.id, ch_id)
    return success(message="已发送测试消息，请查收")


@router.delete("/{ch_id}")
async def delete_channel(
    ch_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await NotifyService(session).delete(user.id, ch_id)
    return success(message="已删除")
