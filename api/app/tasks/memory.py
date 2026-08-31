"""记忆萃取 Celery 任务：取 memories 原文 → 萃取流水线 → 写 Neo4j → 回写状态。

与文档解析任务一致：任务为同步入口，内部用 asyncio.run 跑异步；
每个任务用任务级 DB 引擎（NullPool）避免事件循环绑定问题。
"""
import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.models  # noqa: F401  确保所有 ORM 模型注册到 metadata
from app.celery_app import celery_app
from app.core.llm.resolver import get_client_for_type
from app.core.logging import get_logger
from app.core.memory.extraction.orchestrator import run_extraction
from app.db import neo4j
from app.db.postgres import create_task_engine
from app.models.memory_model import (
    MEMORY_STATUS_DONE,
    MEMORY_STATUS_EXTRACTING,
    MEMORY_STATUS_FAILED,
)
from app.repositories.memory_repository import MemoryRepository

logger = get_logger(__name__)


async def _run(memory_id: str) -> None:
    mem_uuid = uuid.UUID(memory_id)
    engine = create_task_engine()
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with session_maker() as session:
            await _extract(session, mem_uuid)
    finally:
        await engine.dispose()
        # 关闭本任务事件循环内创建的 Neo4j 驱动
        await neo4j.close()


async def _extract(session: AsyncSession, mem_uuid: uuid.UUID) -> None:
    repo = MemoryRepository(session)
    memory = await repo.get_by_id(mem_uuid)
    if not memory:
        logger.warning("萃取任务：记忆不存在 %s", mem_uuid)
        return
    try:
        memory.status = MEMORY_STATUS_EXTRACTING
        await repo.save(memory)

        chat_client = await get_client_for_type(session, memory.user_id, "chat")
        embed_client = await get_client_for_type(session, memory.user_id, "embedding")

        stats = await run_extraction(
            chat_client=chat_client,
            embed_client=embed_client,
            user_id=str(memory.user_id),
            text=memory.raw_text,
            source=memory.source,
            source_message_id=(
                str(memory.source_message_id) if memory.source_message_id else None
            ),
        )

        memory.status = MEMORY_STATUS_DONE
        memory.graph_dialogue_id = stats.dialogue_id
        memory.graph_stats = stats.to_dict()
        memory.error_msg = None
        await repo.save(memory)
        logger.info("记忆萃取完成: %s %s", mem_uuid, stats.to_dict())
    except Exception as e:
        logger.error("记忆萃取失败: %s: %s", mem_uuid, e, exc_info=True)
        memory.status = MEMORY_STATUS_FAILED
        memory.error_msg = str(e)[:500]
        await repo.save(memory)


@celery_app.task(name="app.tasks.memory.extract_memory")
def extract_memory_task(memory_id: str) -> str:
    """记忆萃取的 Celery 任务入口。"""
    asyncio.run(_run(memory_id))
    return memory_id
