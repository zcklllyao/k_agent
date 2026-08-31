"""定时/主动任务请求 schema。"""
from pydantic import BaseModel, Field


class AgentTaskUpsertRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    instruction: str = Field(..., min_length=1, max_length=2000)
    kb_ids: list[str] | None = None
    trigger_type: str = Field("daily", pattern="^(daily|weekly|interval)$")
    trigger_time: str | None = None  # "HH:MM"（daily/weekly）
    trigger_weekday: int | None = Field(None, ge=0, le=6)  # 0=周一..6=周日（weekly）
    trigger_interval_hours: int | None = Field(None, ge=1, le=720)  # interval
    enabled: bool = True
    notify_enabled: bool = True  # 跑完是否推送到消息渠道
