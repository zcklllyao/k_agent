"""情绪记忆数据访问层。查询强制带 user_id 隔离。"""
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.emotion_model import EmotionProfile, EmotionRecord


class EmotionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── 情绪记录 ──

    async def add_record(self, record: EmotionRecord) -> EmotionRecord:
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def recent_records(
        self, user_id: uuid.UUID, limit: int = 20
    ) -> list[EmotionRecord]:
        """最近 N 条情绪记录（倒序）。"""
        result = await self.session.execute(
            select(EmotionRecord)
            .where(EmotionRecord.user_id == user_id)
            .order_by(EmotionRecord.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_records(
        self, user_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> tuple[list[EmotionRecord], int]:
        """情绪记录分页列表 + 总数。"""
        total = await self.session.scalar(
            select(func.count())
            .select_from(EmotionRecord)
            .where(EmotionRecord.user_id == user_id)
        )
        result = await self.session.execute(
            select(EmotionRecord)
            .where(EmotionRecord.user_id == user_id)
            .order_by(EmotionRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), int(total or 0)

    async def records_since(
        self, user_id: uuid.UUID, since: datetime
    ) -> list[EmotionRecord]:
        """某时间点之后的情绪记录（按时间正序，趋势/分布用）。"""
        result = await self.session.execute(
            select(EmotionRecord)
            .where(
                EmotionRecord.user_id == user_id,
                EmotionRecord.created_at >= since,
            )
            .order_by(EmotionRecord.created_at.asc())
        )
        return list(result.scalars().all())

    # ── 情绪画像 ──

    async def get_profile(self, user_id: uuid.UUID) -> EmotionProfile | None:
        result = await self.session.execute(
            select(EmotionProfile).where(EmotionProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert_profile(
        self,
        user_id: uuid.UUID,
        dominant_emotion: str,
        avg_valence: float,
        avg_arousal: float,
        sample_count: int,
    ) -> EmotionProfile:
        profile = await self.get_profile(user_id)
        if profile is None:
            profile = EmotionProfile(user_id=user_id)
            self.session.add(profile)
        profile.dominant_emotion = dominant_emotion
        profile.avg_valence = avg_valence
        profile.avg_arousal = avg_arousal
        profile.sample_count = sample_count
        await self.session.commit()
        await self.session.refresh(profile)
        return profile
