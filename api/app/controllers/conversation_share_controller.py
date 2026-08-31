"""对话分享路由。

- 鉴权路由（router）：创建分享 / 我的分享列表 / 取消分享。
- 公开路由（public_router）：凭 token 查看分享，**不需要登录**。
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.conversation_share_schema import ShareCreateRequest
from app.services.conversation_share_service import ConversationShareService

router = APIRouter(tags=["share"])
public_router = APIRouter(prefix="/public", tags=["share-public"])


@router.post("/conversations/{conversation_id}/share")
async def create_share(
    conversation_id: uuid.UUID,
    body: ShareCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ConversationShareService(session)
    share = await service.create_share(
        user.id, conversation_id, body.expire_days, body.title
    )
    return success(service.share_out(share), "已生成分享链接")


@router.get("/shares")
async def list_shares(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ConversationShareService(session)
    items = await service.list_shares(user.id)
    return success([service.share_out(s) for s in items])


@router.delete("/shares/{share_id}")
async def revoke_share(
    share_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await ConversationShareService(session).revoke(user.id, share_id)
    return success(message="已取消分享")


@public_router.get("/shares/{token}")
async def get_public_share(
    token: str,
    session: AsyncSession = Depends(get_session),
):
    """公开查看分享内容（无需登录）。"""
    data = await ConversationShareService(session).get_public(token)
    return success(data)


@public_router.get("/report-shares/{token}")
async def get_public_report_share(
    token: str,
    session: AsyncSession = Depends(get_session),
):
    """公开查看研究报告分享（无需登录）。"""
    from app.services.report_share_service import ReportShareService

    data = await ReportShareService(session).get_public(token)
    return success(data)
