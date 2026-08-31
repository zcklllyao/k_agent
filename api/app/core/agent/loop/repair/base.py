"""Repair 抽象基类:把 verifier feedback + 当前 artifact → 新的 artifact。

子类决定具体怎么修(补搜 / 重写 / 兜底)。Controller 不关心实现,只看 RepairAction 描述。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.core.agent.loop.models import RepairAction, VerifyScore


class RepairExecutor(ABC):
    """Repair 策略的抽象执行器。"""

    kind: str = "base"  # patch / chapter_rewrite / force_exceed

    @abstractmethod
    def plan(
        self, *, score: VerifyScore, artifact: dict[str, Any]
    ) -> RepairAction:
        """根据评分与 feedback,规划要做的修复动作(不实际执行)。"""
        raise NotImplementedError

    @abstractmethod
    async def execute(
        self,
        *,
        action: RepairAction,
        artifact: dict[str, Any],
        ctx: dict[str, Any],
    ) -> dict[str, Any]:
        """执行修复,返回**新的 artifact**(下一轮 verify 的输入)。

        Args:
            action: 上一步 plan() 产出的动作
            artifact: 当前轮的 artifact
            ctx: 业务上下文,由 controller 透传(含 model / sources / planner 等供子类按需取用)
        Returns:
            新 artifact(结构同 base verifier 期望的)
        """
        raise NotImplementedError
