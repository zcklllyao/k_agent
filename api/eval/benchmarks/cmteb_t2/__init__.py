"""L2 中文检索基准 —— C-MTEB T2Retrieval。

公共数据集对照：以中文真实搜索场景为题，让我们的 `hybrid_search` 跑在标准 corpus 上，
出 nDCG@10 / Recall@10 / MRR@10，对照 bge-m3 等公认基线。
"""
from eval.benchmarks.cmteb_t2.runner import run_benchmark

__all__ = ["run_benchmark"]
