"""PatchRepair:贪心补丁修复。

适用问题:覆盖度 / 引用对齐 / 时效性单点缺漏(verifier feedback 里 missing_coverage / wrong_citations 有内容)。

思路:
1. 从 feedback 提取「缺什么/错什么」→ 生成补充检索子查询
2. 通过 ctx 里的回调 `ctx["patch_callback"](queries) -> awaitable[new_artifact]` 让上层(research engine)
   执行真正的补搜补写,合并进原 artifact
3. 不重写已有内容,只「贪心地」补充 → 成本低、收敛快

loop 模块本身不依赖 research engine,通过 callback 解耦。
"""
from __future__ import annotations

from typing import Any

from app.core.agent.loop.models import RepairAction, VerifyScore
from app.core.agent.loop.repair.base import RepairExecutor
from app.core.logging import get_logger

logger = get_logger(__name__)


class PatchRepair(RepairExecutor):
    """贪心补丁修复(默认每轮最多 3 个补搜查询,避免漫天补)。"""

    kind = "patch"

    def __init__(self, max_queries: int = 3):
        self.max_queries = max_queries

    def plan(
        self, *, score: VerifyScore, artifact: dict[str, Any]  # noqa: ARG002
    ) -> RepairAction:
        """从 verifier feedback 抽取「缺什么」→ 生成补搜子查询。"""
        fb = score.feedback or {}
        queries: list[str] = []

        # 1) 直接利用 missing_coverage(verifier 已经写成自然语言子问题)
        for item in (fb.get("missing_coverage") or []):
            if isinstance(item, str) and item.strip():
                queries.append(item.strip())

        # 2) 利用 issues 里维度为 coverage / faithfulness / timeliness 的具体问题
        for it in (fb.get("issues") or []):
            if not isinstance(it, dict):
                continue
            dim = (it.get("dim") or "").lower()
            detail = (it.get("detail") or "").strip()
            if not detail:
                continue
            if dim in {"coverage", "faithfulness", "timeliness"}:
                queries.append(detail)

        # 3) 引用错位:对每个错引用号生成一个「核对来源 X」的查询(粗糙但实用)
        for sid in (fb.get("wrong_citations") or []):
            try:
                queries.append(f"核对来源 {int(sid)} 的关键事实")
            except (TypeError, ValueError):
                continue

        # 去重 + 截断
        seen: set[str] = set()
        deduped: list[str] = []
        for q in queries:
            key = q[:120]
            if key in seen:
                continue
            seen.add(key)
            deduped.append(q)
        deduped = deduped[: self.max_queries]

        rationale = (
            f"verifier 指出 {len(fb.get('missing_coverage') or [])} 处覆盖缺漏 / "
            f"{len(fb.get('wrong_citations') or [])} 处引用错位,"
            f"选 {len(deduped)} 个最关键的补搜。"
        )
        return RepairAction(
            kind=self.kind,
            patch_queries=deduped,
            rationale=rationale,
        )

    async def execute(
        self,
        *,
        action: RepairAction,
        artifact: dict[str, Any],
        ctx: dict[str, Any],
    ) -> dict[str, Any]:
        """调上层注入的 patch_callback 完成实际补搜补写。"""
        callback = ctx.get("patch_callback")
        if callback is None or not action.patch_queries:
            logger.warning("PatchRepair.execute: 未提供 patch_callback 或无子查询,返回原 artifact")
            return artifact
        try:
            new_artifact = await callback(action.patch_queries)
            if not isinstance(new_artifact, dict):
                logger.warning("patch_callback 未返回 dict,沿用旧 artifact")
                return artifact
            return new_artifact
        except Exception as e:  # noqa: BLE001
            logger.warning("PatchRepair 执行失败,沿用旧 artifact: %s", e)
            return artifact
