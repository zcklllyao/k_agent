"""情绪分析 Celery 任务：分析用户某轮发言情绪 → 写 emotion_records → 刷新画像。

与记忆萃取一致：同步入口内用 asyncio.run 跑异步；任务级 DB 引擎（NullPool）
避免事件循环绑定问题。情绪分析失败不影响对话主流程（对话侧已 fire-and-forget）。
"""
import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.models  # noqa: F401  确保所有 ORM 模型注册到 metadata
from app.celery_app import celery_app
from app.config import settings
from app.core.emotion.aggregator import aggregate_profile
from app.core.emotion.analyzer import analyze_emotion
from app.core.llm.resolver import get_client_for_type
from app.core.logging import get_logger
from app.db.postgres import create_task_engine
from app.models.emotion_model import EmotionRecord
from app.repositories.emotion_repository import EmotionRepository

logger = get_logger(__name__)


async def _run(
    user_id: str,
    text: str,
    conversation_id: str | None,
    message_id: str | None,
) -> None:
    engine = create_task_engine()
    session_maker = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    try:
        async with session_maker() as session:
            await _analyze(session, user_id, text, conversation_id, message_id)
    finally:
        await engine.dispose()


async def _analyze(
    session: AsyncSession,
    user_id: str,
    text: str,
    conversation_id: str | None,
    message_id: str | None,
) -> None:
    uid = uuid.UUID(user_id)
    repo = EmotionRepository(session)

    # 取对话模型分析情绪
    try:
        client = await get_client_for_type(session, uid, "chat")
    except Exception as e:
        logger.warning("情绪分析跳过（无对话模型）: user=%s err=%s", user_id, e)
        return

    try:
        result = await analyze_emotion(client, text)
    except Exception as e:
        logger.warning("情绪分析失败（忽略）: user=%s err=%s", user_id, e)
        return

    # 弱情绪（强度低于阈值）丢弃，不入库
    if result.intensity < settings.emotion_min_intensity:
        logger.info(
            "情绪强度低于阈值，丢弃: user=%s intensity=%.2f", user_id, result.intensity
        )
        return

    try:
        await repo.add_record(
            EmotionRecord(
                user_id=uid,
                conversation_id=uuid.UUID(conversation_id) if conversation_id else None,
                message_id=uuid.UUID(message_id) if message_id else None,
                emotion_type=result.emotion_type,
                intensity=result.intensity,
                valence=result.valence,
                arousal=result.arousal,
                keywords=result.keywords,
                trigger=result.trigger,
                summary=result.summary,
            )
        )
        # 刷新当前画像（最近 N 条滚动平均）
        recent = await repo.recent_records(uid, settings.emotion_profile_window)
        agg = aggregate_profile(recent)
        await repo.upsert_profile(
            uid, agg.dominant_emotion, agg.avg_valence, agg.avg_arousal, agg.sample_count
        )
        logger.info(
            "情绪分析完成: user=%s emotion=%s intensity=%.2f valence=%.2f",
            user_id,
            result.emotion_type,
            result.intensity,
            result.valence,
        )
    except Exception as e:
        logger.error("情绪记录写入失败: user=%s err=%s", user_id, e, exc_info=True)


@celery_app.task(name="app.tasks.emotion.analyze_emotion")
def analyze_emotion_task(
    user_id: str,
    text: str,
    conversation_id: str | None = None,
    message_id: str | None = None,
) -> str:
    """情绪分析的 Celery 任务入口。"""
    asyncio.run(_run(user_id, text, conversation_id, message_id))
    return user_id
