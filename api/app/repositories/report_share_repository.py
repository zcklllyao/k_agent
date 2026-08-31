"""研究报告分享数据访问层。查询带 user_id 隔离；公开查询按 token。"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_share_model import ReportShare


class ReportShareRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, share: ReportShare) -> ReportShare:
        self.session.add(share)
        await self.session.commit()
        await self.session.refresh(share)
        return share

    async def save(self, share: ReportShare) -> ReportShare:
        await self.session.commit()
        await self.session.refresh(share)
        return share

    async def get(
        self, user_id: uuid.UUID, share_id: uuid.UUID
    ) -> ReportShare | None:
        result = await self.session.execute(
            select(ReportShare).where(
                ReportShare.id == share_id,
                ReportShare.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_active_by_report(
        self, user_id: uuid.UUID, report_id: uuid.UUID
    ) -> ReportShare | None:
        """取该报告已有的有效分享（复用，避免一个报告一堆链接）。"""
        result = await self.session.execute(
            select(ReportShare).where(
                ReportShare.user_id == user_id,
                ReportShare.report_id == report_id,
                ReportShare.is_active.is_(True),
            )
        )
        return result.scalars().first()

    async def get_by_token(self, token: str) -> ReportShare | None:
        result = await self.session.execute(
            select(ReportShare).where(ReportShare.share_token == token)
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID) -> list[ReportShare]:
        result = await self.session.execute(
            select(ReportShare)
            .where(ReportShare.user_id == user_id)
            .order_by(ReportShare.created_at.desc())
        )
        return list(result.scalars().all())
