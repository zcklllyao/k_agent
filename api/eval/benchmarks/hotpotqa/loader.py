"""HotpotQA distractor 数据加载（HuggingFace `hotpot_qa`）。

数据集结构（distractor 配置）：
- question:       str
- answer:         str
- type:           "bridge" | "comparison"
- supporting_facts: {title: [...], sent_id: [...]}      —— 答案出处
- context:        {title: [...], sentences: [[...], ...]} —— 10 个段落（2 gold + 8 distractor）

我们用 dev 集做分层采样（按 bridge/comparison 比例），默认 500 条。
"""
from __future__ import annotations

from typing import TypedDict

from eval.benchmarks._common import cache_path, stratified_sample


class HotpotQuery(TypedDict):
    qid: str
    question: str
    answer: str
    qtype: str  # bridge | comparison
    gold_titles: list[str]
    paragraphs: list[dict]  # [{title, sentences:[str], is_gold:bool}, ...]


def load(n: int = 500, seed: int = 42) -> list[HotpotQuery]:
    """加载 HotpotQA distractor dev 集，分层采样 n 条。"""
    try:
        from datasets import load_dataset
    except ImportError as e:
        raise RuntimeError(
            "缺少 datasets 依赖。请在 api/ 下执行：uv sync"
        ) from e

    cache_dir = str(cache_path("hf_datasets").parent)
    # 用官方组织维护的 parquet 版本(原 hotpot_qa 用 loading script,新版 datasets 不再支持)
    ds = load_dataset(
        "hotpotqa/hotpot_qa", "distractor",
        cache_dir=cache_dir, split="validation",
    )
    queries: list[HotpotQuery] = []
    for row in ds:
        ctx = row["context"]  # {title: [...], sentences: [[str], ...]}
        titles = ctx["title"]
        sentences = ctx["sentences"]
        sf = row["supporting_facts"]
        gold_titles = list(set(sf["title"]))
        paragraphs = []
        for t, sents in zip(titles, sentences):
            paragraphs.append({
                "title": t,
                "sentences": list(sents),
                "is_gold": t in gold_titles,
            })
        queries.append({
            "qid": row["id"],
            "question": row["question"],
            "answer": row["answer"],
            "qtype": row["type"],
            "gold_titles": gold_titles,
            "paragraphs": paragraphs,
        })

    sampled = stratified_sample(queries, n, key=lambda q: q["qtype"], seed=seed)
    return sampled
