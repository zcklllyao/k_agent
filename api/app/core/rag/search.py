"""混合检索：向量召回 + BM25 召回 → 加权融合 →（可选）rerank 重排。

强制 user_id 过滤做多租户隔离。命中子块后返回其父块内容提供更大上下文。
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm.resolver import get_client_for_type, get_optional_client_for_type
from app.core.logging import get_logger
from app.core.rag.es_index import CHUNK_TYPE_CHILD, CHUNK_TYPE_IMAGE, CHUNKS_INDEX
from app.core.rag.language import detect_text_language, keyword_search_fields
from app.db.elastic import get_es

logger = get_logger(__name__)

# 融合权重
_VECTOR_WEIGHT = 0.6
_BM25_WEIGHT = 0.4


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return {k: 1.0 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


async def hybrid_search(
    session: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    top_k: int = 5,
    recall_size: int = 20,
    tags: list[str] | None = None,
    source_type: str | None = None,
    min_vector_score: float | None = None,
    kb_ids: list[str] | None = None,
) -> list[dict]:
    """混合检索，返回 top_k 个结果（含 content / doc_name / source_id / score）。

    source_type 可选 document / image，在 ES 召回阶段就过滤，避免跨类型互相淹没。
    文档检索命中 child 子块（再取父块上下文）；图片检索命中 image_desc 块。

    kb_ids 不为空时限定只检索这些知识库的内容（对话时取"已启用检索"的库集合）。
    传入空列表 [] 表示没有任何启用的库 → 直接返回空（不检索）。

    min_vector_score 不为 None 时启用「绝对相关度门控」（精确导向，用于全局搜索）：
    只保留 BM25 命中 或 向量原始余弦得分 ≥ 阈值的结果，丢弃不相关的最近邻噪声。
    """
    es = get_es()
    uid = str(user_id)

    # 文档用 child 子块；图片用 image_desc 块
    if source_type == "image":
        chunk_types = [CHUNK_TYPE_IMAGE]
    elif source_type == "document":
        chunk_types = [CHUNK_TYPE_CHILD]
    else:
        # 不限来源：同时检索文档子块和图片描述块
        chunk_types = [CHUNK_TYPE_CHILD, CHUNK_TYPE_IMAGE]

    base_filter: list[dict] = [
        {"term": {"user_id": uid}},
        {"terms": {"chunk_type": chunk_types}},
    ]
    if kb_ids is not None:
        base_filter.append({"terms": {"kb_id": kb_ids}})
    if tags:
        base_filter.append({"terms": {"tags": tags}})
    if source_type:
        base_filter.append({"term": {"source_type": source_type}})

    # 1. 向量召回
    embed_client = await get_client_for_type(session, user_id, "embedding")
    query_vector = await embed_client.embed_one(query)
    knn_resp = await es.search(
        index=CHUNKS_INDEX,
        body={
            "size": recall_size,
            "query": {"bool": {"filter": base_filter}},
            "knn": {
                "field": "vector",
                "query_vector": query_vector,
                "k": recall_size,
                "num_candidates": recall_size * 5,
                "filter": {"bool": {"filter": base_filter}},
            },
        },
    )

    # 2. BM25 召回：中文走 IK，英文走 english analyzer，混合查询同时检索。
    query_language = detect_text_language(query)
    search_fields = keyword_search_fields(query_language)
    bm25_resp = await es.search(
        index=CHUNKS_INDEX,
        body={
            "size": recall_size,
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": search_fields,
                                "type": "best_fields",
                            }
                        }
                    ],
                    "filter": base_filter,
                }
            },
        },
    )

    # 3. 收集 + 归一化 + 加权融合
    hits: dict[str, dict] = {}
    vec_scores: dict[str, float] = {}
    bm_scores: dict[str, float] = {}
    for h in knn_resp["hits"]["hits"]:
        hits[h["_id"]] = h["_source"]
        vec_scores[h["_id"]] = h["_score"]
    for h in bm25_resp["hits"]["hits"]:
        hits[h["_id"]] = h["_source"]
        bm_scores[h["_id"]] = h["_score"]

    vec_n = _normalize(vec_scores)
    bm_n = _normalize(bm_scores)
    fused: dict[str, float] = {}
    for cid in hits:
        fused[cid] = (
            _VECTOR_WEIGHT * vec_n.get(cid, 0.0) + _BM25_WEIGHT * bm_n.get(cid, 0.0)
        )

    # 3.5 精确模式（全局搜索）：纯语义余弦门控
    # ES cosine knn 的 _score = (1 + cos) / 2 → cos = 2*score - 1
    # 只保留余弦 ≥ 阈值的结果，按余弦排序，分数用余弦；BM25 单字噪声不达标即丢弃
    if min_vector_score is not None:
        cos_scores = {cid: 2.0 * s - 1.0 for cid, s in vec_scores.items()}
        kept = {cid: c for cid, c in cos_scores.items() if c >= min_vector_score}
        if not kept:
            return []
        ranked = sorted(kept.items(), key=lambda x: x[1], reverse=True)
        candidate_ids = [cid for cid, _ in ranked[:top_k]]
        results: list[dict] = []
        for cid in candidate_ids:
            src = hits[cid]
            content = await _resolve_parent_content(es, uid, src)
            results.append(
                {
                    "chunk_id": cid,
                    "content": content,
                    "doc_name": src.get("doc_name"),
                    "source_id": src.get("source_id"),
                    "source_type": src.get("source_type"),
                    "kb_id": src.get("kb_id"),
                    "score": round(kept[cid], 4),
                }
            )
        return results

    ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)
    candidate_ids = [cid for cid, _ in ranked[: max(top_k, recall_size)]]

    # 4. 可选 rerank（用户配了 rerank 模型才走）
    rerank_client = await get_optional_client_for_type(session, user_id, "rerank")
    if rerank_client and candidate_ids:
        docs = [hits[cid]["content"] for cid in candidate_ids]
        try:
            reranked = await rerank_client.rerank(query, docs, top_n=top_k)
            candidate_ids = [candidate_ids[idx] for idx, _ in reranked]
        except Exception as e:
            logger.warning("rerank 失败，回退加权融合排序: %s", e)

    # 5. 取 top_k，返回父块内容（small-to-big）
    results: list[dict] = []
    for cid in candidate_ids[:top_k]:
        src = hits[cid]
        content = await _resolve_parent_content(es, uid, src)
        results.append(
            {
                "chunk_id": cid,
                "content": content,
                "doc_name": src.get("doc_name"),
                "source_id": src.get("source_id"),
                "source_type": src.get("source_type"),
                "kb_id": src.get("kb_id"),
                "score": round(fused.get(cid, 0.0), 4),
            }
        )
    return results


async def _resolve_parent_content(es, user_id: str, child_src: dict) -> str:
    """命中子块时取其父块内容，提供更大上下文；取不到则用子块本身。"""
    parent_id = child_src.get("parent_id")
    if not parent_id:
        return child_src.get("content", "")
    resp = await es.search(
        index=CHUNKS_INDEX,
        body={
            "size": 1,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"user_id": user_id}},
                        {"term": {"chunk_id": parent_id}},
                    ]
                }
            },
        },
    )
    docs = resp["hits"]["hits"]
    if docs:
        return docs[0]["_source"].get("content", "")
    return child_src.get("content", "")
