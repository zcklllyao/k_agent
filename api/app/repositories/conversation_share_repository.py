"""对话分享数据访问层。查询带 user_id 隔离；公开查询按 token。"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_share_model import ConversationShare


class ConversationShareRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, share: ConversationShare) -> ConversationShare:
        self.session.add(share)
        await self.session.commit()
        await self.session.refresh(share)
        return share

    async def save(self, share: ConversationShare) -> ConversationShare:
        await self.session.commit()
        await self.session.refresh(share)
        return share

    async def get(
        self, user_id: uuid.UUID, share_id: uuid.UUID
    ) -> ConversationShare | None:
        result = await self.session.execute(
            select(ConversationShare).where(
                ConversationShare.id == share_id,
                ConversationShare.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_active_by_conversation(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> ConversationShare | None:
        """取该会话已有的有效分享（复用，避免一个会话一堆链接）。"""
        result = await self.session.execute(
            select(ConversationShare).where(
                ConversationShare.user_id == user_id,
                ConversationShare.conversation_id == conversation_id,
                ConversationShare.is_active.is_(True),
            )
        )
        return result.scalars().first()

    async def get_by_token(self, token: str) -> ConversationShare | None:
        result = await self.session.execute(
            select(ConversationShare).where(
                ConversationShare.share_token == token
            )
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID) -> list[ConversationShare]:
        result = await self.session.execute(
            select(ConversationShare)
            .where(ConversationShare.user_id == user_id)
            .order_by(ConversationShare.created_at.desc())
        )
        return list(result.scalars().all())
