"""QA 答案 Verifier:HotpotQA A/B 实验专用的轻量 LLM-as-judge。

设计:
- 与生产 LoopController 的 Verifier 独立,因为 HotpotQA 是 QA 短答而非 research 长报告,
  6 维 rubric 不适用,直接用单维「答案是否对得上检索证据」判 1/0 即可。
- 复用 V0.0.5 ② 的核心论点验证场景:相同问题 + 检索段落 + 候选答案,
  分别用 SameModel(同 chat 模型) 与 CrossModel(跨 family) 打分,
  对比两者的「verifier 判过率 vs 真实 EM」差距即漏检率,印证「为什么不能 self-critique」。
"""
from __future__ import annotations

import string

from app.core.llm.client import LLMClient
from app.core.logging import get_logger

logger = get_logger(__name__)


_QA_JUDGE_PROMPT = """You are an independent grader for a multi-hop QA system.

Question: {question}

Candidate Answer: {pred}

Retrieved Evidence Passages:
{passages}

Decide whether the candidate answer is CORRECT given ONLY the evidence passages above.
- A correct answer must be directly supported by the evidence (one or two passages).
- Hallucinated facts that look plausible but are not in the evidence are INCORRECT.
- A vague/empty/refusal answer (e.g. "I don't know", "cannot determine") is INCORRECT.

Output exactly one character: 1 if correct, 0 if incorrect. No explanation, no punctuation.
"""


async def judge_qa(
    client: LLMClient,
    *,
    question: str,
    pred: str,
    retrieved_passages: list[tuple[str, str]],
) -> int:
    """LLM-as-judge:仅基于检索证据判答案是否正确,返回 1/0。

    判断完全独立于真实 gold answer —— 模拟「生产环境无 gold 时,verifier 能否准确识别正确/错误答案」。
    A/B 实验把 same vs cross verifier 的判断与真实 gold 对比,差距 = 漏检率。
    """
    if not pred or not pred.strip():
        return 0
    passages_text = "\n\n".join(
        f"[{title}]\n{content[:500]}" for title, content in retrieved_passages[:4]
    ) or "(no passages)"
    prompt = _QA_JUDGE_PROMPT.format(
        question=question, pred=pred, passages=passages_text
    )
    try:
        text = await client.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=4, temperature=0.0,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("QA verifier 调用失败,降级 0(不通过): %s", e)
        return 0
    text = (text or "").strip().strip(string.punctuation + " \"'")
    if text.startswith("1"):
        return 1
    return 0
