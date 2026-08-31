"""文本分块：父子分块策略。

父块（~1024 token）提供上下文，子块（~256 token，10% 重叠）用于向量召回。
按中英文句子边界切分后合并到目标 token 数。
"""
import re

import tiktoken

# 子块/父块目标 token 数
CHILD_CHUNK_TOKENS = 256
PARENT_CHUNK_TOKENS = 1024
CHILD_OVERLAP_RATIO = 0.1

# 句子分隔符（中英文）
_SENT_SEP = re.compile(r"(?<=[。！？\.\!\?\n])")

_encoder = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder.encode(text))


def _split_sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENT_SEP.split(text) if s and s.strip()]
    return parts


def _merge_to_chunks(
    sentences: list[str], target_tokens: int, overlap_ratio: float = 0.0
) -> list[str]:
    """把句子合并成不超过 target_tokens 的块，可带重叠。"""
    chunks: list[str] = []
    cur: list[str] = []
    cur_tokens = 0
    for sent in sentences:
        st = count_tokens(sent)
        # 单句超长：直接成块
        if st >= target_tokens:
            if cur:
                chunks.append("".join(cur))
                cur, cur_tokens = [], 0
            chunks.append(sent)
            continue
        if cur_tokens + st > target_tokens and cur:
            chunks.append("".join(cur))
            # 重叠：保留尾部一部分句子
            if overlap_ratio > 0:
                keep = max(1, int(len(cur) * overlap_ratio))
                cur = cur[-keep:]
                cur_tokens = sum(count_tokens(s) for s in cur)
            else:
                cur, cur_tokens = [], 0
        cur.append(sent)
        cur_tokens += st
    if cur:
        chunks.append("".join(cur))
    return chunks


class ParentChunk:
    """一个父块及其下的子块。"""

    def __init__(self, content: str):
        self.content = content
        self.children: list[str] = []


def chunk_parent_child(text: str) -> list[ParentChunk]:
    """父子分块：先切父块，再在每个父块内切子块。"""
    text = text.strip()
    if not text:
        return []
    sentences = _split_sentences(text)
    parent_contents = _merge_to_chunks(sentences, PARENT_CHUNK_TOKENS)
    result: list[ParentChunk] = []
    for pc in parent_contents:
        parent = ParentChunk(pc)
        child_sents = _split_sentences(pc)
        parent.children = _merge_to_chunks(
            child_sents, CHILD_CHUNK_TOKENS, CHILD_OVERLAP_RATIO
        )
        result.append(parent)
    return result
