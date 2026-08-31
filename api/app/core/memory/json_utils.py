"""LLM JSON 输出的健壮解析。

LLM（尤其中文模型）返回的 JSON 常见噪声：markdown 代码块包裹、首尾多余解释文本、
字符串内裸控制字符（换行/制表符）、尾随逗号、缺引号、未闭合截断等。

解析策略（从宽到稳）：
1. 剥离代码块、截取首尾大括号，去标准 json.loads(strict=False)；
2. 失败则交给 json_repair 修复（专治残缺/非法 JSON）；
3. 仍失败返回空 dict（调用方据此走兜底）。
"""
import json
from typing import Any

import json_repair

from app.core.logging import get_logger

logger = get_logger(__name__)


def _strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t[:4].lower() == "json":
            t = t[4:]
    return t.strip()


def parse_json_object(answer: str) -> dict[str, Any]:
    """从 LLM 文本中解析出 JSON 对象。失败返回空 dict。"""
    if not answer or not answer.strip():
        return {}
    text = _strip_fence(answer)
    start = text.find("{")
    end = text.rfind("}")
    snippet = text[start : end + 1] if (start != -1 and end > start) else text

    # 1) 标准解析（宽松，允许字符串内控制字符）
    try:
        data = json.loads(snippet, strict=False)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # 2) json_repair 修复（专治尾随逗号、缺引号、裸换行、截断未闭合等）
    try:
        repaired = json_repair.repair_json(snippet, return_objects=True)
        if isinstance(repaired, dict):
            return repaired
        # 修复结果可能是 list / 标量，非 dict 则视为失败
    except Exception as e:  # noqa: BLE001  json_repair 极少抛错，兜底记录
        logger.warning("json_repair 修复失败: %s", e)

    return {}


def parse_json_list(answer: str) -> list[Any]:
    """从 LLM 文本中解析出 JSON 数组。失败返回空 list。"""
    if not answer or not answer.strip():
        return []
    text = _strip_fence(answer)
    start = text.find("[")
    end = text.rfind("]")
    snippet = text[start : end + 1] if (start != -1 and end > start) else text

    try:
        data = json.loads(snippet, strict=False)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    try:
        repaired = json_repair.repair_json(snippet, return_objects=True)
        if isinstance(repaired, list):
            return repaired
    except Exception as e:  # noqa: BLE001
        logger.warning("json_repair 修复失败: %s", e)

    return []


__all__ = ["parse_json_object", "parse_json_list"]
