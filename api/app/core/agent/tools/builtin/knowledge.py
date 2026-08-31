"""知识库检索工具：检索相关片段，并提供精确的知识库文档统计。"""
import uuid

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.agent.tools.base import ToolBuildContext, ToolSpec, register_tool
from app.models.document_model import (
    DOC_STATUS_DONE,
    DOC_STATUS_FAILED,
    DOC_STATUS_PARSING,
    DOC_STATUS_PENDING,
    Document,
)

KEY = "knowledge_search"


class _QueryInput(BaseModel):
    query: str = Field(..., description="要检索的问题或关键词")


async def _document_counts(session, user_id, kb_ids: list[str] | None) -> dict[str, int]:
    """从 PostgreSQL 统计文档，而不是用 top-k 检索结果估算文档数。

    ES 中一个文档会被切成多个 chunk，因此不能用检索命中的 chunk 去重来回答
    “有多少篇”。
    """
    filters = [Document.user_id == user_id]
    if kb_ids is not None:
        # 空列表表示本轮没有启用任何知识库，不能误统计用户的全部文档。
        if not kb_ids:
            return {"total": 0, "ready": 0, "pending": 0, "parsing": 0, "failed": 0}
        filters.append(Document.kb_id.in_([uuid.UUID(k) for k in kb_ids]))

    rows = await session.execute(
        select(Document.status, func.count(Document.id))
        .where(*filters)
        .group_by(Document.status)
    )
    counts = {str(status): int(count) for status, count in rows.all()}
    return {
        "total": sum(counts.values()),
        "ready": counts.get(DOC_STATUS_DONE, 0),
        "pending": counts.get(DOC_STATUS_PENDING, 0),
        "parsing": counts.get(DOC_STATUS_PARSING, 0),
        "failed": counts.get(DOC_STATUS_FAILED, 0),
    }


async def _build(ctx: ToolBuildContext) -> StructuredTool:
    session = ctx.session
    user_id = ctx.user_id
    citations = ctx.citations
    stats_holder = ctx.stats_holder
    kb_ids = ctx.kb_ids

    async def _run(query: str) -> str:
        from app.core.rag.search import hybrid_search

        counts = await _document_counts(session, user_id, kb_ids)
        hits = await hybrid_search(session, user_id, query, top_k=5, kb_ids=kb_ids)
        # 命中统计仅用于展示检索效果，不再冒充知识库文档总数。
        doc_keys = {h.get("source_id") for h in hits if h.get("source_id")}
        stats_holder[KEY] = {
            "hit_count": len(hits),
            "doc_count": len(doc_keys),
            "total_doc_count": counts["total"],
            "ready_doc_count": counts["ready"],
            "pending_doc_count": counts["pending"],
            "parsing_doc_count": counts["parsing"],
            "failed_doc_count": counts["failed"],
        }
        if not hits:
            return (
                "知识库文档统计（按数据库中的文档记录精确统计，不能用本次检索条数代替）：\n"
                f"- 当前对话启用范围内文档总数：{counts['total']} 篇\n"
                f"- 已完成、可检索：{counts['ready']} 篇\n"
                f"- 待处理：{counts['pending']} 篇，解析中：{counts['parsing']} 篇，失败：{counts['failed']} 篇\n\n"
                "本次没有检索到与问题相关的片段。"
            )
        seen = {c["source_id"] for c in citations}
        parts: list[str] = []
        for h in hits:
            parts.append(h["content"])
            sid = h.get("source_id")
            if sid and sid not in seen:
                seen.add(sid)
                citations.append(
                    {
                        "source_id": sid,
                        "source_type": h.get("source_type"),
                        "doc_name": h.get("doc_name"),
                        "score": h.get("score"),
                    }
                )
        stats = (
            "知识库文档统计（精确总数）："
            f"当前范围共 {counts['total']} 篇，其中可检索 {counts['ready']} 篇；"
            f"本次相关结果覆盖 {len(doc_keys)} 篇文档、{len(hits)} 个片段。"
        )
        return stats + "\n\n检索到的相关知识库内容：\n\n" + "\n\n".join(parts)

    return StructuredTool.from_function(
        coroutine=_run,
        name=KEY,
        description=(
            "从用户知识库中检索相关内容。涉及知识库文档数量、总数或统计时必须调用此工具，"
            "并使用工具返回的数据库精确总数；检索命中片段数不是文档总数。"
        ),
        args_schema=_QueryInput,
    )


register_tool(
    ToolSpec(
        key=KEY,
        name="知识库检索",
        description="检索知识库内容并提供精确的文档数量统计。",
        icon="🔍",
        builder=_build,
        default_enabled=True,
    )
)
