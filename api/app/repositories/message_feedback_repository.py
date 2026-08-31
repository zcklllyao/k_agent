"""消息反馈数据访问层。查询强制带 user_id 隔离。"""
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message_feedback_model import MessageFeedback


class MessageFeedbackRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(
        self, user_id: uuid.UUID, message_id: uuid.UUID
    ) -> MessageFeedback | None:
        result = await self.session.execute(
            select(MessageFeedback).where(
                MessageFeedback.user_id == user_id,
                MessageFeedback.message_id == message_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: uuid.UUID,
        message_id: uuid.UUID,
        conversation_id: uuid.UUID,
        rating: str,
        comment: str | None = None,
    ) -> MessageFeedback:
        """有则更新评级，无则新建（同用户+消息唯一）。"""
        existing = await self.get(user_id, message_id)
        if existing:
            existing.rating = rating
            if comment is not None:
                existing.comment = comment
            await self.session.commit()
            await self.session.refresh(existing)
            return existing
        feedback = MessageFeedback(
            user_id=user_id,
            message_id=message_id,
            conversation_id=conversation_id,
            rating=rating,
            comment=comment,
        )
        self.session.add(feedback)
        await self.session.commit()
        await self.session.refresh(feedback)
        return feedback

    async def remove(self, user_id: uuid.UUID, message_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(MessageFeedback).where(
                MessageFeedback.user_id == user_id,
                MessageFeedback.message_id == message_id,
            )
        )
        await self.session.commit()

    async def list_by_conversation(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> list[MessageFeedback]:
        result = await self.session.execute(
            select(MessageFeedback).where(
                MessageFeedback.user_id == user_id,
                MessageFeedback.conversation_id == conversation_id,
            )
        )
        return list(result.scalars().all())
