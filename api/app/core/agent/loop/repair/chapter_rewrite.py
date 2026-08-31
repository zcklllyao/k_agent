"""ChapterRewrite:章节重写修复。

适用问题:论证深度 / 相关性烂(verifier feedback 里 weak_chapters 有内容,或 issues 里有 depth/relevance 维度)。

思路:
1. 从 feedback 定位「哪些章节差」
2. 通过 ctx["rewrite_callback"](chapters) -> awaitable[new_artifact] 让上层(research engine)
   把这些章节扔回 writer 重写,合并进原 artifact 替换原章节
3. 比贪心补丁重,但能修结构性问题

loop 模块本身不依赖 research engine,通过 callback 解耦。
"""
from __future__ import annotations

from typing import Any

from app.core.agent.loop.models import RepairAction, VerifyScore
from app.core.agent.loop.repair.base import RepairExecutor
from app.core.logging import get_logger

logger = get_logger(__name__)


class ChapterRewrite(RepairExecutor):
    """章节级重写修复(默认每轮最多重写 2 章,控成本)。"""

    kind = "chapter_rewrite"

    def __init__(self, max_chapters: int = 2):
        self.max_chapters = max_chapters

    def plan(
        self, *, score: VerifyScore, artifact: dict[str, Any]
    ) -> RepairAction:
        """从 feedback 找差章节,与现有 headings 求交集(防止 verifier 编出来的章节名)。"""
        fb = score.feedback or {}
        headings_set = {h.strip() for h in (artifact.get("headings") or []) if h}
        candidates: list[str] = []

        # 1) feedback.weak_chapters 直接列出来
        for h in (fb.get("weak_chapters") or []):
            if isinstance(h, str) and h.strip() in headings_set:
                candidates.append(h.strip())

        # 2) issues 里 dim=depth/relevance 的,从 detail 文本中匹配现有 headings
        for it in (fb.get("issues") or []):
            if not isinstance(it, dict):
                continue
            dim = (it.get("dim") or "").lower()
            detail = (it.get("detail") or "")
            if dim in {"depth", "relevance"}:
                for h in headings_set:
                    if h and h in detail and h not in candidates:
                        candidates.append(h)

        candidates = candidates[: self.max_chapters]
        rationale = (
            f"verifier 指出 {len(fb.get('weak_chapters') or [])} 章论证薄弱,"
            f"重写其中 {len(candidates)} 章(超出上限的轮到下一轮再修)。"
        )
        return RepairAction(
            kind=self.kind,
            rewrite_chapters=candidates,
            rationale=rationale,
        )

    async def execute(
        self,
        *,
        action: RepairAction,
        artifact: dict[str, Any],
        ctx: dict[str, Any],
    ) -> dict[str, Any]:
        """调上层注入的 rewrite_callback 完成实际章节重写。"""
        callback = ctx.get("rewrite_callback")
        if callback is None or not action.rewrite_chapters:
            logger.warning(
                "ChapterRewrite.execute: 未提供 rewrite_callback 或无差章节,返回原 artifact"
            )
            return artifact
        try:
            new_artifact = await callback(action.rewrite_chapters)
            if not isinstance(new_artifact, dict):
                logger.warning("rewrite_callback 未返回 dict,沿用旧 artifact")
                return artifact
            return new_artifact
        except Exception as e:  # noqa: BLE001
            logger.warning("ChapterRewrite 执行失败,沿用旧 artifact: %s", e)
            return artifact
