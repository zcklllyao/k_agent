"""研究报告分享请求 schema。"""
from pydantic import BaseModel, Field


class ReportShareCreateRequest(BaseModel):
    """生成/刷新报告分享。"""

    title: str | None = Field(default=None, max_length=256)  # 自定义标题，空=用报告标题
    expire_days: int | None = Field(default=None, ge=1, le=3650)  # 过期天数，空=永久
