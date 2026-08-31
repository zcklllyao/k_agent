"""对话人格业务服务：CRUD + 设为当前生效。"""
# 本类有名为 list 的方法，会遮蔽内置 list，使类体内 `-> list[dict]` 注解报错；
# 用 future 注解延迟求值规避（与 skill_service 同）。
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.logging import get_logger
from app.core.storage import get_storage
from app.models.agent_persona_model import AgentPersona
from app.repositories.agent_persona_repository import AgentPersonaRepository
from app.schemas.agent_persona_schema import PersonaCreate, PersonaUpdate

logger = get_logger(__name__)

# 单用户人格数量上限，防滥用
MAX_PERSONAS = 200


class AgentPersonaService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AgentPersonaRepository(session)

    async def list(
        self, user_id: uuid.UUID, include_group_only: bool = False
    ) -> list[AgentPersona]:
        items = await self.repo.list_by_user(user_id)
        # 角色列表为空：懒创建一个开箱即用的默认角色（覆盖新/存量用户，无需回填）
        if not items:
            from app.services.persona_scenario_builtins import DEFAULT_PERSONA

            default = AgentPersona(
                user_id=user_id,
                name=DEFAULT_PERSONA["name"],
                system_prompt=DEFAULT_PERSONA["system_prompt"],
                temperature=DEFAULT_PERSONA["temperature"],
                is_active=True,
            )
            await self.repo.add(default)
            items = await self.repo.list_by_user(user_id)
        # 默认只返回「单个角色」（隐藏仅作为卡组成员的角色，保持列表干净）；
        # include_group_only=True 时返回全部（含角色卡组专属成员）
        if not include_group_only:
            items = [p for p in items if not p.in_group_only]
        return items

    async def _get_or_404(
        self, user_id: uuid.UUID, persona_id: uuid.UUID
    ) -> AgentPersona:
        persona = await self.repo.get(user_id, persona_id)
        if persona is None:
            raise BizError("角色不存在", code=4040, status_code=404)
        return persona

    async def create(self, user_id: uuid.UUID, body: PersonaCreate) -> AgentPersona:
        if await self.repo.count(user_id) >= MAX_PERSONAS:
            raise BizError(f"角色数量已达上限（{MAX_PERSONAS}）", code=4041)
        persona = AgentPersona(
            user_id=user_id,
            name=body.name.strip(),
            avatar_key=(body.avatar_key or None),
            system_prompt=body.system_prompt or "",
            temperature=body.temperature,
        )
        # 首个角色自动设为当前生效
        if await self.repo.count(user_id) == 0:
            persona.is_active = True
        created = await self.repo.add(persona)
        logger.info("创建角色: user=%s persona=%s name=%s", user_id, created.id, created.name)
        return created

    async def update(
        self, user_id: uuid.UUID, persona_id: uuid.UUID, body: PersonaUpdate
    ) -> AgentPersona:
        persona = await self._get_or_404(user_id, persona_id)
        fields = body.model_dump(exclude_unset=True)
        if "name" in fields and fields["name"] is not None:
            persona.name = fields["name"].strip()
        if "avatar_key" in fields:
            # 传空串/None 表示移除头像
            persona.avatar_key = fields["avatar_key"] or None
        if "system_prompt" in fields and fields["system_prompt"] is not None:
            persona.system_prompt = fields["system_prompt"]
        if "temperature" in fields and fields["temperature"] is not None:
            persona.temperature = fields["temperature"]
        return await self.repo.save(persona)

    async def delete(self, user_id: uuid.UUID, persona_id: uuid.UUID) -> None:
        persona = await self._get_or_404(user_id, persona_id)
        await self.repo.delete(persona)
        logger.info("删除角色: user=%s persona=%s", user_id, persona_id)

    async def activate(self, user_id: uuid.UUID, persona_id: uuid.UUID) -> AgentPersona:
        """设为当前生效：先把其余置 false，再激活本条（单事务）。"""
        persona = await self._get_or_404(user_id, persona_id)
        await self.repo.deactivate_all(user_id)
        persona.is_active = True
        saved = await self.repo.save(persona)
        logger.info("切换当前角色: user=%s persona=%s", user_id, persona_id)
        return saved

    @staticmethod
    def to_out_dict(persona: AgentPersona) -> dict:
        avatar_url = None
        if persona.avatar_key:
            try:
                avatar_url = get_storage().get_url(persona.avatar_key)
            except Exception as e:  # 取 url 失败不影响列表返回
                logger.warning("角色头像 url 生成失败: key=%s err=%s", persona.avatar_key, e)
        return {
            "id": str(persona.id),
            "name": persona.name,
            "avatar_key": persona.avatar_key,
            "avatar_url": avatar_url,
            "system_prompt": persona.system_prompt,
            "temperature": persona.temperature,
            "is_active": persona.is_active,
        }
