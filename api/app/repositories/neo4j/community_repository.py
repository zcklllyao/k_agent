"""社区聚类数据访问层：Community 节点的 upsert / 实体归属 / 成员查询 / 元数据。

只做数据存取，聚类算法在 core/memory/clustering 里。
"""
from datetime import datetime
from typing import Any

from app.db.neo4j import get_driver
from app.repositories.neo4j import cypher_queries as cq


class CommunityRepository:
    def __init__(self):
        self._driver = get_driver()

    async def has_communities(self, user_id: str) -> bool:
        async with self._driver.session() as session:
            result = await session.run(cq.COMMUNITY_EXISTS, user_id=user_id)
            record = await result.single()
            return bool(record and record["cnt"] > 0)

    async def list_entities_with_embedding(self, user_id: str) -> list[dict[str, Any]]:
        async with self._driver.session() as session:
            result = await session.run(cq.ENTITY_IDS_WITH_EMBEDDING, user_id=user_id)
            return [dict(r) async for r in result]

    async def neighbors_for_vote(
        self, user_id: str, entity_ids: list[str]
    ) -> dict[str, list[dict]]:
        """返回 {entity_id: [邻居(含 community_id/name_embedding), ...]}。"""
        async with self._driver.session() as session:
            result = await session.run(
                cq.ENTITY_NEIGHBORS_FOR_VOTE, user_id=user_id, entity_ids=entity_ids
            )
            out: dict[str, list[dict]] = {}
            async for r in result:
                out.setdefault(r["entity_id"], []).append(
                    {
                        "id": r["id"],
                        "community_id": r["community_id"],
                        "name_embedding": r["name_embedding"],
                    }
                )
            return out

    async def upsert_community(self, user_id: str, community_id: str) -> None:
        async with self._driver.session() as session:
            await session.run(
                cq.COMMUNITY_UPSERT,
                user_id=user_id,
                community_id=community_id,
                created_at=datetime.now().isoformat(),
            )

    async def assign_entity(
        self, user_id: str, entity_id: str, community_id: str
    ) -> None:
        async with self._driver.session() as session:
            await session.run(
                cq.ENTITY_ASSIGN_COMMUNITY,
                user_id=user_id,
                entity_id=entity_id,
                community_id=community_id,
            )

    async def refresh_member_count(self, user_id: str, community_id: str) -> int:
        async with self._driver.session() as session:
            result = await session.run(
                cq.COMMUNITY_REFRESH_COUNT, user_id=user_id, community_id=community_id
            )
            record = await result.single()
            return record["cnt"] if record else 0

    async def get_members(self, user_id: str, community_id: str) -> list[dict[str, Any]]:
        async with self._driver.session() as session:
            result = await session.run(
                cq.COMMUNITY_MEMBERS, user_id=user_id, community_id=community_id
            )
            return [dict(r) async for r in result]

    async def get_relationships(
        self, user_id: str, community_id: str
    ) -> list[dict[str, Any]]:
        async with self._driver.session() as session:
            result = await session.run(
                cq.COMMUNITY_RELATIONSHIPS, user_id=user_id, community_id=community_id
            )
            return [dict(r) async for r in result]

    async def update_metadata(
        self, user_id: str, community_id: str, name: str, summary: str
    ) -> None:
        async with self._driver.session() as session:
            await session.run(
                cq.COMMUNITY_UPDATE_META,
                user_id=user_id,
                community_id=community_id,
                name=name,
                summary=summary,
            )

    async def list_communities(self, user_id: str) -> list[dict[str, Any]]:
        async with self._driver.session() as session:
            result = await session.run(cq.COMMUNITY_LIST, user_id=user_id)
            return [dict(r) async for r in result]

    async def prune_empty(self, user_id: str) -> None:
        async with self._driver.session() as session:
            await session.run(cq.COMMUNITY_PRUNE_EMPTY, user_id=user_id)
