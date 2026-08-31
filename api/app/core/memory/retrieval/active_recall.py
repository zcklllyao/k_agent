"""记忆主动召回：对话每轮用当前问题检索相关记忆 + 洞察，拼成背景块注入 system prompt。

与「记忆工具」并存：主动召回提供基础背景（主动、稳定），LLM 仍可调记忆工具查更细。
带余弦门控节流：命中相关度低于阈值则不注入，避免无关噪声挤占上下文。

性能：query 只做一次 embedding（洞察/实体召回复用同一向量）；两路召回并行；
整体加超时保护，召回是锦上添花，超时即放弃注入，绝不拖累对话首字延迟。
"""
import asyncio
import uuid

from app.config import settings
from app.core.llm.client import LLMClient
from app.core.logging import get_logger
from app.core.memory.retrieval.searcher import search_memory
from app.repositories.neo4j.memory_graph_repository import MemoryGraphRepository

logger = get_logger(__name__)

# 召回整体超时（秒）：超时放弃注入，直接让模型回答
_RECALL_TIMEOUT = 3.5


def _confidence(value: object, default: float = 0.8) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _uncertain_prefix(confidence: object) -> str:
    return "待确认：" if _confidence(confidence) < settings.active_recall_uncertain_confidence else ""


async def recall_context(
    *,
    embed_client: LLMClient,
    user_id: uuid.UUID,
    query: str,
) -> str:
    """召回与当前问题相关的记忆事实 + 洞察，拼成背景块。无命中/超时返回空串。"""
    query = (query or "").strip()
    if not query:
        return ""
    try:
        return await asyncio.wait_for(
            _do_recall(embed_client, user_id, query), timeout=_RECALL_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.info("主动召回超时（>%.1fs），跳过注入: user=%s", _RECALL_TIMEOUT, user_id)
        return ""
    except Exception as e:
        logger.warning("主动召回失败（忽略）: user=%s err=%s", user_id, e)
        return ""


async def _do_recall(
    embed_client: LLMClient, user_id: uuid.UUID, query: str
) -> str:
    uid = str(user_id)
    # 1. query 只 embed 一次，洞察与实体召回复用
    try:
        qvec = await embed_client.embed_one(query)
    except Exception as e:
        logger.warning("主动召回-向量化失败（忽略）: %s", e)
        return ""

    repo = MemoryGraphRepository()

    async def _recall_insights() -> list[str]:
        try:
            rows = await repo.search_insights_by_vector(
                uid, qvec, settings.active_recall_insight_top_k
            )
            return [
                (r.get("content") or "").strip()
                for r in rows
                if (r.get("content") or "").strip()
            ]
        except Exception as e:
            logger.warning("主动召回-洞察失败（忽略）: %s", e)
            return []

    async def _recall_entities() -> list[str]:
        lines: list[str] = []
        try:
            hits = await search_memory(
                embed_client=embed_client,
                user_id=user_id,
                query=query,
                top_k=settings.active_recall_entity_top_k,
                min_vector_score=settings.active_recall_min_score,
                min_confidence=settings.active_recall_min_confidence,
                use_reliability_score=True,
                query_vector=qvec,  # 复用已算好的向量，不重复 embedding
            )
            for h in hits:
                name = h.get("name") or ""
                desc = (h.get("description") or "").strip()
                prefix = _uncertain_prefix(h.get("confidence"))
                lines.append(f"- {prefix}{name}：{desc}" if desc else f"- {prefix}{name}")
                for rel in h.get("relations", [])[:2]:
                    obj = rel.get("object_name") or ""
                    if obj:
                        rel_prefix = _uncertain_prefix(rel.get("confidence"))
                        lines.append(f"  · {rel_prefix}{name} {rel.get('predicate', '')} {obj}")
        except Exception as e:
            logger.warning("主动召回-记忆失败（忽略）: %s", e)
        return lines

    # 2. 两路并行
    insight_lines, memory_lines = await asyncio.gather(
        _recall_insights(), _recall_entities()
    )

    if not insight_lines and not memory_lines:
        return ""

    parts: list[str] = [
        "【关于用户的已知信息（供参考，可自然融入回答，不必刻意提及；"
        "待确认内容不要当作确定事实，回答时应表达不确定或向用户确认）】"
    ]
    if insight_lines:
        parts.append("我对用户的理解：" + "；".join(insight_lines))
    if memory_lines:
        parts.append("相关记忆：")
        parts.extend(memory_lines)
    block = "\n".join(parts)

    if len(block) > settings.active_recall_max_chars:
        block = block[: settings.active_recall_max_chars] + "…"
    logger.info(
        "主动召回命中: user=%s 洞察=%d 记忆行=%d",
        user_id, len(insight_lines), len(memory_lines),
    )
    return block


__all__ = ["recall_context"]
