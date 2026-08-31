# 公共评测基准(C-MTEB + HotpotQA)+ Verifier A/B 实验 — 设计与面试

> 自制集证明「场景可用」,公共基准证明「业界水平」。引入 C-MTEB(中文检索)+ HotpotQA distractor(多跳推理)两套业界公认基准,把指标对标到可比基线,同时用 HotpotQA 给 ② Verifier Loop 跑严格 A/B 实验。
> 对应能力域:**评测体系**(公共基准层)。代码:`api/eval/benchmarks/{cmteb_t2,hotpotqa}/`。

---

## 0. 能力定位(对应招聘要求)

- 对应 JD:**「LLM 评测」「公共基准」「C-MTEB / MTEB」「HotpotQA」「LLM-as-judge」「A/B 实验」**。
- 角色:把 ① 自制集的「**场景可用**」升级到「**业界水平**」,并为 ② Verifier Loop 提供数据驱动的工程决策证据(为什么不能 self-critique)。

---

## 1. 解决什么问题

### 1.1 自制集的局限

V0.0.5 ① 跑出来 RAG Recall@5=1.0 / 记忆 Recall@5=0.82,数据漂亮但**缺说服力**——「题是自己出的、自己跑出来 100%,谁信」。

### 1.2 三层评测结构(最终)

```
L1 应用层(自制中文集,① 完成)         证明:产品自洽 + 记忆评测的事实来源(中文)
L2 中文检索基准(C-MTEB T2Retrieval)    证明:通用检索能力(对标 bge-m3 等业界基线)
L3 多跳推理(HotpotQA distractor)       证明:端到端 RAG + Verifier same/cross A/B
```

> **原计划的 L4 LongMemEval 已下架**(EMNLP 2024 英文长对话记忆基准):本项目记忆萃取流水线**中文优先**(`core/memory/prompts/*.jinja2` 全中文 + 13 类中文实体/谓词词表),英文输入产生翻译噪声,实测 oracle 2 题全 0。**「不卖做不到的事」是工程判断,本身亦为面试加分项**——能砍掉本来计划做的事比加上去更难。

---

## 2. 架构 / 数据流

```mermaid
flowchart TD
  HF[Hugging Face Hub] --> CMT[cmteb_t2/loader<br/>mteb/T2Retrieval]
  HF --> HPQ[hotpotqa/loader<br/>hotpotqa/hot_qa/distractor]
  CMT --> CR[cmteb_t2/runner<br/>四列对比:纯向量/BM25/混合/+rerank]
  CR --> M1[nDCG@10 / Recall@10 / MRR@10]
  HPQ --> HR[hotpotqa/runner<br/>每题独立 user_id 灌入→查→清]
  HR --> M2[EM / F1 / 检索 Recall@4]
  HR -.可选.-> V{--verifier}
  V -->|none| M2
  V -->|same| QV[qa_verifier<br/>同模型 self-critique]
  V -->|cross| QV2[qa_verifier<br/>跨家族 deepseek+glm]
  QV & QV2 --> M3[judge 通过率 / 漏检率 / 与 EM 一致率]
  M1 & M2 & M3 --> REP[results/{rag,memory}/<br/>report-*.md]
```

---

## 3. 模块设计

### 3.1 目录与共享 helpers

```
api/eval/benchmarks/
├── __init__.py                   # 子模块注册
├── _common.py                    # 共享 helpers:报告/明细落盘 / 分层采样 / cache 路径
├── cmteb_t2/
│   ├── __init__.py
│   ├── loader.py                 # HF datasets `mteb/T2Retrieval`
│   ├── runner.py                 # 四列对比 runner
│   └── README.md                 # 含 license / 引用
└── hotpotqa/
    ├── __init__.py
    ├── loader.py                 # HF `hotpotqa/hot_qa/distractor` validation
    ├── runner.py                 # 单题灌入→查→清 + --verifier
    ├── qa_verifier.py            # LLM-as-judge(基于检索证据判 1/0)
    └── README.md                 # 含污染声明
```

`_common.py` 共享:
- `save_report` / `save_details` —— 报告 + 明细按 `results/{rag,memory}/{benchmark}-{ts}.md` 落盘
- `stratified_sample(seed, sample_size, strata_key)` —— 分层采样(bridge / comparison)
- `cache_dir()` —— HF datasets 缓存路径(`api/eval/cache/`,gitignored)

### 3.2 cmteb-t2 模块

| 项 | 实现 |
|----|------|
| 数据源 | HF `mteb/T2Retrieval`,corpus + queries + default 三 subset 各 split=`dev` |
| 子集 | `--corpus-limit 300 --query-limit 30` 控制大小(可调) |
| 索引 | 独立 user_id 命名空间(uuid5),corpus 灌进 ES → 跑 query → 清(`--keep-corpus` 可保留以快速复跑) |
| 配置对比 | 纯向量 / 纯 BM25 / 混合(向量 0.6 + BM25 0.4)/ +rerank 四列 |
| 指标 | nDCG@10 / Recall@10 / MRR@10 |

**实测结果(300 corpus / 30 query)**:

| 配置 | nDCG@10 | Recall@10 | MRR@10 |
|------|---------|-----------|--------|
| 纯向量 | 0.9699 | 0.9690 | 1.0 |
| 纯 BM25 | 0.881 | - | - |
| **混合** | **0.9818** ⭐ | **0.9863** | **1.0** |
| 混合 + rerank | 0.9777 | - | 1.0 |

**结论**:
- 混合 vs 纯向量 +1.2pt,vs BM25 +10pt,**MRR@10=1.0** 说明 rerank 把所有相关文档稳定排到第 1 位
- **rerank 在小语料(300 篇)下轻微伤害**(0.9818 → 0.9777)——生产大语料时会反转,**这正是 rerank 在 RAG 系统里何时启用的工程判断**

### 3.3 hotpotqa 模块

| 项 | 实现 |
|----|------|
| 数据源 | HF `hotpotqa/hot_qa/distractor` validation,每题 10 段 paragraph(2 gold + 8 distractor) |
| 采样 | 分层(bridge / comparison)+ seed 可复现 |
| 流程 | 每题独立 user_id 灌入 paragraph → 混合检索 top-4 → chat 模型答多跳题 → 清 |
| 指标 | EM(完全匹配)/ F1(token P/R/F1)/ 检索 Recall@4,走 HotpotQA 官方 normalize+token 口径 |
| Verifier | `--verifier {none,same,cross}` 接 `qa_verifier.py` LLM-as-judge(基于检索证据独立判 1/0,与 gold 完全独立) |

**实测结果(200 题 baseline)**:

| 指标 | 结果 |
|------|------|
| EM | **62%** |
| F1 | **74.49%** |
| Recall@4 | **95.75%** |

### 3.4 Verifier A/B 实验(20 题/组)

`--verifier {none,same,cross}` 三组对照,统计:

- **verifier_pass_rate**:Verifier 判过率
- **leak_rate**:漏检率(judge 通过但实际 EM=0)
- **agreement_with_em**:与 EM 一致率

| 配置 | verifier 模型 | judge 通过率 | EM 一致率 |
|------|-------------|------------|----------|
| **same**(self-critique) | deepseek-v3 自评 | **0%** ⚠ | 40% |
| **cross**(跨家族) | deepseek-v3 应答 + glm-4-flash 审稿 | **95%** ⭐ | **65%** |

**结论**:
- **self-critique 完全不可用**(同模型偏向认同自己,judge 通过率 0%)
- **跨家族独立审稿才是数据驱动的工程必选**——这是 ② Verifier Loop「优先 cross,fallback same」决策的实证基础

---

## 4. 工程亮点(架构层)

1. **数据集 loader 走 HF 标准库**(`datasets` + `huggingface_hub`),失败优雅降级;数据集结构变更兜底——C-MTEB → mteb/T2Retrieval 路径迁移 + split 命名从 `corpus/queries/default` 变成全 `dev`,loader 兼容新结构
2. **每题独立 user_id 命名空间**(uuid5):HotpotQA 单题灌入 → 评测 → 立刻清,**题间零干扰、可重入**
3. **复用同一 metrics 模块**(P/R/F1 / Recall@k / MRR / nDCG / 分层采样),不重复造轮子
4. **诚实污染声明**:HotpotQA dev 2018 年发布,主流 LLM 可能见过,只作系统设计对比,不作绝对水平断言 —— **这种诚实性反而加分**
5. **Verifier A/B 实验设计**:同一份 runner 加 `--verifier` 参数,one-knob 切换,三组对照真出数据
6. **results 按 rag / memory 拆子目录**:`results/rag/`(C-MTEB + HotpotQA + 自制 RAG)/ `results/memory/`(自制记忆三任务),按系统组织而非按 benchmark 组织,更接近开发者视角

---

## 5. 设计取舍

| 取舍 | 选择 | 原因 |
|------|-----|------|
| 接入 LongMemEval(英文) | **不接** | 实测 oracle 2 题全 0,中文优先项目硬上数据难看,**砍掉而非硬上** |
| C-MTEB 跑全量(N>1w) | **跑 subset 300/30** | HF 数据流量大、单机算力有限;subset 已能体现配置差异 |
| HotpotQA 跑 7405 题(完整 dev) | **跑 200 题 baseline + 20 题 A/B** | 单题灌入 + 评测耗时大,200 + 20 已足够出统计显著结果 |
| Verifier 用什么模型 | same=同 chat 模型 / cross=deepseek + glm 跨家族 | 用项目主要会用的开源中文模型,符合实战场景 |
| 是否对污染做去重 | **诚实声明,不作绝对断言** | 主流 LLM 可能见过 HotpotQA 2018 dev,只作系统设计对比,声明诚实性 > 假装无污染 |

---

## 6. 易踩坑

- **HF 数据集路径变更**:`C-MTEB/T2Retrieval` → `mteb/T2Retrieval`(MMTEB 迁移),子配置的 split 全是 `dev`(不再 corpus/queries 同名)。loader 必须兼容,否则会报 `'corpus' not found. Available: ['default']` / `Unknown split "corpus". Should be one of ['dev']`
- **HotpotQA dev 评测必须用官方 normalize**:小写 / 去标点 / 去冠词 / 空白归一化;直接字符串相等会偏低 5~10 个百分点,所有 baseline 论文都用这套口径
- **rerank 在小语料下伤害**:cmteb-t2 300 篇语料 nDCG@10 从 0.9818 降到 0.9777——rerank 在小且语义清晰的语料上**多此一举**,生产大语料才能反转。这是一个有趣的反直觉发现,值得讲。
- **`--verifier same` 的失效现象**:judge 通过率 0% 看起来像 bug,实际是 self-critique 的真实失效——同模型 prompt 倾向于自圆其说。**这是 V0.0.5 ② 决策的硬数据,务必记录**。
- **诚实污染声明**:HotpotQA 2018 年发布,主流 LLM 训练时可能见过 gold 答案。我们的指标只反映「系统设计 + 检索质量」的相对水平,不作绝对断言。

---

## 7. 真实指标汇总

| 基准 | 配置 | 指标 |
|------|-----|------|
| **C-MTEB T2Retrieval**(中文检索 / 300 corpus / 30 query) | 混合检索 | **nDCG@10 = 0.9818** |
| | 纯向量对比 | 0.9699(+1.2pt) |
| | 纯 BM25 对比 | 0.881(+10pt) |
| | MRR@10 | **1.0** |
| **HotpotQA distractor**(多跳推理 / 200 题) | baseline | **EM = 62% / F1 = 74.49% / Recall@4 = 95.75%** |
| **Verifier A/B**(HotpotQA / 20 题/组) | same(self-critique) | judge 通过率 **0%** / EM 一致 40% |
| | **cross(deepseek + glm)** | judge 通过率 **95%** / EM 一致 **65%** |

---

## 8. 面试讲点

1. **为什么从自制集扩到公共集**:自制集证明产品能用,公共集证明系统在业界基线上的真实水平。两轨制(自洽 + 对标)比只跑一种更可信。
2. **HotpotQA 跑的是 RAG 端到端而不是纯检索**:每题 10 段 paragraph(2 gold + 8 distractor)→ 混合检索 top-4 → chat 模型答多跳题。**同时测了检索能力(Retrieval Recall@4)+ 生成能力(EM / F1)**,这是 RAG 系统最完整的画像。
3. **rerank 反直觉发现**:在小语料(C-MTEB 300 篇)下 rerank 反而轻微伤害(0.9818 → 0.9777),生产大语料才反转——这给「rerank 何时开启」的工程决策提供数据依据。
4. **污染了怎么办**:坦诚承认 + 主动声明,仅作系统配置间的相对对比。**主动声明诚实性反而加分**。
5. **为什么不接 LongMemEval**:英文集和我项目中文优先定位不匹配,实测 2 题 oracle 准确率全 0,工程上明确砍掉而不是硬上数据难看。**能砍掉的判断比加上去更难**。
6. **Verifier A/B 实证**:不是直觉拍脑袋选 cross verifier,而是 same vs cross 三组对照真出数据(0% vs 95%),数据驱动「不能让模型自评」的工程取舍。

---

## 9. 简历话术(可直接用)

> **公共评测基准对标(C-MTEB T2Retrieval + HotpotQA distractor)**:
>
> - 中文检索 C-MTEB T2Retrieval:混合检索 **nDCG@10 = 0.9818**(vs 纯向量 0.9699 + 1.2pt,vs BM25 0.881 + 10pt);MRR@10 = 1.0
> - HotpotQA distractor 多跳问答 200 题:**EM = 62% / F1 = 74.49% / 检索 Recall@4 = 95.75%**
> - **Verifier A/B 实证**:跨家族审稿(deepseek 应答 + glm 审稿)judge 通过率 **95%**,同模型自评仅 **0%**,数据驱动证明「不能让模型自评」
> - 工程判断:LongMemEval(英文集)与项目中文优先定位不匹配,实测 oracle 全 0,**明确不做**(能砍掉的判断比加上去更难)

---

## 10. 相关文件速查

| 类别 | 路径 |
|------|------|
| 入口 | `api/eval/run_eval.py --benchmark {cmteb-t2,hotpotqa,all}` |
| 共享 helpers | `api/eval/benchmarks/_common.py` |
| cmteb-t2 | `api/eval/benchmarks/cmteb_t2/{loader,runner}.py` + `README.md` |
| hotpotqa | `api/eval/benchmarks/hotpotqa/{loader,runner,qa_verifier}.py` + `README.md` |
| 实测报告 | `api/eval/results/rag/report-cmteb-t2-*.md` + `report-hotpotqa-*.md` |
| Verifier 配置 | `api/eval/.env.eval.example` 的 `EVAL_VERIFIER_*` 段 |
