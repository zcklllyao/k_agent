"""Policy:Verifier Loop 的决策器。

输入:VerifyScore + 当前迭代信息(轮次 / 上限) + Rubric
输出:决策(pass / retry_patch / retry_rewrite / exceed)+ 选用的 RepairExecutor

设计取舍(每条都对应面试讲点):
- 不是「不通过就重做」,按问题严重程度自动选最经济的修复
- 多维全面烂(≥3 维不达硬门槛)→ ForceExceed,避免越改越乱
- 上限默认 2 轮(token vs 收益取舍;N 轮内 70%+ 问题能在 Patch 阶段补完)
"""
from __future__ import annotations

from app.core.agent.loop.models import (
    DECISION_EXCEED,
    DECISION_PASS,
    DECISION_RETRY_PATCH,
    DECISION_RETRY_REWRITE,
    RubricDef,
    VerifyScore,
)
from app.core.agent.loop.repair import ChapterRewrite, PatchRepair, RepairExecutor
from app.core.logging import get_logger

logger = get_logger(__name__)

# 一旦 ≥ 这么多维度同时未达硬门槛,认为「全面烂」,直接 ForceExceed
_FULL_FAILURE_THRESHOLD = 6

# 这些维度的单点缺漏归 Patch 处理
_PATCH_DIMS = {"coverage", "faithfulness", "timeliness"}
# 这些维度的差归 ChapterRewrite 处理
_REWRITE_DIMS = {"depth", "relevance"}

# After repair attempts, minor citation/timeliness/readability issues are warnings.
# Coverage and relevance remain hard gates so an off-topic or materially incomplete
# report is not silently published.
_SOFT_PASS_THRESHOLD = 0.45
_HARD_DIMS = {"coverage", "relevance"}


class Policy:
    """决策器:输入评分输出动作 + 修复执行器。"""

    def __init__(
        self,
        *,
        patch_repair: PatchRepair | None = None,
        chapter_rewrite: ChapterRewrite | None = None,
        full_failure_threshold: int = _FULL_FAILURE_THRESHOLD,
    ):
        self.patch_repair = patch_repair or PatchRepair()
        self.chapter_rewrite = chapter_rewrite or ChapterRewrite()
        self.full_failure_threshold = full_failure_threshold

    def decide(
        self,
        *,
        score: VerifyScore,
        rubric: RubricDef,
        iteration_no: int,
        max_iterations: int,
    ) -> tuple[str, RepairExecutor | None]:
        """决策一轮迭代后下一步做什么。

        Returns:
            (decision, executor):
                decision: DECISION_* 常量
                executor: retry_* 时为对应的 RepairExecutor;其他 None
        """
        # 1. 通过判定:加权总分 ≥ 阈值 且 所有单维 ≥ 硬门槛
        failed_dims = rubric.failed_dims(score.raw_scores)
        if score.total >= rubric.pass_threshold and not failed_dims:
            return DECISION_PASS, None

        # 2. 已达迭代上限 → 强制停
        if iteration_no >= max_iterations:
            hard_failed = set(failed_dims) & _HARD_DIMS
            if score.total >= _SOFT_PASS_THRESHOLD and not hard_failed:
                logger.warning(
                    "Policy: repair limit reached; allowing a usable report with quality warnings "
                    "(score=%.3f, soft_failed=%s)",
                    score.total,
                    sorted(set(failed_dims) - _HARD_DIMS),
                )
                return DECISION_PASS, None
            return DECISION_EXCEED, None

        # 3. 多维全面烂 → 强制停(避免越改越乱)
        if len(failed_dims) >= self.full_failure_threshold:
            logger.info(
                "Policy: 多维全面烂(%d 维不达门槛),ForceExceed", len(failed_dims)
            )
            return DECISION_EXCEED, None

        # 4. 优先 ChapterRewrite:若有维度落在 _REWRITE_DIMS(论证深度 / 相关性),走章节重写
        if any(d in _REWRITE_DIMS for d in failed_dims):
            return DECISION_RETRY_REWRITE, self.chapter_rewrite

        # 5. 否则 PatchRepair(覆盖度 / 引用对齐 / 时效性 单点缺漏)
        if any(d in _PATCH_DIMS for d in failed_dims):
            return DECISION_RETRY_PATCH, self.patch_repair

        # 6. 总分不达但单维硬门槛都过(权重均匀偏低)→ 走 Patch 兜底
        return DECISION_RETRY_PATCH, self.patch_repair
