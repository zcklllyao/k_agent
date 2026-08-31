"""MemoryCorrection ORM 模型 —— PostgreSQL memory_corrections 表。

V0.0.5 ⑤ 记忆审查与人类反馈闭环:用户对 AI 萃取的低置信度实体做
confirm / correct / delete 三类操作时,本表结构化记录前后快照与原因。

价值:
- 审计可回滚(误删的实体能从 before 快照恢复)
- 给 V0.0.6 self-improvement loop 提供训练信号(LLM 从纠错记录中
  总结萃取 prompt 改进点)
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


# action 枚举
ACTION_CONFIRM = "confirm"   # 👍 确认正确(置信度提升 + 标 human_verified)
ACTION_CORRECT = "correct"   # ✏️ 修正(改名称/类型/描述)
ACTION_DELETE = "delete"     # 🗑 删除(软删 entity)


class MemoryCorrection(Base):
    """用户对记忆实体的人工纠错记录。"""

    __tablename__ = "memory_corrections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # 被操作的实体(Neo4j entity.id,String 不是 FK 因为跨库)
    entity_id: Mapped[str] = mapped_column(String(128), index=True)
    # 动作:confirm / correct / delete
    action: Mapped[str] = mapped_column(String(16), index=True)
    # 操作前的实体快照(name / type / description / aliases),用于回滚 + 给 V0.0.6 LLM 总结改进点
    before: Mapped[dict] = mapped_column(JSONB, default=dict)
    # 操作后的快照(correct 时非空;confirm/delete 可以为空字典或包含 human_verified=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # 用户填的原因(可选)或系统填的「确认/修正/删除」
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # 该记忆萃取自哪段对话(便于跳来源 + 用作训练信号)
    source_dialogue_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
