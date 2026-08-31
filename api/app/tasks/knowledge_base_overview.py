"""知识库 Markdown 总览生成任务。

总览是知识库级别的内部索引，不写入 documents 表，也不会参与普通文档计数。
它会为知识库中的每篇已完成文档生成一段压缩摘要，并保存到对象存储。
"""
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.models  # noqa: F401
from app.celery_app import celery_app
from app.core.llm.client import close_llm_client
from app.core.llm.resolver import get_optional_client_for_type
from app.core.logging import get_logger
from app.core.rag.parser import parse_document
from app.core.storage import build_file_key, get_storage
from app.db.elastic import close as close_elastic
from app.db.postgres import create_task_engine
from app.models.document_model import DOC_STATUS_DONE
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository

logger = get_logger(__name__)

MAX_SOURCE_CHARS = 16000
MAX_OVERVIEW_CHARS = 24000


def overview_file_key(user_id: str | uuid.UUID, kb_id: str | uuid.UUID) -> str:
    return build_file_key(str(user_id), "knowledge-base-overviews", str(kb_id), ".md")


def build_overview_markdown(
    kb_name: str,
    summaries: list[dict[str, str]],
    *,
    generated_at: str | None = None,
    purpose: str | None = None,
) -> str:
    """将每篇文档的摘要拼成稳定、适合模型阅读的 Markdown。"""
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    lines = [
        f"# 知识库总览：{kb_name}",
        "",
        f"> 生成时间：{timestamp}  ",
        f"> 文档数量：{len(summaries)}（仅统计解析完成的文档）",
        "",
        "## 知识库用途",
        "",
        purpose
        or "当前知识库还没有已解析完成的文档。上传并解析文档后，这里会自动概括知识库的主题与资料范围。",
        "",
        "> 使用说明：这是一份导航索引。先用它判断资料范围和定位相关文档；涉及具体事实、数字或原文表述时，仍需调用知识库检索并以原文为准。",
        "",
        "## 文档目录",
        "",
        "| 序号 | 文档 | 核心主题 | 定位关键词 |",
        "| --- | --- | --- | --- |",
    ]
    for index, item in enumerate(summaries, 1):
        name = item.get("name", "未命名文档").replace("|", "\\|")
        topic = item.get("topic", "未提取").replace("|", "\\|").replace("\n", " ")
        keywords = item.get("keywords", "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {index} | {name} | {topic} | {keywords} |")

    lines.extend(["", "## 文档摘要", ""])
    for index, item in enumerate(summaries, 1):
        lines.extend(
            [
                f"### {index}. {item.get('name', '未命名文档')}",
                "",
                f"- 核心内容：{item.get('summary', '暂无摘要')}",
                f"- 关键词：{item.get('keywords', '未提取')}",
                f"- 可定位问题：{item.get('questions', '未提取')}",
                "",
            ]
        )
    return "\n".join(lines)[:MAX_OVERVIEW_CHARS]


async def generate_knowledge_base_overview(
    session: AsyncSession, user_id: uuid.UUID, kb_id: uuid.UUID
) -> str:
    kb = await KnowledgeBaseRepository(session).get(user_id, kb_id)
    if not kb:
        raise ValueError("知识库不存在")
    docs = await DocumentRepository(session).list_by_kb(user_id, kb_id)
    docs = [d for d in docs if d.status == DOC_STATUS_DONE]
    chat_client = await get_optional_client_for_type(session, user_id, "chat")
    summaries: list[dict[str, str]] = []
    for doc in docs:
        name = doc.file_name
        try:
            raw = await get_storage().get(doc.file_key)
            text = (parse_document(doc.file_ext, raw) or "").strip()
            source = text[:MAX_SOURCE_CHARS]
            if chat_client and source:
                answer = await chat_client.chat(
                    [
                        {
                            "role": "system",
                            "content": (
                                "你是知识库维护助手。请把一篇文档压缩成导航摘要，严格输出四行，"
                                "不要添加标题或 Markdown 代码块：\n"
                                "主题：...\n关键词：用逗号分隔\n摘要：不超过120字\n"
                                "可定位问题：列出3个以内用户可能提出的问题"
                            ),
                        },
                        {"role": "user", "content": f"文档名：{name}\n\n{source}"},
                    ],
                    temperature=0.1,
                    max_tokens=420,
                )
                values = {"topic": "未提取", "keywords": "未提取", "summary": "暂无摘要", "questions": "未提取"}
                for line in (answer or "").splitlines():
                    if "：" in line:
                        key, value = line.split("：", 1)
                        mapping = {"主题": "topic", "关键词": "keywords", "摘要": "summary", "可定位问题": "questions"}
                        if key.strip() in mapping and value.strip():
                            values[mapping[key.strip()]] = value.strip()
                summaries.append({"name": name, **values})
            else:
                summaries.append(
                    {
                        "name": name,
                        "topic": "待进一步概括",
                        "keywords": "",
                        "summary": " ".join(source.split())[:240] or "文档没有可提取文本",
                        "questions": "这篇文档包含哪些内容？",
                    }
                )
        except Exception as exc:  # 单篇失败不影响整个知识库总览
            logger.warning("生成文档摘要失败: kb=%s doc=%s err=%s", kb_id, doc.id, exc)
            summaries.append(
                {
                    "name": name,
                    "topic": "摘要生成失败",
                    "keywords": "",
                    "summary": "该文档暂时无法生成摘要，请直接检索原文。",
                    "questions": "该文档的主要内容是什么？",
                }
            )

    purpose = ""
    if chat_client and summaries:
        digest = "\n".join(
            f"- {item['name']}｜{item.get('topic', '')}｜{item.get('summary', '')}"
            for item in summaries
        )[:12000]
        try:
            purpose = (
                await chat_client.chat(
                    [
                        {
                            "role": "system",
                            "content": (
                                "根据文档摘要概括整个知识库的用途。用2到4句话说明：主要主题、"
                                "覆盖的资料范围、适合回答的问题。不要虚构，不要使用Markdown标题。"
                            ),
                        },
                        {"role": "user", "content": digest},
                    ],
                    temperature=0.1,
                    max_tokens=360,
                )
            ).strip()
        except Exception as exc:
            logger.warning("生成知识库用途失败: kb=%s err=%s", kb_id, exc)
    if not purpose and summaries:
        topics = "、".join(item.get("topic", "") for item in summaries[:8] if item.get("topic"))
        purpose = f"该知识库收录了 {len(summaries)} 篇文档，主要涉及：{topics or '请查看下方文档摘要'}。"

    markdown = build_overview_markdown(kb.name, summaries, purpose=purpose)
    file_key = overview_file_key(user_id, kb_id)
    await get_storage().save(file_key, markdown.encode("utf-8"))
    kb.overview_file_key = file_key
    kb.overview_status = "done"
    kb.overview_error = None
    kb.overview_updated_at = datetime.now(timezone.utc)
    await KnowledgeBaseRepository(session).save(kb)
    return markdown


async def _run(user_id: str, kb_id: str) -> None:
    engine = create_task_engine()
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with maker() as session:
            try:
                kb_uuid = uuid.UUID(kb_id)
                kb = await KnowledgeBaseRepository(session).get(uuid.UUID(user_id), kb_uuid)
                if kb:
                    kb.overview_status = "generating"
                    kb.overview_error = None
                    await KnowledgeBaseRepository(session).save(kb)
                await generate_knowledge_base_overview(session, uuid.UUID(user_id), kb_uuid)
            except Exception as exc:
                kb = await KnowledgeBaseRepository(session).get(uuid.UUID(user_id), uuid.UUID(kb_id))
                if kb:
                    kb.overview_status = "failed"
                    kb.overview_error = str(exc)[:500]
                    await KnowledgeBaseRepository(session).save(kb)
                raise
    finally:
        await engine.dispose()
        await close_llm_client()
        await close_elastic()


@celery_app.task(name="app.tasks.knowledge_base_overview.generate")
def generate_knowledge_base_overview_task(user_id: str, kb_id: str) -> str:
    asyncio.run(_run(user_id, kb_id))
    return kb_id


__all__ = [
    "build_overview_markdown",
    "generate_knowledge_base_overview",
    "generate_knowledge_base_overview_task",
    "overview_file_key",
    "read_overview_context",
]


async def read_overview_context(
    session: AsyncSession,
    user_id: uuid.UUID,
    kb_ids: list[str] | None,
    max_chars: int = 9000,
) -> str:
    """读取当前问答范围内的总览，作为检索前的导航上下文。"""
    if not kb_ids:
        return ""
    repo = KnowledgeBaseRepository(session)
    parts: list[str] = []
    remaining = max_chars
    for raw_id in kb_ids:
        try:
            kb = await repo.get(user_id, uuid.UUID(str(raw_id)))
        except (ValueError, TypeError):
            continue
        if not kb or not kb.overview_file_key or remaining <= 0:
            continue
        try:
            text = (await get_storage().get(kb.overview_file_key)).decode(
                "utf-8", errors="replace"
            )
        except Exception as exc:
            logger.warning("读取问答总览失败: kb=%s err=%s", raw_id, exc)
            continue
        if text.strip():
            piece = f"### {kb.name}\n{text.strip()}"
            parts.append(piece[:remaining])
            remaining -= len(piece)
    return "\n\n".join(parts)
