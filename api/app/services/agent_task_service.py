"""定时/主动任务业务服务：CRUD + 下次运行时间计算 + 立即运行一次。

调度本身由 Celery beat 每分钟心跳扫表触发（见 tasks/agent_task.py），本服务只管
任务的增删改查与 next_run_at 维护。
"""
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.logging import get_logger
from app.models.agent_task_model import (
    TRIGGER_DAILY,
    TRIGGER_INTERVAL,
    TRIGGER_WEEKLY,
    AgentTask,
)
from app.repositories.agent_task_repository import AgentTaskRepository
from app.schemas.agent_task_schema import AgentTaskUpsertRequest

logger = get_logger(__name__)

TZ = ZoneInfo("Asia/Shanghai")


def _parse_hhmm(text: str | None) -> tuple[int, int]:
    """解析 'HH:MM'，非法则回退 09:00。"""
    try:
        hh, mm = (text or "09:00").split(":")
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except (ValueError, AttributeError):
        pass
    return 9, 0


def compute_next_run(task: AgentTask, from_dt: datetime | None = None) -> datetime:
    """根据触发规则计算下次运行时间（Asia/Shanghai 时区感知）。"""
    now = from_dt or datetime.now(TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ)

    if task.trigger_type == TRIGGER_INTERVAL:
        hours = task.trigger_interval_hours or 24
        return now + timedelta(hours=hours)

    h, m = _parse_hhmm(task.trigger_time)
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)

    if task.trigger_type == TRIGGER_WEEKLY:
        weekday = task.trigger_weekday if task.trigger_weekday is not None else 0
        days_ahead = (weekday - now.weekday()) % 7
        target = target + timedelta(days=days_ahead)
        if target <= now:
            target = target + timedelta(days=7)
        return target

    # daily
    if target <= now:
        target = target + timedelta(days=1)
    return target


class AgentTaskService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AgentTaskRepository(session)

    async def create(
        self, user_id: uuid.UUID, body: AgentTaskUpsertRequest
    ) -> AgentTask:
        self._validate(body)
        task = AgentTask(
            user_id=user_id,
            name=body.name.strip(),
            instruction=body.instruction.strip(),
            kb_ids=body.kb_ids or None,
            trigger_type=body.trigger_type,
            trigger_time=body.trigger_time,
            trigger_weekday=body.trigger_weekday,
            trigger_interval_hours=body.trigger_interval_hours,
            enabled=body.enabled,
            notify_enabled=body.notify_enabled,
        )
        task.next_run_at = compute_next_run(task) if body.enabled else None
        created = await self.repo.create(task)
        logger.info("创建定时任务: user=%s id=%s next=%s", user_id, created.id, created.next_run_at)
        return created

    async def update(
        self, user_id: uuid.UUID, task_id: uuid.UUID, body: AgentTaskUpsertRequest
    ) -> AgentTask:
        self._validate(body)
        task = await self._get_or_404(user_id, task_id)
        task.name = body.name.strip()
        task.instruction = body.instruction.strip()
        task.kb_ids = body.kb_ids or None
        task.trigger_type = body.trigger_type
        task.trigger_time = body.trigger_time
        task.trigger_weekday = body.trigger_weekday
        task.trigger_interval_hours = body.trigger_interval_hours
        task.enabled = body.enabled
        task.notify_enabled = body.notify_enabled
        task.next_run_at = compute_next_run(task) if body.enabled else None
        return await self.repo.save(task)

    async def set_enabled(
        self, user_id: uuid.UUID, task_id: uuid.UUID, enabled: bool
    ) -> AgentTask:
        task = await self._get_or_404(user_id, task_id)
        task.enabled = enabled
        task.next_run_at = compute_next_run(task) if enabled else None
        return await self.repo.save(task)

    async def delete(self, user_id: uuid.UUID, task_id: uuid.UUID) -> None:
        task = await self._get_or_404(user_id, task_id)
        await self.repo.delete(task)

    async def run_now(self, user_id: uuid.UUID, task_id: uuid.UUID) -> None:
        """立即运行一次（派发 Celery 执行任务，不改 next_run_at）。"""
        await self._get_or_404(user_id, task_id)
        from app.tasks.agent_task import run_agent_task_task

        run_agent_task_task.delay(str(task_id))

    async def list_tasks(self, user_id: uuid.UUID) -> list[dict]:
        tasks = await self.repo.list_by_user(user_id)
        return [self.to_dict(t) for t in tasks]

    async def list_runs(self, user_id: uuid.UUID, task_id: uuid.UUID) -> list[dict]:
        """某任务的运行历史（复用 research_reports，task_id 关联）。

        V0.0.5 ② 起,每条 run 附 `verified`(passed/exceeded/failed/none)+ `final_score`,
        前端能直接显示评分徽章。无 LoopRun 时 verified='none' 不影响展示。
        """
        from app.core.agent.loop.store import LoopStore
        from app.models.loop_model import LoopRun
        from app.repositories.research_report_repository import (
            ResearchReportRepository,
        )
        from sqlalchemy import select

        await self._get_or_404(user_id, task_id)
        reports = await ResearchReportRepository(self.session).list_by_task(
            user_id, task_id
        )
        report_ids = [r.id for r in reports]

        # 批量查这些 report 对应的最新 LoopRun(避免 N+1)
        loop_by_report: dict = {}
        if report_ids:
            stmt = (
                select(LoopRun)
                .where(LoopRun.task_type == "research")
                .where(LoopRun.task_id.in_(report_ids))
                .order_by(LoopRun.started_at.desc())
            )
            res = await self.session.execute(stmt)
            for run in res.scalars().all():
                if run.task_id and run.task_id not in loop_by_report:
                    loop_by_report[run.task_id] = run
        _ = LoopStore  # 引用一下避免 ruff 提示未使用

        return [
            {
                "id": str(r.id),
                "title": r.title or r.topic,
                "status": r.status,
                "error_msg": r.error_msg,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "verified": (
                    loop_by_report[r.id].status if r.id in loop_by_report else "none"
                ),
                "final_score": (
                    loop_by_report[r.id].final_score if r.id in loop_by_report else None
                ),
            }
            for r in reports
        ]

    async def unread_count(self, user_id: uuid.UUID) -> int:
        """未读定时报告数（created_at 晚于用户上次查看简报的时间）。"""
        from app.models.user_model import User
        from app.repositories.research_report_repository import (
            ResearchReportRepository,
        )

        user = await self.session.get(User, user_id)
        since = user.briefing_seen_at if user else None
        return await ResearchReportRepository(self.session).count_unread_scheduled(
            user_id, since
        )

    async def mark_seen(self, user_id: uuid.UUID) -> None:
        """把「上次查看简报时间」更新为现在，清未读红点。"""
        from app.models.user_model import User

        user = await self.session.get(User, user_id)
        if user:
            user.briefing_seen_at = datetime.now(TZ)
            await self.session.commit()

    async def _get_or_404(
        self, user_id: uuid.UUID, task_id: uuid.UUID
    ) -> AgentTask:
        task = await self.repo.get(user_id, task_id)
        if not task:
            raise BizError("任务不存在", code=3060, status_code=404)
        return task

    @staticmethod
    def _validate(body: AgentTaskUpsertRequest) -> None:
        if body.trigger_type in (TRIGGER_DAILY, TRIGGER_WEEKLY) and not body.trigger_time:
            raise BizError("请设置触发时间（HH:MM）", code=3061)
        if body.trigger_type == TRIGGER_WEEKLY and body.trigger_weekday is None:
            raise BizError("请选择每周触发的星期", code=3062)
        if body.trigger_type == TRIGGER_INTERVAL and not body.trigger_interval_hours:
            raise BizError("请设置间隔小时数", code=3063)

    @staticmethod
    def to_dict(t: AgentTask) -> dict:
        return {
            "id": str(t.id),
            "name": t.name,
            "instruction": t.instruction,
            "kb_ids": t.kb_ids or [],
            "trigger_type": t.trigger_type,
            "trigger_time": t.trigger_time,
            "trigger_weekday": t.trigger_weekday,
            "trigger_interval_hours": t.trigger_interval_hours,
            "enabled": t.enabled,
            "notify_enabled": t.notify_enabled,
            "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
            "last_status": t.last_status or None,
            "next_run_at": t.next_run_at.isoformat() if t.next_run_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
