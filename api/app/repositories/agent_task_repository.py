"""AgentTask 数据访问层 —— PostgreSQL agent_tasks 表。查询带 user_id 隔离（心跳除外）。"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_task_model import AgentTask


class AgentTaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, task: AgentTask) -> AgentTask:
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def save(self, task: AgentTask) -> AgentTask:
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def get(self, user_id: uuid.UUID, task_id: uuid.UUID) -> AgentTask | None:
        stmt = select(AgentTask).where(
            AgentTask.id == task_id, AgentTask.user_id == user_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, task_id: uuid.UUID) -> AgentTask | None:
        """心跳/执行用：仅按 id 取。"""
        stmt = select(AgentTask).where(AgentTask.id == task_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID) -> list[AgentTask]:
        stmt = (
            select(AgentTask)
            .where(AgentTask.user_id == user_id)
            .order_by(AgentTask.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_due(self) -> list[AgentTask]:
        """心跳：取所有启用且已到下次运行时间的任务（跨用户）。

        加 FOR UPDATE SKIP LOCKED：即便误起多个 beat，也不会同时抢到同一行重复触发；
        调用方需在同一事务内推进 next_run_at 后提交（保存即提交，释放行锁）。
        """
        stmt = (
            select(AgentTask)
            .where(
                AgentTask.enabled.is_(True),
                AgentTask.next_run_at.isnot(None),
                AgentTask.next_run_at <= func.now(),
            )
            .with_for_update(skip_locked=True)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, task: AgentTask) -> None:
        await self.session.delete(task)
        await self.session.commit()
