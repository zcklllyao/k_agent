"""MemoryCorrection 仓储 —— PostgreSQL 端,人类反馈纠错记录的 CRUD。

主要被 MemoryService 调用,落用户对实体的 confirm / correct / delete 三类操作。
"""
import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory_correction_model import MemoryCorrection


class MemoryCorrectionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(
        self,
        *,
        user_id: uuid.UUID,
        entity_id: str,
        action: str,
        before: dict,
        after: dict | None = None,
        reason: str | None = None,
        source_dialogue_id: str | None = None,
    ) -> MemoryCorrection:
        """记录一条用户纠错。失败 raise(被 service 包 try/except 不阻断业务)。"""
        rec = MemoryCorrection(
            user_id=user_id,
            entity_id=entity_id,
            action=action,
            before=before or {},
            after=after,
            reason=reason,
            source_dialogue_id=source_dialogue_id,
        )
        self.session.add(rec)
        await self.session.commit()
        await self.session.refresh(rec)
        return rec

    async def list_recent(
        self, user_id: uuid.UUID, limit: int = 50
    ) -> list[MemoryCorrection]:
        """近 N 条纠错记录(给后续 self-improvement loop 消费 / 前端审计用)。"""
        stmt = (
            select(MemoryCorrection)
            .where(MemoryCorrection.user_id == user_id)
            .order_by(desc(MemoryCorrection.created_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_action(self, user_id: uuid.UUID) -> dict[str, int]:
        """各 action 累计计数(给全景统计用)。"""
        from sqlalchemy import func

        stmt = (
            select(MemoryCorrection.action, func.count())
            .where(MemoryCorrection.user_id == user_id)
            .group_by(MemoryCorrection.action)
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}
