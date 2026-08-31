"""记忆业务服务：主动记住、记忆列表/详情/删除。

「主动记住」流程：建 memories 记录(status=pending) → 立即返回 → 派发 Celery 萃取任务。
萃取任务完成后回写 status 与图谱溯源统计。
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.logging import get_logger
from app.models.memory_model import (
    MEMORY_SOURCE_MANUAL,
    MEMORY_STATUS_PENDING,
    Memory,
)
from app.repositories.memory_repository import MemoryRepository

logger = get_logger(__name__)


class MemoryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = MemoryRepository(session)

    async def remember(self, user_id: uuid.UUID, text: str) -> Memory:
        """主动记住：落库 + 派发异步萃取任务。"""
        text = (text or "").strip()
        if not text:
            raise BizError("记忆内容不能为空", code=3001)
        memory = Memory(
            user_id=user_id,
            raw_text=text,
            source=MEMORY_SOURCE_MANUAL,
            status=MEMORY_STATUS_PENDING,
        )
        memory = await self.repo.create(memory)
        # 派发异步萃取（worker 起 memory 队列）
        from app.tasks.memory import extract_memory_task

        extract_memory_task.delay(str(memory.id))
        logger.info("主动记住已提交萃取: memory=%s", memory.id)
        return memory

    async def get_detail(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> Memory:
        memory = await self.repo.get_by_id(memory_id)
        if not memory or memory.user_id != user_id:
            raise BizError("记忆不存在", code=3002, status_code=404)
        return memory

    async def list_memories(
        self, user_id: uuid.UUID, page: int, page_size: int
    ) -> tuple[list[Memory], int]:
        return await self.repo.list_by_user(user_id, page, page_size)

    async def delete(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> None:
        memory = await self.get_detail(user_id, memory_id)
        await self.repo.delete(memory)

    async def search(
        self, user_id: uuid.UUID, query: str, top_k: int = 10
    ) -> list[dict]:
        """记忆检索：图谱混合检索（向量+全文+邻居遍历）。"""
        from app.core.llm.resolver import get_client_for_type
        from app.core.memory.retrieval.searcher import search_memory

        embed_client = await get_client_for_type(self.session, user_id, "embedding")
        return await search_memory(
            embed_client=embed_client, user_id=user_id, query=query, top_k=top_k
        )

    async def get_profile(self, user_id: uuid.UUID) -> dict:
        """画像视图：图谱实体按类型分组 + 类型计数。"""
        from app.repositories.neo4j.memory_graph_repository import (
            MemoryGraphRepository,
        )

        repo = MemoryGraphRepository()
        repo_factory = getattr(self, "_memory_graph_repo_factory", None)
        if repo_factory is not None:
            repo = repo_factory()
        uid = str(user_id)
        entities = await repo.list_all_entities(uid)
        counts = await repo.entity_type_counts(uid)

        groups: dict[str, list[dict]] = {}
        for e in entities:
            item = {
                "id": e.get("id"),
                "name": e.get("name"),
                "type": e.get("type"),
                "description": e.get("description") or "",
                "aliases": e.get("aliases") or [],
                "relations": e.get("relations") or [],
                "importance": e.get("importance", 0.5),
                "confidence": e.get("confidence", 0.8),
                "memory_layer": e.get("memory_layer") or "short_term",
                "access_count": e.get("access_count", 0),
                "mention_count": e.get("mention_count", 1),
                "core_facts": e.get("core_facts") or [],
                "traits": e.get("traits") or [],
            }
            groups.setdefault(item["type"], []).append(item)

        return {
            "total": len(entities),
            "type_counts": {c["type"]: c["cnt"] for c in counts},
            "groups": [
                {"type": t, "entities": items} for t, items in groups.items()
            ],
        }

    async def delete_entity(self, user_id: uuid.UUID, entity_id: str) -> None:
        """删除单个图谱实体（连带关系）。"""
        from app.repositories.neo4j.memory_graph_repository import (
            MemoryGraphRepository,
        )

        await MemoryGraphRepository().delete_entity(str(user_id), entity_id)

    # ── V0.0.5 ⑤ 人类反馈闭环 ──

    async def review_overview(self, user_id: uuid.UUID, days: int = 30) -> dict:
        """记忆审查 Tab 1「我的记忆全景」聚合:类型分布 + 置信度直方 +
        长短期比例 + 近 N 天新增趋势 + 纠错统计。"""
        from datetime import datetime as _dt, timedelta, timezone as _tz

        from app.repositories.memory_correction_repository import (
            MemoryCorrectionRepository,
        )
        from app.repositories.neo4j.memory_graph_repository import (
            MemoryGraphRepository,
        )

        uid = str(user_id)
        repo = MemoryGraphRepository()
        entities = await repo.list_all_entities(uid)
        # 类型分布
        type_dist: dict[str, int] = {}
        # 置信度 5 分桶(0~0.2 / 0.2~0.4 / ... / 0.8~1.0)
        conf_buckets = [0] * 5
        long_term = 0
        verified = 0
        # 近 30 天新增按天聚合
        since = _dt.now(_tz.utc) - timedelta(days=days)
        since_date = since.date()
        daily_new: dict[str, int] = {}
        for e in entities:
            t = e.get("type") or "其他"
            type_dist[t] = type_dist.get(t, 0) + 1
            conf = float(e.get("confidence", 0.8) or 0.8)
            idx = min(4, max(0, int(conf * 5)))
            conf_buckets[idx] += 1
            if e.get("memory_layer") == "long_term":
                long_term += 1
            if e.get("human_verified"):
                verified += 1
            ca = e.get("created_at")
            if ca:
                try:
                    # Neo4j 返回的 created_at 可能是 neo4j.time.DateTime
                    d = ca.to_native().date() if hasattr(ca, "to_native") else ca.date()
                    if d >= since_date:
                        key = d.isoformat()
                        daily_new[key] = daily_new.get(key, 0) + 1
                except Exception:  # noqa: BLE001
                    pass
        trend = [
            {"date": d, "count": daily_new.get(d, 0)}
            for d in sorted(daily_new.keys())
        ]
        # 纠错统计
        try:
            correction_counts = await MemoryCorrectionRepository(
                self.session
            ).count_by_action(user_id)
        except Exception:  # noqa: BLE001
            correction_counts = {}
        # 关系数(只算外向 RELATION)
        total_relations = sum(len(e.get("relations") or []) for e in entities)
        # 待确认(低置信度)实体数:< 0.75
        pending = sum(
            1 for e in entities
            if not e.get("human_verified")
            and float(e.get("confidence", 0.8) or 0.8) < 0.75
        )
        return {
            "total_entities": len(entities),
            "total_relations": total_relations,
            "long_term": long_term,
            "verified": verified,
            "pending": pending,
            "type_distribution": [
                {"type": t, "count": c}
                for t, c in sorted(
                    type_dist.items(), key=lambda x: x[1], reverse=True
                )
            ],
            "confidence_buckets": [
                {"range": "0~0.2", "count": conf_buckets[0]},
                {"range": "0.2~0.4", "count": conf_buckets[1]},
                {"range": "0.4~0.6", "count": conf_buckets[2]},
                {"range": "0.6~0.8", "count": conf_buckets[3]},
                {"range": "0.8~1.0", "count": conf_buckets[4]},
            ],
            "trend": trend,
            "correction_counts": correction_counts,
            "days": days,
        }

    async def list_review_entities(
        self,
        user_id: uuid.UUID,
        *,
        max_confidence: float = 0.75,
        type_: str | None = None,
        include_verified: bool = False,
        limit: int = 50,
    ) -> list[dict]:
        """Tab 2「审查列表」:筛选低置信度实体(默认 < 0.75 且未 verify)。"""
        from app.repositories.neo4j.memory_graph_repository import (
            MemoryGraphRepository,
        )

        entities = await MemoryGraphRepository().list_all_entities(str(user_id))
        out: list[dict] = []
        for e in entities:
            conf = float(e.get("confidence", 0.8) or 0.8)
            if conf > max_confidence:
                continue
            if not include_verified and e.get("human_verified"):
                continue
            if type_ and e.get("type") != type_:
                continue
            out.append({
                "id": e.get("id"),
                "name": e.get("name"),
                "type": e.get("type"),
                "description": e.get("description"),
                "aliases": e.get("aliases") or [],
                "confidence": round(conf, 3),
                "memory_layer": e.get("memory_layer") or "short_term",
                "human_verified": bool(e.get("human_verified")),
                "relations": [
                    {
                        "predicate": r.get("predicate"),
                        "object_name": r.get("object_name"),
                        "object_type": r.get("object_type"),
                        "confidence": r.get("confidence"),
                    }
                    for r in (e.get("relations") or [])[:5]
                ],
            })
        # 按置信度升序(最不确定的排前面给用户优先处理)
        out.sort(key=lambda x: x["confidence"])
        return out[:limit]

    async def confirm_entity(
        self, user_id: uuid.UUID, entity_id: str, reason: str | None = None
    ) -> dict:
        """👍 用户确认实体正确:打 human_verified=true / confidence=1.0,落 memory_corrections。"""
        from app.repositories.memory_correction_repository import (
            MemoryCorrectionRepository,
        )
        from app.repositories.neo4j.memory_graph_repository import (
            MemoryGraphRepository,
        )

        uid = str(user_id)
        repo = MemoryGraphRepository()
        before = await repo.entity_snapshot(uid, entity_id) or {}
        await repo.human_verify_entity(uid, entity_id)
        # 落 PG(失败只 warning 不阻断 Neo4j 已生效的操作)
        try:
            await MemoryCorrectionRepository(self.session).record(
                user_id=user_id,
                entity_id=entity_id,
                action="confirm",
                before=_serializable(before),
                after={"human_verified": True, "confidence": 1.0},
                reason=reason or "用户确认",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("memory_corrections 写入失败(不影响 Neo4j 已生效): %s", e)
        return {"ok": True, "entity_id": entity_id}

    async def correct_entity_with_reason(
        self,
        user_id: uuid.UUID,
        entity_id: str,
        *,
        name: str | None = None,
        type_: str | None = None,
        description: str | None = None,
        aliases: list[str] | None = None,
        reason: str | None = None,
    ) -> dict:
        """✏️ 用户修正实体属性。任一字段 None 即不改。"""
        from app.repositories.memory_correction_repository import (
            MemoryCorrectionRepository,
        )
        from app.repositories.neo4j.memory_graph_repository import (
            MemoryGraphRepository,
        )

        uid = str(user_id)
        repo = MemoryGraphRepository()
        before = await repo.entity_snapshot(uid, entity_id) or {}
        result = await repo.correct_entity(
            uid, entity_id,
            name=name, type_=type_, description=description, aliases=aliases,
        )
        after = {
            "name": result.get("name") if result else name,
            "type": result.get("type") if result else type_,
            "description": description,
            "aliases": aliases,
            "human_verified": True,
            "confidence": 1.0,
        }
        try:
            await MemoryCorrectionRepository(self.session).record(
                user_id=user_id,
                entity_id=entity_id,
                action="correct",
                before=_serializable(before),
                after={k: v for k, v in after.items() if v is not None},
                reason=reason or "用户修正",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("memory_corrections 写入失败: %s", e)
        return {"ok": True, "entity_id": entity_id, "name": after["name"]}

    async def delete_entity_with_reason(
        self, user_id: uuid.UUID, entity_id: str, reason: str | None = None
    ) -> dict:
        """🗑 用户删除实体(理由可选)。删除前快照入 memory_corrections,失败可回滚。"""
        from app.repositories.memory_correction_repository import (
            MemoryCorrectionRepository,
        )
        from app.repositories.neo4j.memory_graph_repository import (
            MemoryGraphRepository,
        )

        uid = str(user_id)
        repo = MemoryGraphRepository()
        before = await repo.entity_snapshot(uid, entity_id) or {}
        # 先落 PG 再删 Neo4j —— 若 PG 失败则不删,避免「数据没了又没记录」
        try:
            await MemoryCorrectionRepository(self.session).record(
                user_id=user_id,
                entity_id=entity_id,
                action="delete",
                before=_serializable(before),
                reason=reason or "用户删除",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("delete 落库失败,放弃删除: %s", e)
            return {"ok": False, "error": "落库失败,已取消删除"}
        await repo.delete_entity(uid, entity_id)
        return {"ok": True, "entity_id": entity_id}

    async def list_communities(self, user_id: uuid.UUID) -> list[dict]:
        """社区列表（名称/摘要/成员数）。"""
        from app.repositories.neo4j.community_repository import CommunityRepository

        return await CommunityRepository().list_communities(str(user_id))

    async def community_members(
        self, user_id: uuid.UUID, community_id: str
    ) -> list[dict]:
        """某社区的成员实体。"""
        from app.repositories.neo4j.community_repository import CommunityRepository

        members = await CommunityRepository().get_members(str(user_id), community_id)
        return [
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "type": m.get("type"),
                "description": m.get("description") or "",
                "aliases": m.get("aliases") or [],
            }
            for m in members
        ]

    async def recluster(self, user_id: uuid.UUID) -> None:
        """手动触发全量社区聚类（先合并历史重复实体，再聚类）。"""
        from app.core.llm.resolver import get_optional_client_for_type
        from app.core.memory.clustering.label_propagation import (
            LabelPropagationEngine,
        )

        await self.merge_duplicates(user_id)
        chat_client = await get_optional_client_for_type(self.session, user_id, "chat")
        await LabelPropagationEngine(chat_client=chat_client).full_clustering(
            str(user_id)
        )

    async def merge_duplicates(self, user_id: uuid.UUID) -> int:
        """合并历史重复实体（同名同类型只保留一个图节点）。"""
        from app.repositories.neo4j.memory_graph_repository import (
            MemoryGraphRepository,
        )

        return await MemoryGraphRepository().merge_duplicate_entities(str(user_id))

    async def consolidate(self, user_id: uuid.UUID) -> dict:
        """手动触发记忆巩固（短期→长期 + 画像增强）。"""
        from app.core.llm.resolver import get_optional_client_for_type
        from app.core.memory.consolidation.consolidator import ConsolidationEngine

        chat_client = await get_optional_client_for_type(self.session, user_id, "chat")
        return await ConsolidationEngine(chat_client=chat_client).run(str(user_id))

    async def reflect(self, user_id: uuid.UUID) -> dict:
        """手动触发反思：归纳高层洞察 Insight。"""
        from app.core.llm.resolver import get_optional_client_for_type
        from app.core.memory.reflection.reflector import ReflectionEngine

        chat_client = await get_optional_client_for_type(self.session, user_id, "chat")
        embed_client = await get_optional_client_for_type(
            self.session, user_id, "embedding"
        )
        return await ReflectionEngine(
            chat_client=chat_client, embed_client=embed_client
        ).run(str(user_id))

    async def list_insights(self, user_id: uuid.UUID) -> list[dict]:
        """列出用户的高层洞察（AI 对你的理解）。"""
        from app.repositories.neo4j.memory_graph_repository import (
            MemoryGraphRepository,
        )

        rows = await MemoryGraphRepository().list_insights(str(user_id))
        return [
            {
                "id": r.get("id"),
                "theme": r.get("theme") or "",
                "content": r.get("content") or "",
                "importance": r.get("importance", 0.6),
                "confidence": r.get("confidence", 0.7),
                "source_count": r.get("source_count", 0),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            }
            for r in rows
        ]

    async def delete_insight(self, user_id: uuid.UUID, insight_id: str) -> None:
        """删除单条洞察。"""
        from app.repositories.neo4j.memory_graph_repository import (
            MemoryGraphRepository,
        )

        await MemoryGraphRepository().delete_insight(str(user_id), insight_id)

    async def get_graph(self, user_id: uuid.UUID) -> dict:
        """知识图谱全量数据：nodes（五类节点）+ edges（溯源/语义边）+ communities。"""
        from app.repositories.neo4j.community_repository import CommunityRepository
        from app.repositories.neo4j.memory_graph_repository import (
            MemoryGraphRepository,
        )

        uid = str(user_id)
        repo = MemoryGraphRepository()
        raw_nodes = await repo.graph_full_nodes(uid)
        raw_edges = await repo.graph_full_edges(uid)
        communities = await CommunityRepository().list_communities(uid)

        def _disp_name(kind: str, name: str | None) -> str:
            text = (name or "").strip().replace("\n", " ")
            if kind in ("Entity", "Event"):
                return text
            # 溯源类节点（对话/片段/陈述）名称可能很长，截断用于标签显示
            return text[:24] + ("…" if len(text) > 24 else "")

        nodes = [
            {
                "id": n.get("id"),
                "kind": n.get("kind") or "Entity",
                "name": _disp_name(n.get("kind") or "Entity", n.get("name")),
                "type": n.get("type"),
                "description": n.get("description") or "",
                "community_id": n.get("community_id"),
                "importance": n.get("importance", 0.5),
                "memory_layer": n.get("memory_layer") or "short_term",
                "access_count": n.get("access_count", 0),
                "mention_count": n.get("mention_count", 1),
                "aliases": n.get("aliases") or [],
                "core_facts": n.get("core_facts") or [],
                "traits": n.get("traits") or [],
            }
            for n in raw_nodes
        ]
        edges = [
            {
                "source": e.get("source"),
                "target": e.get("target"),
                "rel": e.get("rel") or "",
                "predicate": e.get("predicate") or "",
                "predicate_surface": e.get("predicate_surface") or "",
            }
            for e in raw_edges
            if e.get("source") and e.get("target")
        ]
        return {
            "nodes": nodes,
            "edges": edges,
            "communities": communities,
        }

    async def get_entity_subgraph(self, user_id: uuid.UUID, entity_id: str) -> dict:
        """单实体一跳子图。"""
        from app.repositories.neo4j.memory_graph_repository import (
            MemoryGraphRepository,
        )

        raw_nodes, raw_edges = await MemoryGraphRepository().entity_subgraph(
            str(user_id), entity_id
        )
        nodes = [
            {
                "id": n.get("id"),
                "name": n.get("name"),
                "type": n.get("type"),
                "description": n.get("description") or "",
                "community_id": n.get("community_id"),
            }
            for n in raw_nodes
        ]
        edges = [
            {
                "source": e.get("source"),
                "target": e.get("target"),
                "predicate": e.get("predicate") or "",
                "predicate_surface": e.get("predicate_surface") or "",
            }
            for e in raw_edges
            if e.get("source") and e.get("target")
        ]
        return {"center": entity_id, "nodes": nodes, "edges": edges}

    async def get_timeline(self, user_id: uuid.UUID) -> list[dict]:
        """事件时间线（按 event_time 倒序）。"""
        from app.repositories.neo4j.memory_graph_repository import (
            MemoryGraphRepository,
        )

        rows = await MemoryGraphRepository().event_timeline(str(user_id))
        return [
            {
                "id": r.get("id"),
                "title": r.get("title"),
                "description": r.get("description") or "",
                "event_time": r.get("event_time"),
                "created_at": r.get("created_at"),
                "participants": r.get("participants") or [],
            }
            for r in rows
        ]

    @staticmethod
    def to_out_dict(memory: Memory) -> dict:
        return {
            "id": str(memory.id),
            "raw_text": memory.raw_text,
            "source": memory.source,
            "status": memory.status,
            "error_msg": memory.error_msg,
            "graph_stats": memory.graph_stats,
            "created_at": memory.created_at.isoformat() if memory.created_at else None,
        }



# ── 工具:把 Neo4j 返回的对象转成可 JSON 序列化的 dict ──

def _serializable(snapshot: dict) -> dict:
    """Neo4j DateTime / Date 等转字符串,保证 JSONB 写入不炸。"""
    out: dict = {}
    for k, v in (snapshot or {}).items():
        if hasattr(v, "to_native"):
            try:
                out[k] = v.to_native().isoformat()
            except Exception:  # noqa: BLE001
                out[k] = str(v)
        elif isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, list):
            out[k] = [
                x if isinstance(x, (str, int, float, bool)) else str(x)
                for x in v
            ]
        else:
            out[k] = str(v)
    return out
