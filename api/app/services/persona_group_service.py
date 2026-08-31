"""角色卡组（场景）业务服务：CRUD + 内置模板。

卡组把一组角色卡打包为可复用场景。成员引用 agent_personas.id；
内置场景一键添加 = 创建成员角色（in_group_only）+ 建卡组。
"""
# 本类有名为 list 的方法，会遮蔽内置 list，使类体内 `-> list[dict]` 注解报错；
# 用 future 注解延迟求值规避（同 skill_service / agent_persona_service）。
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.logging import get_logger
from app.core.storage import get_storage
from app.models.agent_persona_model import AgentPersona
from app.models.persona_group_model import PersonaGroup
from app.repositories.agent_persona_repository import AgentPersonaRepository
from app.repositories.persona_group_repository import PersonaGroupRepository
from app.schemas.persona_group_schema import PersonaGroupCreate, PersonaGroupUpdate

logger = get_logger(__name__)

MAX_GROUPS = 50
MAX_PERSONAS = 100


class PersonaGroupService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = PersonaGroupRepository(session)
        self.persona_repo = AgentPersonaRepository(session)

    async def list(self, user_id: uuid.UUID) -> list[PersonaGroup]:
        return await self.repo.list_by_user(user_id)

    async def _get_or_404(
        self, user_id: uuid.UUID, group_id: uuid.UUID
    ) -> PersonaGroup:
        group = await self.repo.get(user_id, group_id)
        if group is None:
            raise BizError("角色卡组不存在", code=4045, status_code=404)
        return group

    async def create(
        self, user_id: uuid.UUID, body: PersonaGroupCreate
    ) -> PersonaGroup:
        if await self.repo.count(user_id) >= MAX_GROUPS:
            raise BizError(f"卡组数量已达上限（{MAX_GROUPS}）", code=4046)
        # 校验成员角色都归属当前用户
        for pid in body.member_persona_ids:
            if await self.persona_repo.get(user_id, pid) is None:
                raise BizError("选择的角色不存在", code=4047, status_code=404)
        group = PersonaGroup(
            user_id=user_id,
            name=body.name.strip(),
            description=body.description or "",
            icon=body.icon or "",
            member_persona_ids=[str(i) for i in body.member_persona_ids],
        )
        created = await self.repo.add(group)
        logger.info("创建卡组: user=%s group=%s name=%s", user_id, created.id, created.name)
        return created

    async def update(
        self, user_id: uuid.UUID, group_id: uuid.UUID, body: PersonaGroupUpdate
    ) -> PersonaGroup:
        group = await self._get_or_404(user_id, group_id)
        fields = body.model_dump(exclude_unset=True)
        if "name" in fields and fields["name"] is not None:
            group.name = fields["name"].strip()
        if "description" in fields and fields["description"] is not None:
            group.description = fields["description"]
        if "icon" in fields and fields["icon"] is not None:
            group.icon = fields["icon"]
        if "member_persona_ids" in fields and fields["member_persona_ids"] is not None:
            for pid in fields["member_persona_ids"]:
                if await self.persona_repo.get(user_id, pid) is None:
                    raise BizError("选择的角色不存在", code=4047, status_code=404)
            group.member_persona_ids = [str(i) for i in fields["member_persona_ids"]]
        return await self.repo.save(group)

    async def delete(self, user_id: uuid.UUID, group_id: uuid.UUID) -> None:
        """删卡组，不删成员角色（成员是独立角色卡，可能被别处使用）。"""
        group = await self._get_or_404(user_id, group_id)
        await self.repo.delete(group)
        logger.info("删除卡组: user=%s group=%s", user_id, group_id)

    @staticmethod
    def list_builtins() -> list[dict]:
        """内置卡组模板列表（供前端「一键添加」前展示，不含完整 prompt）。"""
        from app.services.persona_scenario_builtins import SCENARIOS

        return [
            {
                "key": s["key"],
                "name": s["name"],
                "description": s["description"],
                "icon": s["icon"],
                "members": [{"name": m["name"]} for m in s["members"]],
            }
            for s in SCENARIOS
        ]

    async def add_builtin(self, user_id: uuid.UUID, key: str) -> PersonaGroup:
        """一键添加内置场景卡组：创建成员角色（in_group_only）+ 建卡组。"""
        from app.services.persona_scenario_builtins import get_scenario

        scenario = get_scenario(key)
        if scenario is None:
            raise BizError("场景模板不存在", code=4049, status_code=404)
        if await self.repo.count(user_id) >= MAX_GROUPS:
            raise BizError(f"卡组数量已达上限（{MAX_GROUPS}）", code=4046)
        members = scenario["members"]
        if await self.persona_repo.count(user_id) + len(members) > MAX_PERSONAS:
            raise BizError(f"角色数量将超出上限（{MAX_PERSONAS}）", code=4041)

        member_ids: list[str] = []
        for m in members:
            persona = AgentPersona(
                user_id=user_id,
                name=m["name"].strip(),
                system_prompt=m.get("system_prompt", ""),
                temperature=m.get("temperature", 0.7),
                in_group_only=True,  # 场景成员只在卡组里展示，不污染「单个角色」
            )
            saved = await self.persona_repo.add(persona)
            member_ids.append(str(saved.id))

        group = PersonaGroup(
            user_id=user_id,
            name=scenario["name"],
            description=scenario["description"],
            icon=scenario["icon"],
            member_persona_ids=member_ids,
            is_builtin=True,
        )
        created = await self.repo.add(group)
        logger.info(
            "添加内置卡组: user=%s key=%s group=%s 成员=%d",
            user_id, key, created.id, len(member_ids),
        )
        return created

    async def to_out_dict(self, group: PersonaGroup) -> dict:
        """卡组出参：解析成员为 {id, name, avatar_url} 供前端宫格头像展示。"""
        members: list[dict] = []
        storage = get_storage()
        for pid in group.member_persona_ids or []:
            try:
                persona = await self.persona_repo.get(group.user_id, uuid.UUID(pid))
            except (ValueError, TypeError):
                persona = None
            if persona is None:
                continue
            avatar_url = None
            if persona.avatar_key:
                try:
                    avatar_url = storage.get_url(persona.avatar_key)
                except Exception as e:
                    logger.warning("卡组成员头像 url 失败: %s", e)
            members.append(
                {
                    "id": str(persona.id),
                    "name": persona.name,
                    "avatar_url": avatar_url,
                }
            )
        return {
            "id": str(group.id),
            "name": group.name,
            "description": group.description,
            "icon": group.icon,
            "member_persona_ids": [str(i) for i in (group.member_persona_ids or [])],
            "members": members,
            "is_builtin": group.is_builtin,
        }
