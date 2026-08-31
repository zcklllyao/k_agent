"""Verifier Loop 跨模块共享的 Pydantic 中间数据结构。

ORM 落库结构在 app.models.loop_model;这里是各模块间(rubric/verifier/repair/policy/controller)传递用的纯数据类,
与 ORM 解耦,便于序列化、单元测试。
"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


# ─────────── Rubric ───────────

class RubricDim(BaseModel):
    """Rubric 一个维度的定义。"""

    key: str                     # 内部 key,如 "coverage" / "faithfulness"
    label: str                   # 展示名,如 "覆盖度"
    weight: float                # 在总分里的权重
    threshold: float = 0.0       # 单维硬门槛,< 此值整体不通过(原始 0~5 分制)
    desc: str = ""               # 评分参考(给 verifier prompt 用)


class RubricDef(BaseModel):
    """一套 rubric 定义(研究 / 定时任务 / 未来扩展)。"""

    name: str                     # "research" / "task"
    dims: list[RubricDim]
    pass_threshold: float = 0.7   # 加权后总分通过线(归一到 0~1)
    raw_max: float = 5.0          # 单维原始分上限(verifier 输出按这个量纲)

    def normalize(self, raw: float) -> float:
        """单维原始分 → 归一到 [0,1]。"""
        if self.raw_max <= 0:
            return 0.0
        return max(0.0, min(1.0, raw / self.raw_max))

    def weighted_total(self, raw_scores: dict[str, float]) -> float:
        """按 weights 算加权总分(0~1)。"""
        total = 0.0
        for dim in self.dims:
            v = raw_scores.get(dim.key)
            if v is None:
                continue
            total += dim.weight * self.normalize(float(v))
        return round(total, 4)

    def failed_dims(self, raw_scores: dict[str, float]) -> list[str]:
        """返回单维硬门槛未达的维度 key 列表。"""
        out: list[str] = []
        for dim in self.dims:
            v = raw_scores.get(dim.key)
            if v is None:
                continue
            if float(v) < dim.threshold:
                out.append(dim.key)
        return out


# ─────────── Verifier ───────────

class VerifyScore(BaseModel):
    """Verifier 单次评分结果。"""

    raw_scores: dict[str, float] = Field(default_factory=dict)   # 维度 key → 0~raw_max 原始分
    total: float = 0.0                                            # 加权归一总分 0~1
    feedback: dict[str, Any] = Field(default_factory=dict)        # 结构化反馈,供 repair 消费
    # feedback 内常见字段(repair 会消费):
    #   - "issues": [{"dim":"coverage","detail":"第二章未提及 X"}, ...]
    #   - "missing_coverage": ["子问题 X 未回答", ...]
    #   - "wrong_citations": [3, 7]   引用错位的来源号
    #   - "weak_chapters": ["章节标题 A", ...]   论证差的章节
    #   - "summary": "总体讲...一句话评价"


# ─────────── Repair / Decision ───────────

DECISION_PASS = "pass"
DECISION_RETRY_PATCH = "retry_patch"
DECISION_RETRY_REWRITE = "retry_rewrite"
DECISION_EXCEED = "exceed"


class RepairAction(BaseModel):
    """Repair 策略产生的修复动作描述(落库 + 给 generator 消费)。"""

    kind: str                                       # patch / chapter_rewrite / force_exceed
    patch_queries: list[str] = Field(default_factory=list)        # PatchRepair 补搜的子查询
    rewrite_chapters: list[str] = Field(default_factory=list)     # ChapterRewrite 要重写的章节标题
    rationale: str = ""                              # 选这个动作的简要原因(给前端 audit)


# ─────────── Iteration outcome ───────────

class IterationOutcome(BaseModel):
    """单轮 generate→verify→decide 后的结果汇总(落库 + 上抛给 controller)。"""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)  # 提前生成,供 tracer 关联 iteration_id
    iteration_no: int
    artifact_snapshot: dict[str, Any] = Field(default_factory=dict)
    score: VerifyScore = Field(default_factory=VerifyScore)
    decision: str = DECISION_PASS                    # pass / retry_patch / retry_rewrite / exceed
    repair_action: RepairAction | None = None        # decision 为 retry_* 时非空
    duration_ms: int = 0


__all__ = [
    "RubricDim",
    "RubricDef",
    "VerifyScore",
    "RepairAction",
    "IterationOutcome",
    "DECISION_PASS",
    "DECISION_RETRY_PATCH",
    "DECISION_RETRY_REWRITE",
    "DECISION_EXCEED",
]
