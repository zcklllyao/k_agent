"""知识库路由：列表/新建/修改/删除。"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.knowledge_base_schema import (
    ChatEnabledRequest,
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
)
from app.services.knowledge_base_service import KnowledgeBaseService

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge_base"])


@router.get("")
async def list_knowledge_bases(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    items = await KnowledgeBaseService(session).list_kbs(user.id)
    return success(items)


@router.get("/{kb_id}")
async def get_knowledge_base(
    kb_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    kb = await KnowledgeBaseService(session).get_detail(user.id, kb_id)
    return success(kb)


@router.get("/{kb_id}/overview")
async def get_knowledge_base_overview(
    kb_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    overview = await KnowledgeBaseService(session).get_overview(user.id, kb_id)
    return success(overview)


@router.post("/{kb_id}/overview/generate")
async def generate_knowledge_base_overview(
    kb_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    overview = await KnowledgeBaseService(session).generate_overview(user.id, kb_id)
    return success(overview, "总览生成任务已提交")


@router.post("")
async def create_knowledge_base(
    body: KnowledgeBaseCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    kb = await KnowledgeBaseService(session).create(user.id, body)
    return success(kb, "创建成功")


@router.put("/{kb_id}")
async def update_knowledge_base(
    kb_id: uuid.UUID,
    body: KnowledgeBaseUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    kb = await KnowledgeBaseService(session).update(user.id, kb_id, body)
    return success(kb, "更新成功")


@router.put("/{kb_id}/chat-enabled")
async def set_chat_enabled(
    kb_id: uuid.UUID,
    body: ChatEnabledRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    kb = await KnowledgeBaseService(session).set_chat_enabled(
        user.id, kb_id, body.chat_enabled
    )
    return success(kb)


@router.delete("/{kb_id}")
async def delete_knowledge_base(
    kb_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await KnowledgeBaseService(session).delete(user.id, kb_id)
    return success(message="删除成功")
