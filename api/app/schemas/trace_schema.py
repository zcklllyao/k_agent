"""Trace / Span 接口的 Pydantic schema。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SpanItem(BaseModel):
    """单个 span(用于详情页的时间线视图)。"""
    model_config = ConfigDict(from_attributes=True)

    span_id: uuid.UUID
    parent_span_id: uuid.UUID | None
    trace_id: uuid.UUID
    span_type: str
    name: str
    status: str
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    model_name: str | None
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_cny: float
    payload: dict[str, Any]
    attributes: dict[str, Any]
    iteration_id: uuid.UUID | None


class TraceListItem(BaseModel):
    """列表行(精简字段,前端列表页用)。"""
    model_config = ConfigDict(from_attributes=True)

    trace_id: uuid.UUID
    task_type: str
    task_id: uuid.UUID | None
    task_name: str | None
    status: str
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    total_input_tokens: int
    total_output_tokens: int
    total_cached_tokens: int
    total_cost_cny: float
    models_used: list[str]
    loop_run_id: uuid.UUID | None


class TraceListResponse(BaseModel):
    total: int
    items: list[TraceListItem]


class TraceDetail(BaseModel):
    """详情(列表行字段 + span 列表)。"""
    model_config = ConfigDict(from_attributes=True)

    trace_id: uuid.UUID
    task_type: str
    task_id: uuid.UUID | None
    task_name: str | None
    status: str
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    total_input_tokens: int
    total_output_tokens: int
    total_cached_tokens: int
    total_cost_cny: float
    models_used: list[str]
    loop_run_id: uuid.UUID | None
    root_span_id: uuid.UUID | None
    attributes: dict[str, Any]
    spans: list[SpanItem]


class CostSummary(BaseModel):
    """成本聚合(仪表盘成本面板用)。"""
    days: int
    total_traces: int
    total_input_tokens: int
    total_output_tokens: int
    total_cached_tokens: int
    total_cost_cny: float
    by_task_type: list[dict[str, Any]]
    by_model: list[dict[str, Any]]
