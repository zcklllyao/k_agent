"""评测总入口:读配置 → (① 自制集 或 ①.5 公共集) → 输出报告+明细 → (可选)清理。

用法:
    # ① 自制集(L1,默认)
    uv run python -m eval.run_eval                 # 全流程(模型自检 + setup + 全部评测,保留数据)
    uv run python -m eval.run_eval --reset         # 重跑:先清空旧数据再写入评测(推荐)
    uv run python -m eval.run_eval --skip-setup    # 跳过写入,直接评测(数据已写过)
    uv run python -m eval.run_eval --only retrieval # 只跑某项 retrieval/extraction/dedup/memory
    uv run python -m eval.run_eval --teardown      # 跑完清理评测数据

    # ①.5 公共评测基准(L2/L3)—— 默认轻量,跑通流程 + 出方向性数据
    uv run python -m eval.run_eval --benchmark cmteb-t2     # L2 中文检索(默认 corpus 1000/query 100,~10 分钟)
    uv run python -m eval.run_eval --benchmark hotpotqa     # L3 多跳推理(默认 100 题分层,~40 分钟)
    uv run python -m eval.run_eval --benchmark all          # 两套都跑(轻量默认)

    # 想放大就显式传(出更稳的简历数据)
    uv run python -m eval.run_eval --benchmark cmteb-t2 --corpus-limit 3000 --query-limit 300
    uv run python -m eval.run_eval --benchmark hotpotqa --sample 200

依赖:复制 eval/.env.eval.example 为 eval/.env.eval 并填模型 key(embedding 必需、chat 必需、rerank 可选)。
存储用 docker-compose 起的 PG/ES/Neo4j/Redis。
"""
import argparse
import asyncio

from app.config import settings

from eval import clients, eval_config, reporters
from eval.pipeline.setup import setup_all
from eval.pipeline.teardown import teardown
from eval.tasks import dedup as t_dedup
from eval.tasks import extraction as t_extraction
from eval.tasks import retrieval as t_retrieval


async def _check_models(embed, chat, rerank, need_chat: bool = True):
    """跑评测前先确认模型真的能调通,避免灌了一半数据才发现 key/url 错。

    embedding 必须可用(不通直接中止);chat 视任务需要(默认必需);
    rerank 可选,不通则打印告警并返回 None(评测自动跳过 rerank 对比)。
    返回最终可用的 rerank client(可能为 None)。
    """
    print("[check] 模型可用性自检…")

    # embedding(必需)—— 顺带校验维度是否与 ES 索引一致
    try:
        v = await embed.embed_one("评测连通性测试")
    except Exception as e:
        raise RuntimeError(f"embedding 模型不可用({embed.model_name}):{e}") from e
    dim = len(v)
    note = ""
    if dim != settings.embedding_dims:
        note = f"  ⚠ 维度 {dim} 与 ES 索引维度 {settings.embedding_dims} 不一致,检索会失败!请改 .env.eval 的 embedding 模型或 EMBEDDING_DIMS"
    print(f"  ✓ embedding 可用({embed.model_name},维度 {dim})")
    if note:
        print(note)

    # chat
    if need_chat:
        try:
            txt = await chat.chat([{"role": "user", "content": "回复两个字:可用"}], max_tokens=16)
        except Exception as e:
            raise RuntimeError(f"chat 模型不可用({chat.model_name}):{e}") from e
        print(f"  ✓ chat 可用({chat.model_name}):{(txt or '').strip()[:20]}")
    else:
        print("  - 当前 benchmark 不需要 chat 模型,跳过 chat 自检")

    # rerank(可选)
    if rerank is None:
        print("  - 未配置 rerank,将跳过 rerank 对比列")
        return None
    try:
        await rerank.rerank("测试查询", ["相关的文档内容", "完全无关的内容"], top_n=2)
        print(f"  ✓ rerank 可用({rerank.model_name})")
        return rerank
    except Exception as e:
        print(f"  ⚠ rerank 不可用({rerank.model_name}),跳过 rerank 对比:{e}")
        return None


async def _run_fixtures(args, embed, chat, rerank) -> None:
    """① 自制集评测流程(原 L1)。"""
    only = args.only
    setup_stats = None

    # 0.5 可选:先清空评测命名空间旧数据
    if args.reset and not args.skip_setup:
        print("[reset] 清空旧评测数据(ES + Neo4j)…")
        await teardown()
    # 1. 写入(除非 --skip-setup)
    if not args.skip_setup:
        print("[setup] 写入评测语料与记忆…")
        setup_stats = await setup_all(chat, embed)
        print(f"[setup] 完成:{setup_stats}")

    # 2. 各评测
    results: dict = {}
    details: dict = {}

    if only in (None, "retrieval"):
        print("[eval] RAG 检索…")
        results["RAG 检索"], details["RAG 检索"] = await t_retrieval.eval_rag(embed, rerank)
    if only in (None, "memory"):
        print("[eval] 记忆检索…")
        results["记忆检索"], details["记忆检索"] = await t_retrieval.eval_memory(embed)
    if only in (None, "extraction"):
        print("[eval] 三元组抽取…")
        results["三元组抽取"], details["三元组抽取"] = await t_extraction.eval_extraction(chat)
    if only in (None, "dedup"):
        print("[eval] 实体去重…")
        results["实体去重"], details["实体去重"] = await t_dedup.eval_dedup(chat, embed)

    # 3. 输出
    reporters.print_summary(results)
    rpt = reporters.write_report(results, setup_stats)
    det = reporters.write_details(details)
    print(f"\n报告:{rpt}\n明细:{det}")

    # 4. 可选清理
    if args.teardown:
        print("[teardown] 清理评测数据…")
        await teardown()


async def _run_benchmark(args, embed, chat, rerank) -> None:
    """①.5 公共评测基准入口。"""
    name = args.benchmark
    targets = ["cmteb-t2", "hotpotqa"] if name == "all" else [name]
    for bm in targets:
        print(f"\n========== ①.5 benchmark: {bm} ==========")
        if bm == "cmteb-t2":
            from eval.benchmarks.cmteb_t2 import run_benchmark
            await run_benchmark(
                embed, rerank,
                corpus_limit=args.corpus_limit,
                query_limit=args.query_limit,
                skip_ingest=args.skip_setup,
                keep_corpus=args.keep_corpus,
            )
        elif bm == "hotpotqa":
            from eval.benchmarks.hotpotqa import run_benchmark
            await run_benchmark(
                embed, chat, rerank,
                sample=args.sample,
                verifier=args.verifier,
                seed=args.seed,
                verifier_client_factory=eval_config.verifier_client,
            )
        else:
            print(f"  未知 benchmark: {bm}")


async def _run(args) -> None:
    embed = eval_config.embed_client()
    chat = eval_config.chat_client()
    rerank = eval_config.rerank_client()

    # 0. 模型可用性自检(除非 --skip-check)
    if not args.skip_check:
        # cmteb-t2 不强需 chat;其他都要
        need_chat = not (args.benchmark == "cmteb-t2")
        rerank = await _check_models(embed, chat, rerank, need_chat=need_chat)

    try:
        if args.benchmark:
            await _run_benchmark(args, embed, chat, rerank)
        else:
            await _run_fixtures(args, embed, chat, rerank)
    finally:
        await clients.close_clients()


def main() -> None:
    p = argparse.ArgumentParser(description="k-agent 离线评测(RAG + 记忆,L1 自制集 + L2/L3 公共基准)")
    # 通用
    p.add_argument("--skip-check", action="store_true", help="跳过模型可用性自检")

    # L1 自制集开关
    p.add_argument("--skip-setup", action="store_true", help="跳过写入,直接评测")
    p.add_argument("--reset", action="store_true", help="setup 前先清空旧评测数据(推荐重跑时用)")
    p.add_argument("--teardown", action="store_true", help="跑完清理评测数据")
    p.add_argument("--only", choices=["retrieval", "memory", "extraction", "dedup"],
                   help="只跑某一项(L1)")

    # ①.5 公共基准开关
    p.add_argument(
        "--benchmark",
        choices=["cmteb-t2", "hotpotqa", "all"],
        help="跑 ①.5 公共评测基准(指定后忽略 --only 等 L1 选项)",
    )
    # cmteb-t2 控制
    p.add_argument("--corpus-limit", type=int, default=1000,
                   help="[cmteb-t2] corpus 数量上限（默认 1000，全量约 100w 篇极重）")
    p.add_argument("--query-limit", type=int, default=100,
                   help="[cmteb-t2] query 数量上限（默认 100，全量约 2k 条）")
    p.add_argument("--keep-corpus", action="store_true",
                   help="[cmteb-t2] 跑完保留 corpus（默认会清理）")
    # hotpotqa 控制
    p.add_argument("--sample", type=int, default=100,
                   help="[hotpotqa] 采样题数（默认 100，分层 bridge/comparison；全量 dev 约 7400 题极重）")
    p.add_argument("--verifier", choices=["none", "same", "cross"], default="none",
                   help="[hotpotqa] Verifier 配置（等 ② Verifier Loop 完成后启用）")
    p.add_argument("--seed", type=int, default=42, help="[hotpotqa] 采样种子")

    asyncio.run(_run(p.parse_args()))


if __name__ == "__main__":
    main()
