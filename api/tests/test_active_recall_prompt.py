import unittest
import uuid
from unittest.mock import AsyncMock, patch

from app.core.memory.retrieval.active_recall import _do_recall


class _EmbedClient:
    async def embed_one(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class ActiveRecallPromptTests(unittest.IsolatedAsyncioTestCase):
    async def test_uncertain_memory_is_marked_as_pending_confirmation(self):
        with (
            patch("app.core.memory.retrieval.active_recall.MemoryGraphRepository") as repo_cls,
            patch("app.core.memory.retrieval.active_recall.search_memory", new_callable=AsyncMock) as search,
        ):
            repo_cls.return_value.search_insights_by_vector = AsyncMock(return_value=[])
            search.return_value = [
                {
                    "name": "爵士乐",
                    "description": "用户可能喜欢爵士乐",
                    "confidence": 0.7,
                    "relations": [
                        {"predicate": "偏好", "object_name": "夜间播放列表", "confidence": 0.7}
                    ],
                }
            ]

            block = await _do_recall(_EmbedClient(), uuid.uuid4(), "我喜欢听什么？")

        self.assertIn("待确认", block)
        self.assertIn("不要当作确定事实", block)
        search.assert_awaited_once()
        _, kwargs = search.await_args
        self.assertEqual(kwargs["min_confidence"], 0.6)
        self.assertTrue(kwargs["use_reliability_score"])

    async def test_high_confidence_memory_is_not_marked_uncertain(self):
        with (
            patch("app.core.memory.retrieval.active_recall.MemoryGraphRepository") as repo_cls,
            patch("app.core.memory.retrieval.active_recall.search_memory", new_callable=AsyncMock) as search,
        ):
            repo_cls.return_value.search_insights_by_vector = AsyncMock(return_value=[])
            search.return_value = [
                {
                    "name": "Python",
                    "description": "用户熟悉 Python",
                    "confidence": 0.92,
                    "relations": [],
                }
            ]

            block = await _do_recall(_EmbedClient(), uuid.uuid4(), "我会什么语言？")

        self.assertIn("Python", block)
        self.assertNotIn("待确认：Python", block)

    async def test_no_memory_lines_are_injected_when_search_filters_everything(self):
        with (
            patch("app.core.memory.retrieval.active_recall.MemoryGraphRepository") as repo_cls,
            patch("app.core.memory.retrieval.active_recall.search_memory", new_callable=AsyncMock) as search,
        ):
            repo_cls.return_value.search_insights_by_vector = AsyncMock(return_value=[])
            search.return_value = []

            block = await _do_recall(_EmbedClient(), uuid.uuid4(), "我喜欢听什么？")

        self.assertEqual(block, "")


if __name__ == "__main__":
    unittest.main()
