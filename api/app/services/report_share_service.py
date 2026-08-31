"""研究报告分享业务服务：创建（快照冻结）/ 列表 / 取消 / 公开查看。

快照式：创建时把报告标题 + Markdown 正文 + 来源冻结进快照，原报告后续删改不影响分享。
同报告复用：已有有效分享则刷新快照并返回，不重复建链接。
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.logging import get_logger
from app.models.report_share_model import ReportShare
from app.models.research_report_model import RESEARCH_STATUS_DONE
from app.repositories.report_share_repository import ReportShareRepository
from app.repositories.research_report_repository import ResearchReportRepository

logger = get_logger(__name__)


class ReportShareService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ReportShareRepository(session)
        self.report_repo = ResearchReportRepository(session)

    async def create_share(
        self,
        user_id: uuid.UUID,
        report_id: uuid.UUID,
        expire_days: int | None,
        title: str | None = None,
    ) -> ReportShare:
        """创建/刷新报告分享。同报告已有有效分享则刷新快照复用，否则新建。"""
        report = await self.report_repo.get(user_id, report_id)
        if not report:
            raise BizError("研究报告不存在", code=3070, status_code=404)
        if report.status != RESEARCH_STATUS_DONE or not report.report_md:
            raise BizError("报告尚未完成，无法分享", code=3071)

        share_title = (title or "").strip() or (report.title or report.topic[:60] or "研究报告")
        content_md = report.report_md
        sources = report.sources or []

        expire_at = None
        if expire_days and expire_days > 0:
            expire_at = datetime.now(timezone.utc) + timedelta(days=expire_days)

        existing = await self.repo.get_active_by_report(user_id, report_id)
        if existing:
            existing.title = share_title
            existing.content_md = content_md
            existing.sources = sources
            existing.expire_at = expire_at
            saved = await self.repo.save(existing)
            logger.info("刷新报告分享: user=%s share=%s", user_id, saved.id)
            return saved

        share = ReportShare(
            user_id=user_id,
            report_id=report_id,
            share_token=secrets.token_urlsafe(16),
            title=share_title,
            content_md=content_md,
            sources=sources,
            is_active=True,
            expire_at=expire_at,
        )
        created = await self.repo.add(share)
        logger.info("创建报告分享: user=%s share=%s", user_id, created.id)
        return created

    async def list_shares(self, user_id: uuid.UUID) -> list[ReportShare]:
        return await self.repo.list_by_user(user_id)

    async def revoke(self, user_id: uuid.UUID, share_id: uuid.UUID) -> None:
        share = await self.repo.get(user_id, share_id)
        if not share:
            raise BizError("分享不存在", code=3072, status_code=404)
        share.is_active = False
        await self.repo.save(share)
        logger.info("取消报告分享: user=%s share=%s", user_id, share_id)

    async def get_public(self, token: str) -> dict:
        """公开查看（无需登录）：校验有效性 + 浏览数 +1，返回报告快照。"""
        share = await self.repo.get_by_token(token)
        if not share or not share.is_active:
            raise BizError("分享不存在或已取消", code=3073, status_code=404)
        if share.expire_at is not None:
            now = datetime.now(timezone.utc)
            exp = share.expire_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < now:
                raise BizError("分享链接已过期", code=3074, status_code=404)
        try:
            share.view_count = (share.view_count or 0) + 1
            await self.repo.save(share)
        except Exception as e:
            logger.warning("报告分享浏览数自增失败（忽略）: %s", e)
        return {
            "title": share.title,
            "markdown": share.content_md or "",
            "sources": share.sources or [],
            "created_at": share.created_at.isoformat() if share.created_at else None,
        }

    def share_out(self, share: ReportShare) -> dict:
        return {
            "id": str(share.id),
            "report_id": str(share.report_id),
            "share_token": share.share_token,
            "title": share.title,
            "is_active": share.is_active,
            "expire_at": share.expire_at.isoformat() if share.expire_at else None,
            "view_count": share.view_count or 0,
            "created_at": share.created_at.isoformat() if share.created_at else None,
        }
