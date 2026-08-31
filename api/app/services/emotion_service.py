"""情绪记忆业务服务：当前画像 / 趋势 / 记录 / 分布。

读侧聚合 emotion_records 与 emotion_profiles，供仪表盘与下游消费。
写侧（情绪分析入库 + 画像刷新）在 Celery 任务里完成，本服务只读。
"""
import uuid
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.emotion.ontology import DEFAULT_EMOTION
from app.repositories.emotion_repository import EmotionRepository


class EmotionService:
    def __init__(self, session: AsyncSession):
        self.repo = EmotionRepository(session)

    async def current(self, user_id: uuid.UUID) -> dict:
        """当前情绪画像；无记录返回中性默认画像 + 健康指数。"""
        profile = await self.repo.get_profile(user_id)
        if profile is None:
            return {
                "dominant_emotion": DEFAULT_EMOTION,
                "avg_valence": 0.0,
                "avg_arousal": 0.0,
                "sample_count": 0,
                "updated_at": None,
                "health_index": self._health_index(0.0),
            }
        return {
            "dominant_emotion": profile.dominant_emotion,
            "avg_valence": profile.avg_valence,
            "avg_arousal": profile.avg_arousal,
            "sample_count": profile.sample_count,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
            "health_index": self._health_index(profile.avg_valence),
        }

    async def records(
        self, user_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> dict:
        """情绪记录分页列表。"""
        rows, total = await self.repo.list_records(user_id, limit, offset)
        items = [
            {
                "id": str(r.id),
                "conversation_id": str(r.conversation_id) if r.conversation_id else None,
                "message_id": str(r.message_id) if r.message_id else None,
                "emotion_type": r.emotion_type,
                "intensity": r.intensity,
                "valence": r.valence,
                "arousal": r.arousal,
                "keywords": r.keywords or [],
                "trigger": r.trigger,
                "summary": r.summary,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
        return {"items": items, "total": total}

    async def trend(self, user_id: uuid.UUID, days: int = 7) -> dict:
        """近 days 天每天的 valence/arousal 平均 + 记录数。无数据的日期补 0。"""
        days = max(1, min(days, 90))
        today = datetime.now().date()
        start_date = today - timedelta(days=days - 1)
        since = datetime.combine(start_date, datetime.min.time())
        rows = await self.repo.records_since(user_id, since)

        # 按日期分组
        bucket: dict[str, list] = {}
        for r in rows:
            d = r.created_at.date().isoformat() if r.created_at else None
            if d:
                bucket.setdefault(d, []).append(r)

        points = []
        for i in range(days):
            d = (start_date + timedelta(days=i)).isoformat()
            recs = bucket.get(d, [])
            if recs:
                n = len(recs)
                points.append({
                    "date": d,
                    "avg_valence": round(sum(x.valence for x in recs) / n, 4),
                    "avg_arousal": round(sum(x.arousal for x in recs) / n, 4),
                    "count": n,
                })
            else:
                points.append({"date": d, "avg_valence": 0.0, "avg_arousal": 0.0, "count": 0})
        return {"points": points}

    async def distribution(self, user_id: uuid.UUID, days: int = 30) -> dict:
        """近 days 天情绪类型分布（饼图用）。"""
        days = max(1, min(days, 365))
        since = datetime.now() - timedelta(days=days)
        rows = await self.repo.records_since(user_id, since)
        counts = Counter(r.emotion_type for r in rows)
        items = [
            {"name": name, "value": cnt}
            for name, cnt in counts.most_common()
        ]
        return {"items": items, "total": len(rows)}

    @staticmethod
    def _health_index(avg_valence: float) -> int:
        """情绪健康指数 0~100：由平均效价（-1~1）线性映射到 0~100。"""
        return round((avg_valence + 1) / 2 * 100)


__all__ = ["EmotionService"]
