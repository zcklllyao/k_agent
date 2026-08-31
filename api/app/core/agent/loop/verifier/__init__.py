"""Verifier:独立 LLM-as-judge,按 Rubric 给 artifact 打分。

核心设计:Verify ⊥ Generate —— Verifier 必须用独立 session,不能带 Generator 的上下文。
避免「同上下文里模型已被自己说服了再问它『做对了吗』会无脑说『对』」这种自夸偏见。

两套实现:
- SameModelVerifier (kind="same") : 同 chat 模型新开 session + critic 角色 prompt (基线)
- CrossModelVerifier (kind="cross"): 用单独配置的 verifier 模型,跨 family 避免同模型盲点

A/B 实验在 HotpotQA 上跑出真实数据证明哪种更好(简历卖点)。
"""
from app.core.agent.loop.verifier.base import Verifier
from app.core.agent.loop.verifier.llm_verifier import (
    CrossModelVerifier,
    SameModelVerifier,
    build_verifier,
)

__all__ = ["Verifier", "SameModelVerifier", "CrossModelVerifier", "build_verifier"]
