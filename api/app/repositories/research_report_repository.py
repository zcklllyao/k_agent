"""ResearchReport 数据访问层 —— PostgreSQL research_reports 表。所有查询带 user_id 隔离。"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_report_model import ResearchReport


class ResearchReportRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, report: ResearchReport) -> ResearchReport:
        self.session.add(report)
        await self.session.commit()
        await self.session.refresh(report)
        return report

    async def save(self, report: ResearchReport) -> ResearchReport:
        await self.session.commit()
        await self.session.refresh(report)
        return report

    async def get(
        self, user_id: uuid.UUID, report_id: uuid.UUID
    ) -> ResearchReport | None:
        stmt = select(ResearchReport).where(
            ResearchReport.id == report_id, ResearchReport.user_id == user_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, report_id: uuid.UUID) -> ResearchReport | None:
        """后台任务用：仅按 id 取（无 user 过滤，调用方已知归属）。"""
        stmt = select(ResearchReport).where(ResearchReport.id == report_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_paged(
        self, user_id: uuid.UUID, page: int, page_size: int
    ) -> tuple[list[ResearchReport], int]:
        base = select(ResearchReport).where(ResearchReport.user_id == user_id)
        total = await self.session.scalar(
            select(func.count()).select_from(base.subquery())
        )
        result = await self.session.execute(
            base.order_by(ResearchReport.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def list_by_task(
        self, user_id: uuid.UUID, task_id: uuid.UUID, limit: int = 30
    ) -> list[ResearchReport]:
        """某定时任务的运行历史（按时间倒序）。"""
        stmt = (
            select(ResearchReport)
            .where(
                ResearchReport.user_id == user_id,
                ResearchReport.task_id == task_id,
            )
            .order_by(ResearchReport.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_unread_scheduled(
        self, user_id: uuid.UUID, since
    ) -> int:
        """统计「定时任务产出且已完成」、created_at 晚于 since 的报告数（未读红点用）。

        since 为 None 时视为全部未读（用户从未看过简报）。
        """
        stmt = select(func.count()).select_from(ResearchReport).where(
            ResearchReport.user_id == user_id,
            ResearchReport.task_id.isnot(None),
            ResearchReport.status == "done",
        )
        if since is not None:
            stmt = stmt.where(ResearchReport.created_at > since)
        return int(await self.session.scalar(stmt) or 0)

    async def delete(self, report: ResearchReport) -> None:
        await self.session.delete(report)
        await self.session.commit()
