"""对话人格（角色卡）路由：CRUD + 设为当前生效。"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.agent_persona_schema import PersonaCreate, PersonaUpdate
from app.services.agent_persona_service import AgentPersonaService

router = APIRouter(prefix="/personas", tags=["agent"])


@router.get("")
async def list_personas(
    all: bool = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """角色列表。默认只返回「单个角色」；all=true 返回全部（含仅卡组成员）。"""
    service = AgentPersonaService(session)
    items = await service.list(user.id, include_group_only=all)
    return success([service.to_out_dict(p) for p in items])


@router.post("")
async def create_persona(
    body: PersonaCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = AgentPersonaService(session)
    persona = await service.create(user.id, body)
    return success(service.to_out_dict(persona), "已创建")


@router.put("/{persona_id}")
async def update_persona(
    persona_id: uuid.UUID,
    body: PersonaUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = AgentPersonaService(session)
    persona = await service.update(user.id, persona_id, body)
    return success(service.to_out_dict(persona), "已保存")


@router.delete("/{persona_id}")
async def delete_persona(
    persona_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await AgentPersonaService(session).delete(user.id, persona_id)
    return success(message="已删除")


@router.post("/{persona_id}/activate")
async def activate_persona(
    persona_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = AgentPersonaService(session)
    persona = await service.activate(user.id, persona_id)
    return success(service.to_out_dict(persona), "已切换")
