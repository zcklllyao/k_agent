"""角色卡组（场景）路由：CRUD + 内置模板。"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.persona_group_schema import PersonaGroupCreate, PersonaGroupUpdate
from app.services.persona_group_service import PersonaGroupService

router = APIRouter(prefix="/persona-groups", tags=["persona-group"])


@router.get("")
async def list_groups(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = PersonaGroupService(session)
    items = await service.list(user.id)
    return success([await service.to_out_dict(g) for g in items])


@router.get("/builtins")
async def list_builtin_groups(
    user: User = Depends(get_current_user),
):
    """内置场景卡组模板列表（用于「一键添加」前展示）。"""
    return success(PersonaGroupService.list_builtins())


@router.post("/builtins/{key}")
async def add_builtin_group(
    key: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """把内置场景复制为用户自己的卡组（含创建成员角色）。"""
    service = PersonaGroupService(session)
    group = await service.add_builtin(user.id, key)
    return success(await service.to_out_dict(group), "已添加场景")


@router.post("")
async def create_group(
    body: PersonaGroupCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = PersonaGroupService(session)
    group = await service.create(user.id, body)
    return success(await service.to_out_dict(group), "已创建")


@router.put("/{group_id}")
async def update_group(
    group_id: uuid.UUID,
    body: PersonaGroupUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = PersonaGroupService(session)
    group = await service.update(user.id, group_id, body)
    return success(await service.to_out_dict(group), "已保存")


@router.delete("/{group_id}")
async def delete_group(
    group_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await PersonaGroupService(session).delete(user.id, group_id)
    return success(message="已删除")
