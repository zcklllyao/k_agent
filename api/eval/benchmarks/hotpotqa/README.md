# L3 · HotpotQA distractor

多跳问答的业界标杆基准。每题给 10 段文字(2 段含答案 + 8 段干扰),系统先「检索 top-k 段落」再「多跳推理答」。

## 数据来源

- **HuggingFace 数据集**:`hotpot_qa`, 配置 `distractor`,切分 `validation`
- **License**:CC BY-SA 4.0(见数据集 README)
- 首次下载会缓存到 `api/eval/cache/hf_datasets/`

## 评测协议

- **指标**:
  - 答案 EM(Exact Match)/ F1(token 级 P/R/F1)—— 走 HotpotQA 官方 evaluator 口径
  - 检索 Recall@k(top-k 段落对 gold_titles 的覆盖)
- **采样**:默认 500 条,分层采样(`bridge` / `comparison` 按原比例),seed 固定可复现
- **检索 top-k**:默认 4(distractor 共 10 段,2 段是 gold)

## 命名空间隔离

- 每题独立 `user_id = uuid5(NS_HOTPOT, qid)`,灌入 → 查 → 立刻清理
- 单题独立,题间互不干扰;跑完整 500 题不会留任何残留

## 跑法

```bash
# 默认 500 题
uv run python -m eval.run_eval --benchmark hotpotqa

# 小规模快速验证
uv run python -m eval.run_eval --benchmark hotpotqa --sample 50

# Verifier 对照(等 ② Verifier Loop 完成后启用)
uv run python -m eval.run_eval --benchmark hotpotqa --verifier same   # 同模型 self-critique
uv run python -m eval.run_eval --benchmark hotpotqa --verifier cross  # 跨 family Verifier
```

## 输出

- `report-hotpotqa-{ts}.md`:指标表(EM / F1 / Retrieval Recall@k / 样本数)
- `details-hotpotqa-{ts}.json`:逐题明细(检索 top-k titles / pred / EM / F1)

## 污染声明(诚实)

HotpotQA dev 集发布于 2018 年,主流 LLM 训练集大概率已覆盖。本评测**仅用于系统设计对比**(不同检索配置、不同 Verifier 配置间的相对差异),**不作系统的绝对水平断言**。

## 简历话术(待填真实数字)

> 在 HotpotQA distractor 500 题(分层采样,bridge/comparison 按原比例)上:
> baseline F1 = X / EM = Y / 检索 Recall@4 = Z;
> 加 ② Verifier Loop 后 F1 +N,跨 family Verifier 较同模型 self-critique 漏检率低 M 个百分点。

## 引用

```bibtex
@inproceedings{yang2018hotpotqa,
  title={HotpotQA: A Dataset for Diverse, Explainable Multi-hop Question Answering},
  author={Yang, Zhilin and Qi, Peng and Zhang, Saizheng and Bengio, Yoshua and Cohen, William and Salakhutdinov, Ruslan and Manning, Christopher D},
  booktitle={Proceedings of the 2018 Conference on Empirical Methods in Natural Language Processing},
  pages={2369--2380},
  year={2018}
}
```
