"""Verifier Loop ORM 模型 —— PostgreSQL loop_runs / loop_iterations 两张表。

V0.0.5 ② Loop Engineering 落地的状态外置层:
- `loop_runs`:一次完整 Loop(对应一份研究报告或一次定时任务结果)
- `loop_iterations`:Loop 内每一轮 generate→verify→decide 的详细记录

状态外置 = 进程崩了/worker 重启也能从 checkpoint 恢复;每轮回炉决策完整 audit trail。
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


# task_type 枚举(字符串而非 SQL enum,便于扩展未来场景)
TASK_TYPE_RESEARCH = "research"
TASK_TYPE_AGENT_TASK = "agent_task"

# status 枚举
STATUS_RUNNING = "running"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"      # 异常崩溃
STATUS_EXCEEDED = "exceeded"  # 超过最大迭代仍未通过

# decision 枚举(每轮迭代的决策)
DECISION_PASS = "pass"
DECISION_RETRY_PATCH = "retry_patch"
DECISION_RETRY_REWRITE = "retry_rewrite"
DECISION_EXCEED = "exceed"


class LoopRun(Base):
    """一次完整的 Verifier Loop。

    一份研究报告 / 一次定时任务输出 = 一个 LoopRun。所有迭代记录挂在它下面。
    """

    __tablename__ = "loop_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # 任务类型:research / agent_task / 未来扩展
    task_type: Mapped[str] = mapped_column(String(32), index=True)
    # 关联的业务 id(research_reports.id / agent_tasks.id);不加 FK 以解耦,业务删除不应级联清 loop
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    # 状态机:running / passed / failed / exceeded
    status: Mapped[str] = mapped_column(String(16), default=STATUS_RUNNING, index=True)
    # 迭代次数(实际跑了几轮 verify;通过/超限/失败都计入)
    iterations: Mapped[int] = mapped_column(Integer, default=0)
    # 最终加权总分(0~1)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 通过阈值与最大迭代数(快照,便于不同 run 间对比策略变化)
    pass_threshold: Mapped[float] = mapped_column(Float, default=0.7)
    max_iterations: Mapped[int] = mapped_column(Integer, default=2)

    # 模型审计:generator/verifier 用了什么模型(便于后续对比实验)
    generator_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verifier_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # verifier 配置:same(同模型 critic)/ cross(跨 family);A/B 实验时区分
    verifier_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # 用的 rubric 名(research / task / 未来扩展)
    rubric_name: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # 失败/超限时的简要原因(给前端展示)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class LoopIteration(Base):
    """LoopRun 内的一轮迭代:generate → verify → decide。"""

    __tablename__ = "loop_iterations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("loop_runs.id", ondelete="CASCADE"),
        index=True,
    )
    # 轮次序号(1 起)
    iteration_no: Mapped[int] = mapped_column(Integer)

    # artifact 摘要:不存全文(那会让表膨胀),存哈希 + 长度 + 引用数 + section 数等结构化字段
    # 全文在业务表(research_reports.content_md 等)里查
    artifact_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)

    # verifier 评分:{coverage:0.7, faithfulness:0.9, ...} + total
    scores: Mapped[dict] = mapped_column(JSONB, default=dict)
    # verifier 给的具体问题(供 repair 消费;含 missing_coverage / wrong_citations / weak_chapters 等)
    feedback: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 决策:pass / retry_patch / retry_rewrite / exceed
    decision: Mapped[str] = mapped_column(String(16))
    # 本轮选的修复动作详情(retry_* 时非空;含 patch queries / 重写章节列表 等)
    repair_action: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # 本轮耗时(毫秒,含 generate + verify;repair 算在下一轮的 generate)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
