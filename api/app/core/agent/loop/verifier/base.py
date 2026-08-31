"""Verifier 抽象基类。

子类必须实现 `verify()`,返回 VerifyScore(原始分 + 加权总分 + 结构化反馈)。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.core.agent.loop.models import RubricDef, VerifyScore


class Verifier(ABC):
    """Verifier 抽象:接收 artifact + rubric → 输出 VerifyScore。"""

    # 标识 verifier 类型,落库到 loop_runs.verifier_kind(同模型基线 / 跨模型异源)
    kind: str = "base"
    # 标识 verifier 使用的 LLM 模型名(可选,落库到 loop_runs.verifier_model)
    model_name: str = ""

    @abstractmethod
    async def verify(
        self,
        *,
        topic: str,
        artifact: dict[str, Any],
        rubric: RubricDef,
    ) -> VerifyScore:
        """对 artifact 评分。

        Args:
            topic: 任务主题(深度研究的题目 / 定时任务的研究指令)
            artifact: 待评产物。结构由 controller 提供,通用约定:
                {
                    "title": str,
                    "markdown": str,          # 完整报告 markdown
                    "sources": [{index, title, url}, ...],
                    "headings": [str, ...],   # 大纲章节(供覆盖度评估)
                }
            rubric: 评分规则(维度 + 权重 + 阈值)
        Returns:
            VerifyScore: 原始分 + 加权总分 + 结构化反馈
        """
        raise NotImplementedError
