"""L3 多跳推理基准 —— HotpotQA distractor。

公共数据集对照：每题给 10 段文字（2 段含答案 + 8 段干扰），系统要先「检索 + 多跳推理」答出。
验证我们「深度研究多跳子问题分解」与 ② Verifier 的有效性。
"""
from eval.benchmarks.hotpotqa.runner import run_benchmark

__all__ = ["run_benchmark"]
