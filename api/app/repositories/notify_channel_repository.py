"""消息推送渠道数据访问层。查询带 user_id 隔离。"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notify_channel_model import NotifyChannel


class NotifyChannelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, ch: NotifyChannel) -> NotifyChannel:
        self.session.add(ch)
        await self.session.commit()
        await self.session.refresh(ch)
        return ch

    async def save(self, ch: NotifyChannel) -> NotifyChannel:
        await self.session.commit()
        await self.session.refresh(ch)
        return ch

    async def get(self, user_id: uuid.UUID, ch_id: uuid.UUID) -> NotifyChannel | None:
        stmt = select(NotifyChannel).where(
            NotifyChannel.id == ch_id, NotifyChannel.user_id == user_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID) -> list[NotifyChannel]:
        stmt = (
            select(NotifyChannel)
            .where(NotifyChannel.user_id == user_id)
            .order_by(NotifyChannel.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_enabled(self, user_id: uuid.UUID) -> list[NotifyChannel]:
        """取用户所有已启用渠道（推送时用）。"""
        stmt = select(NotifyChannel).where(
            NotifyChannel.user_id == user_id, NotifyChannel.enabled.is_(True)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, ch: NotifyChannel) -> None:
        await self.session.delete(ch)
        await self.session.commit()
