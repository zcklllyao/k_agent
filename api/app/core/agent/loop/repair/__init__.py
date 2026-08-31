"""Repair 策略:把 Verifier 的 feedback 翻译成 Generator 可消费的修复动作。

按问题严重程度三档自动选(由 policy.py 决策):
- PatchRepair(贪心补丁):仅覆盖/引用/时效问题 → 喂 reflector 补搜补写
- ChapterRewrite(章节重写):论证深度/相关性烂 → 扔回 writer 重写差章节
- ForceExceed(强制停):多维全面烂 → 标 unverified 仍展示(避免越改越乱)
"""
from app.core.agent.loop.repair.base import RepairExecutor
from app.core.agent.loop.repair.chapter_rewrite import ChapterRewrite
from app.core.agent.loop.repair.patch_repair import PatchRepair

__all__ = ["RepairExecutor", "PatchRepair", "ChapterRewrite"]
