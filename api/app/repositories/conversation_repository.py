"""会话 / 消息数据访问层。查询强制带 user_id / conversation_id 隔离。"""
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_model import Conversation, Message


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, conv: Conversation) -> Conversation:
        self.session.add(conv)
        await self.session.commit()
        await self.session.refresh(conv)
        return conv

    async def save(self, conv: Conversation) -> Conversation:
        await self.session.commit()
        await self.session.refresh(conv)
        return conv

    async def get(
        self, user_id: uuid.UUID, conv_id: uuid.UUID
    ) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation).where(
                Conversation.id == conv_id, Conversation.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID) -> list[Conversation]:
        result = await self.session.execute(
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.is_group.isnot(True),
            )
            .order_by(Conversation.updated_at.desc())
        )
        return list(result.scalars().all())

    async def delete(self, conv: Conversation) -> None:
        await self.session.delete(conv)
        await self.session.commit()

    async def touch(self, conv_id: uuid.UUID) -> None:
        """更新会话的 updated_at（有新消息时调用，保证列表按最近活跃排序）。"""
        from sqlalchemy import func, update

        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conv_id)
            .values(updated_at=func.now())
        )
        await self.session.commit()


class MessageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, message: Message) -> Message:
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def get(self, message_id: uuid.UUID) -> Message | None:
        result = await self.session.execute(
            select(Message).where(Message.id == message_id)
        )
        return result.scalar_one_or_none()

    async def delete(self, message: Message) -> None:
        await self.session.delete(message)
        await self.session.commit()

    async def list_by_conversation(
        self, conv_id: uuid.UUID, limit: int | None = None
    ) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at.asc())
        )
        if limit:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def recent_history(
        self, conv_id: uuid.UUID, max_turns: int
    ) -> list[Message]:
        """取最近 max_turns*2 条消息（user+assistant 成对），按时间正序返回。"""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at.desc())
            .limit(max_turns * 2)
        )
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())
        return list(reversed(rows))

    async def count(self, conv_id: uuid.UUID) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conv_id)
        )
        return int(total or 0)

    async def delete_by_conversation(self, conv_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(Message).where(Message.conversation_id == conv_id)
        )
        await self.session.commit()
