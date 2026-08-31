"""文档解析 Celery 任务：取文件 → 解析 → 父子分块 → 向量化 → 写 ES。

Celery 任务为同步入口，内部用 asyncio.run 跑异步流程。
每个任务使用独立的事件循环，需用任务级 DB 引擎并重置 ES 客户端，
避免全局单例绑定到已关闭的旧事件循环。
"""
import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.models  # noqa: F401  确保所有 ORM 模型注册到 metadata
from app.celery_app import celery_app
from app.core.llm.client import close_llm_client
from app.core.llm.resolver import get_client_for_type, get_optional_client_for_type
from app.core.logging import get_logger
from app.core.rag.chunker import chunk_parent_child
from app.core.rag.classifier import classify_content
from app.core.rag.es_index import CHUNK_TYPE_CHILD, CHUNK_TYPE_PARENT
from app.core.rag.es_store import (
    build_chunk_doc,
    bulk_index,
    delete_by_source,
    update_tags_by_source,
)
from app.core.rag.parser import parse_document
from app.core.storage import get_storage
from app.db import elastic
from app.db.postgres import create_task_engine
from app.models.document_model import (
    DOC_STATUS_DONE,
    DOC_STATUS_FAILED,
    DOC_STATUS_PARSING,
)
from app.repositories.document_repository import DocumentRepository
from app.repositories.tag_repository import TagRepository

logger = get_logger(__name__)


async def _run(document_id: str) -> None:
    doc_uuid = uuid.UUID(document_id)
    engine = create_task_engine()
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with session_maker() as session:
            await _parse(session, document_id, doc_uuid)
    finally:
        await engine.dispose()
        # Windows 下 Celery 的 solo worker 会为每个任务调用 asyncio.run()，
        # 每次任务使用不同的事件循环。LLMClient 内部的共享 httpx.AsyncClient
        # 不能跨任务循环复用，否则下一个 PDF 任务会触发 "Event loop is closed"。
        await close_llm_client()
        # 关闭本任务事件循环内创建的 ES 客户端
        await elastic.close()


async def _parse(session: AsyncSession, document_id: str, doc_uuid: uuid.UUID) -> None:
    repo = DocumentRepository(session)
    doc = await repo.get_by_id(doc_uuid)
    if not doc:
        logger.warning("解析任务：文档不存在 %s", document_id)
        return

    try:
        doc.status = DOC_STATUS_PARSING
        doc.progress = 0.1
        await repo.save(doc)

        # 1. 取文件
        content = await get_storage().get(doc.file_key)
        # 2. 解析为纯文本
        text = parse_document(doc.file_ext, content)
        if not text.strip():
            raise ValueError("解析结果为空")
        doc.progress = 0.3
        await repo.save(doc)

        # 3. 父子分块
        parents = chunk_parent_child(text)
        if not parents:
            raise ValueError("分块结果为空")

        # 4. 子块向量化（用用户默认 embedding 模型）
        embed_client = await get_client_for_type(session, doc.user_id, "embedding")
        user_id = str(doc.user_id)
        kb_id = str(doc.kb_id) if doc.kb_id else None
        es_docs: list[dict] = []
        chunk_total = 0
        for parent in parents:
            parent_doc = build_chunk_doc(
                user_id=user_id,
                source_type="document",
                source_id=document_id,
                doc_name=doc.file_name,
                chunk_type=CHUNK_TYPE_PARENT,
                content=parent.content,
                vector=None,
                kb_id=kb_id,
            )
            parent_chunk_id = parent_doc["_id"]
            es_docs.append(parent_doc)

            if parent.children:
                vectors = await embed_client.embed(parent.children)
                for child, vec in zip(parent.children, vectors):
                    es_docs.append(
                        build_chunk_doc(
                            user_id=user_id,
                            source_type="document",
                            source_id=document_id,
                            doc_name=doc.file_name,
                            chunk_type=CHUNK_TYPE_CHILD,
                            content=child,
                            vector=vec,
                            parent_id=parent_chunk_id,
                            kb_id=kb_id,
                        )
                    )
                    chunk_total += 1
        doc.progress = 0.8
        await repo.save(doc)

        # 5. 写 ES（先清旧 chunk，支持重试幂等）
        await delete_by_source(user_id, document_id)
        await bulk_index(es_docs)

        # 6. AI 自动分类打标签（有对话模型才做，失败不阻断）
        await _auto_tag(session, doc, text)

        doc.status = DOC_STATUS_DONE
        doc.progress = 1.0
        doc.chunk_num = chunk_total
        doc.error_msg = None
        await repo.save(doc)
        from app.tasks.knowledge_base_overview import generate_knowledge_base_overview_task

        if doc.kb_id:
            generate_knowledge_base_overview_task.delay(str(doc.user_id), str(doc.kb_id))
        logger.info("文档解析完成: %s chunks=%d", document_id, chunk_total)
    except Exception as e:
        logger.error("文档解析失败: %s: %s", document_id, e, exc_info=True)
        doc.status = DOC_STATUS_FAILED
        doc.error_msg = str(e)[:500]
        await repo.save(doc)


async def _auto_tag(session: AsyncSession, doc, text: str) -> None:
    """用对话模型给文档分类，写回 PG（关联）与 ES（chunk tags）。"""
    chat_client = await get_optional_client_for_type(session, doc.user_id, "chat")
    if not chat_client:
        return
    tag_repo = TagRepository(session)
    existing = [t.name for t in await tag_repo.list_by_user(doc.user_id)]
    tag_names = await classify_content(chat_client, text, existing)
    if not tag_names:
        return
    tag_ids = []
    for name in tag_names:
        tag = await tag_repo.get_or_create(doc.user_id, name)
        tag_ids.append(tag.id)
    await tag_repo.set_document_tags(doc.id, tag_ids)
    await update_tags_by_source(str(doc.user_id), str(doc.id), tag_names)


@celery_app.task(name="app.tasks.parse.parse_document")
def parse_document_task(document_id: str) -> str:
    """解析文档的 Celery 任务入口。"""
    asyncio.run(_run(document_id))
    return document_id
