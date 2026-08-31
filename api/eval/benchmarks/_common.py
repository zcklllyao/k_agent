"""benchmarks 共享 helpers:数据集采样、报告/明细写盘、LLM-as-judge 解析等。

各 benchmark runner 共用,避免重复造轮子。

报告/明细按 benchmark 类型(rag / memory)落到对应子目录,方便查阅:
- results/rag/      L2 中文检索 / L3 端到端 RAG(多跳)
- results/memory/   L4 长对话记忆
- results/          L1 自制集汇总(覆盖 RAG + 记忆 + 抽取 + 去重,不拆)
"""
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Iterable, TypeVar

from eval.benchmarks import CACHE_DIR

T = TypeVar("T")

_RESULTS_DIR = Path(__file__).parent.parent / "results"
_RESULTS_DIR.mkdir(exist_ok=True)


def ts() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _category_dir(category: str | None) -> Path:
    """按 benchmark 类型(rag / memory / None)落到子目录:
    - 'rag'     → results/rag/
    - 'memory'  → results/memory/
    - None      → results/(根,L1 自制集汇总用)
    """
    if not category:
        return _RESULTS_DIR
    sub = _RESULTS_DIR / category
    sub.mkdir(exist_ok=True)
    return sub


def write_benchmark_report(
    benchmark: str, title: str, table: dict, meta: dict | None = None,
    extra_notes: list[str] | None = None,
    category: str | None = None,
) -> Path:
    """单 benchmark 报告 Markdown:标题 + 元信息 + 指标表 + 备注。

    category 决定落到 results/{rag,memory}/ 还是根目录。
    """
    lines = [
        f"# {title} 评测报告 {ts()}",
        "",
    ]
    if meta:
        lines.append("**评测元信息**")
        for k, v in meta.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
    if extra_notes:
        for n in extra_notes:
            lines.append(f"> {n}")
        lines.append("")

    if not table:
        lines.append("(无数据)")
    else:
        metric_names = list(next(iter(table.values())).keys())
        lines.append("| 配置 | " + " | ".join(metric_names) + " |")
        lines.append("|" + "---|" * (len(metric_names) + 1))
        for row, m in table.items():
            lines.append(f"| {row} | " + " | ".join(str(m.get(k, "")) for k in metric_names) + " |")
    path = _category_dir(category) / f"report-{benchmark}-{ts()}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_benchmark_details(
    benchmark: str, details: list, category: str | None = None,
) -> Path:
    """单 benchmark 明细 JSON,与报告同目录。"""
    path = _category_dir(category) / f"details-{benchmark}-{ts()}.json"
    path.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def stratified_sample(
    items: list[T],
    n: int,
    key: callable,
    seed: int = 42,
) -> list[T]:
    """分层采样:按 `key(item)` 分组后按原比例采样总数 n 条。

    比纯随机更稳定(不至于某类型为零)。seed 固定保证可复现。
    """
    if n >= len(items):
        return items
    rng = random.Random(seed)
    groups: dict = {}
    for it in items:
        groups.setdefault(key(it), []).append(it)
    total = len(items)
    out: list[T] = []
    for grp, lst in groups.items():
        rng.shuffle(lst)
        # 按比例分配,至少取 1(避免小类被采到 0)
        take = max(1, round(n * len(lst) / total))
        out.extend(lst[:take])
    rng.shuffle(out)
    return out[:n]


def cache_path(*parts: str) -> Path:
    """benchmark 的本地缓存路径(在 CACHE_DIR 下)。"""
    p = CACHE_DIR.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def chunked(items: list[T], size: int) -> Iterable[list[T]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]
