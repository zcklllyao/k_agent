"""技能（Skill）路由：CRUD + 内置模板列表 + 一键添加。"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.skill_schema import (
    OptimizeSkillPromptRequest,
    SkillCreate,
    SkillUpdate,
)
from app.services.skill_service import SkillService

router = APIRouter(prefix="/skills", tags=["skill"])


@router.get("")
async def list_skills(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = SkillService(session)
    items = await service.list(user.id)
    return success([service.to_out_dict(s) for s in items])


@router.get("/builtins")
async def list_builtin_skills(
    user: User = Depends(get_current_user),
):
    """内置技能模板列表（用于「一键添加」前展示）。"""
    return success(SkillService.list_builtins())


@router.post("")
async def create_skill(
    body: SkillCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = SkillService(session)
    skill = await service.create(user.id, body)
    return success(service.to_out_dict(skill), "已创建")


@router.post("/builtins/{key}")
async def add_builtin_skill(
    key: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """把一个内置模板复制为用户自己的技能。"""
    service = SkillService(session)
    skill = await service.add_builtin(user.id, key)
    return success(service.to_out_dict(skill), "已添加")


@router.post("/optimize-prompt")
async def optimize_skill_prompt(
    body: OptimizeSkillPromptRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """技能任务提示词一键优化（专用元提示词，聚焦任务执行，不写人设）。"""
    service = SkillService(session)
    optimized = await service.optimize_prompt(user.id, body.prompt)
    return success({"optimized": optimized})


@router.put("/{skill_id}")
async def update_skill(
    skill_id: uuid.UUID,
    body: SkillUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = SkillService(session)
    skill = await service.update(user.id, skill_id, body)
    return success(service.to_out_dict(skill), "已保存")


@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await SkillService(session).delete(user.id, skill_id)
    return success(message="已删除")
