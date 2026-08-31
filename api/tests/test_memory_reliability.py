import unittest
import uuid

from app.core.memory.retrieval.searcher import _rank_memory_hits, format_memory_context
from app.services.memory_service import MemoryService


class MemoryReliabilityRankingTests(unittest.TestCase):
    def test_filters_entities_below_min_confidence(self):
        hits = {
            "low": {"id": "low", "name": "低置信", "confidence": 0.4, "memory_layer": "short_term"},
            "high": {"id": "high", "name": "高置信", "confidence": 0.9, "memory_layer": "short_term"},
        }
        semantic_scores = {"low": 0.95, "high": 0.7}

        ranked = _rank_memory_hits(
            hits,
            semantic_scores,
            top_k=10,
            min_confidence=0.6,
            use_reliability_score=True,
        )

        self.assertEqual([item[0] for item in ranked], ["high"])

    def test_high_confidence_ranks_before_low_confidence_when_semantic_score_ties(self):
        hits = {
            "low": {"id": "low", "name": "低置信", "confidence": 0.65, "memory_layer": "short_term"},
            "high": {"id": "high", "name": "高置信", "confidence": 0.95, "memory_layer": "short_term"},
        }
        semantic_scores = {"low": 0.8, "high": 0.8}

        ranked = _rank_memory_hits(
            hits,
            semantic_scores,
            top_k=10,
            min_confidence=0.6,
            use_reliability_score=True,
        )

        self.assertEqual([item[0] for item in ranked], ["high", "low"])

    def test_long_term_ranks_before_short_term_when_score_and_confidence_tie(self):
        hits = {
            "short": {"id": "short", "name": "短期", "confidence": 0.8, "memory_layer": "short_term"},
            "long": {"id": "long", "name": "长期", "confidence": 0.8, "memory_layer": "long_term"},
        }
        semantic_scores = {"short": 0.8, "long": 0.8}

        ranked = _rank_memory_hits(
            hits,
            semantic_scores,
            top_k=10,
            min_confidence=0.6,
            use_reliability_score=True,
        )

        self.assertEqual([item[0] for item in ranked], ["long", "short"])

    def test_ranked_items_keep_semantic_score_and_add_reliability_score(self):
        hits = {
            "a": {"id": "a", "name": "A", "confidence": 0.5, "memory_layer": "long_term"},
        }
        semantic_scores = {"a": 0.8}

        ranked = _rank_memory_hits(
            hits,
            semantic_scores,
            top_k=10,
            min_confidence=None,
            use_reliability_score=True,
        )

        _, score, reliability_score = ranked[0]
        self.assertEqual(score, 0.8)
        self.assertAlmostEqual(reliability_score, 0.8 * 0.5 * 1.1)


class MemoryContextFormattingTests(unittest.TestCase):
    def test_low_confidence_entity_and_relation_are_marked_uncertain(self):
        context = format_memory_context(
            [
                {
                    "name": "爵士乐",
                    "type": "兴趣",
                    "description": "用户可能喜欢爵士乐",
                    "confidence": 0.7,
                    "relations": [
                        {"predicate": "偏好", "object_name": "夜间播放列表", "confidence": 0.7}
                    ],
                }
            ]
        )

        self.assertIn("待确认", context)
        self.assertIn("爵士乐", context)
        self.assertIn("夜间播放列表", context)

    def test_high_confidence_entity_is_not_marked_uncertain(self):
        context = format_memory_context(
            [
                {
                    "name": "Python",
                    "type": "技能",
                    "description": "用户熟悉 Python",
                    "confidence": 0.9,
                    "relations": [],
                }
            ]
        )

        self.assertNotIn("待确认", context)
        self.assertIn("Python", context)


class MemoryProfileConfidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_profile_includes_entity_and_relation_confidence(self):
        service = MemoryService(session=None)  # type: ignore[arg-type]
        user_id = uuid.uuid4()

        class _Repo:
            async def list_all_entities(self, user_id_text: str) -> list[dict]:
                self.user_id_text = user_id_text
                return [
                    {
                        "id": "entity-1",
                        "name": "爵士乐",
                        "type": "兴趣",
                        "description": "用户可能喜欢爵士乐",
                        "confidence": 0.7,
                        "relations": [
                            {
                                "predicate": "偏好",
                                "object_name": "夜间播放列表",
                                "object_type": "歌单",
                                "confidence": 0.65,
                            }
                        ],
                    }
                ]

            async def entity_type_counts(self, user_id_text: str) -> list[dict]:
                return [{"type": "兴趣", "cnt": 1}]

        repo = _Repo()
        service._memory_graph_repo_factory = lambda: repo

        profile = await service.get_profile(user_id)
        entity = profile["groups"][0]["entities"][0]

        self.assertEqual(entity["confidence"], 0.7)
        self.assertEqual(entity["relations"][0]["confidence"], 0.65)


if __name__ == "__main__":
    unittest.main()
