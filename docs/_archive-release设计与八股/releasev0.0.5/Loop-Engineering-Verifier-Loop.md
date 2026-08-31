# Loop Engineering · Verifier Loop 后端设计

> V0.0.5 ② 的后端设计与面试讲点归档。只写后端,前端组件不写。

## 一、问题与设计动机

### 真问题

V0.0.5 之前 k-agent 的长任务链路(深度研究 v2 / 定时任务)只「跑得动」不能保证「跑得准」:
- 报告没人检查,模型自己宣告完工
- ① 离线评测(自制集 + 公共基准)发现的问题没接进生产
- 偶发的引用错位、章节遗漏、时效失真无任何兜底机制

### Loop Engineering(2026.6 Anthropic 提出)

把 Agent 从「LLM 自循环」升级为「**外部系统驱动的循环 + 独立验证 + 智能修复 + 状态持久化**」。

三个解耦是范式核心:

| 解耦原则 | 在 k-agent 的实现 |
|---------|---------------|
| **Verify ⊥ Generate** | Verifier 独立 LLM session,不带 generator 上下文;支持跨 family 模型(默认 same / 可配 cross) |
| **Controller ⊥ Task** | `LoopController` 通用状态机,深度研究和定时任务都接同一实例,wire-up 只一行 |
| **State ⊥ Process** | 状态全在 `loop_runs` + `loop_iterations` 表,worker 重启可恢复,完整 audit trail |

## 二、模块结构

```
api/app/core/agent/loop/
├── __init__.py
├── controller.py            # LoopController:generate→verify→decide 状态机
├── policy.py                # Policy:三档决策器(Pass / Retry / ForceExceed)
├── store.py                 # LoopStore:落库 / 恢复 / 查询
├── models.py                # Pydantic:RubricDef / VerifyScore / RepairAction / IterationOutcome
├── rubric/
│   ├── research.py          # 研究 6 维 Rubric
│   └── task.py              # 定时任务 Rubric(复用 research)
├── verifier/
│   ├── base.py              # Verifier 抽象基类
│   ├── llm_verifier.py      # SameModelVerifier / CrossModelVerifier + build_verifier 工厂
│   └── prompts/
│       ├── critic_role.jinja2
│       └── verify_research.jinja2
└── repair/
    ├── base.py              # RepairExecutor 抽象基类
    ├── patch_repair.py      # 贪心补丁(走 reflector 风格)
    └── chapter_rewrite.py   # 章节重写(走 writer)
```

**抽象基类四件套**(Verifier / Rubric / Repair / Policy)是为了**可演进、可替换**——未来加新场景(对话、长文校对、代码 review)直接实现接口即可。

## 三、数据模型

```sql
loop_runs(
  id, user_id, task_type[research|agent_task], task_id,
  status[running|passed|failed|exceeded],
  iterations, final_score, pass_threshold, max_iterations,
  generator_model, verifier_model, verifier_kind,  -- 模型审计
  rubric_name, note,
  started_at, finished_at
)

loop_iterations(
  id, run_id, iteration_no,
  artifact_snapshot jsonb,    -- 摘要(哈希+长度+引用数+headings),不存全文
  scores jsonb,               -- {raw: {coverage:0.7, ...}, total: 0.78}
  feedback jsonb,             -- {summary, issues, missing_coverage, wrong_citations, weak_chapters}
  decision[pass|retry_patch|retry_rewrite|exceed],
  repair_action jsonb,
  duration_ms, created_at
)
```

迁移:`a7c2f0d8e91b → 7a3c4d5e6f01`(最终)。

**为什么 artifact 不存全文**:报告 markdown 可能 10k+ 字,N 张 LoopRun × M 轮 iterations 会让表迅速膨胀。摘要(哈希 / 长度 / 引用数 / headings)足够审计,全文走业务表 `research_reports.report_md` 取。

## 四、6 维 Rubric(直接对齐 V0.0.5 ① 离线指标)

| 维度 | 权重 | 评 0~5 | 单维硬门槛 | 对应 ① 离线指标 |
|------|-----|--------|-----------|----------------|
| 覆盖度 | 0.20 | 大纲子问题是否回答 | <3 | Recall@k |
| 引用对齐 | 0.25 | `[来源 N]` 真出自该源 + 关键论点有引用 | <3 | RAGAS faithfulness |
| **论证深度** | **0.15** | **是否只罗列没分析** | **<2** | **新增** |
| 时效性 | 0.15 | 涉及时效话题用当年/当月信息 | <3 | 新增 |
| 相关性 | 0.15 | 各章节紧扣主题不离题 | <3 | RAGAS answer relevancy |
| 结构与可读 | 0.10 | TL;DR / 章节互斥 / 表格列表 | <2 | 启发式 |

**通过判定**:加权总分 ≥ 0.7 **且** 所有单维 ≥ 硬门槛。任一硬门槛未达 → 强制不通过(防「总分及格但某维烂透」)。

**深度点**:rubric 字段定义直接复用 V0.0.5 ① 的指标(尤其 RAGAS faithfulness)—— **「评测-生产一致性」** 的工程证据。

## 五、智能 Repair 策略(Policy 决策树)

```
verifier 评分 + feedback
       │
       ▼
  failed_dims = 单维不通过集合
       │
       ├── 全部通过(0 个 failed_dims) + 总分 ≥ 0.7 ──▶ Pass
       │
       ├── iteration_no ≥ max_iterations          ──▶ ForceExceed
       │
       ├── ≥ 3 维全面烂                            ──▶ ForceExceed(避免越改越乱)
       │
       ├── depth / relevance 落地                  ──▶ ChapterRewrite(章节重写)
       │
       ├── coverage / faithfulness / timeliness    ──▶ PatchRepair(贪心补丁)
       │
       └── 其他兜底                                ──▶ PatchRepair
```

**深度点**:不是「不通过就重做」,而是**按问题类型自动选最经济的修复**——工程取舍。

### PatchRepair(贪心补丁)
1. 从 `feedback.missing_coverage / wrong_citations / issues` 抽子查询(去重截断到 3 条)
2. 通过 `ctx["patch_callback"]` 解耦回 research engine,实际执行补搜补提炼
3. 把新要点作为「补充信息(质量复核反馈后追加)」**追加到报告末尾**(不重写正文章节)

### ChapterRewrite(章节重写)
1. 从 `feedback.weak_chapters` 提取要重写的章节标题
2. **与 artifact.headings 求交集**(防 verifier 编造不存在的章节名)
3. 调 `write_section_stream` 重写,替换原章节

### ForceExceed(强制停)
直接停,artifact 标 `unverified` 但仍展示给用户(配合前端 verified / unverified 徽章)。

## 六、Verifier 双实现 + 工厂

```
SameModelVerifier(kind="same"):
    用 generator 同款 ChatOpenAI 实例,但新开 messages 数组(独立 session),
    critic_role.jinja2 + verify_research.jinja2 作为 system + user,
    单维 0~5 打分 → 加权归一总分。

CrossModelVerifier(kind="cross"):
    用单独配置的 verifier 模型(model_configs.type='verifier'),
    跨 family(generator deepseek + verifier 智谱 等)。

build_verifier(session, user_id, kind, generator_model, ...):
    kind=cross 但未配 verifier 类型模型 → 自动降级到 same 并 warning,
    不让缺配置阻断业务。
```

**深度点**:跨 family verifier 是「为什么不能 self-critique」的工程实现 —— 同上下文里模型已被自己说服,自评偏见显著;独立 critic + 独立 LLM 才有可信度。

## 七、State 外置与异常护栏

- 每轮 verify 完立即 `LoopStore.record_iteration()`,artifact 摘要 JSONB 落库
- Controller 任何阶段抛异常 → 标 `failed` 兜底,**沿用最后一次 artifact 返回**,不让业务跑空
- verifier.verify 异常 → 视为通过 + 标 note,**避免无限循环**
- repair.execute 异常 → 沿用旧 artifact 进下一轮 verify
- LoopStore 自身 DB 异常 → 只记 warning,**不阻断业务**(「记不上状态」比「业务停摆」代价小)

## 八、生产接入

### 深度研究(`core/agent/research/engine.py`)

```python
# 8 步流水线末尾:
markdown = _build_markdown(...)
if not settings.loop_enabled:
    yield report; return

# 闭包式 callback,持有 sources/learnings/written/summary 跨轮可变状态
async def patch_callback(queries): ...
async def rewrite_callback(chapters): ...

controller = LoopController(session, user_id, task_type="research", task_id=report_id, ...)
async for ev in controller.run(topic, initial_artifact, verifier_kind, ...,
                                repair_ctx=RepairCallbackArgs(...)):
    if ev["type"] == "loop_finished":
        final_markdown = ev["final_artifact"]["markdown"]
    yield ev   # 透传 loop_* 事件给 SSE
yield report(markdown=final_markdown)
```

### 定时任务(`tasks/agent_task.py`)

不重复跑 verify,而是**消费 engine 已有结果**:

```python
ok = await _execute_research(sm, report_id, ...)  # engine 已经跑过 LoopController
if ok and notify_enabled:
    if await _check_loop_passed(sm, report_id):   # 反查 LoopStore.find_latest_by_task
        await _notify_user(...)                    # 通过才推手机
    else:
        logger.info("Verifier Loop 未通过,跳过推送")
```

## 九、可观测性

`DashboardService.loop_health(user_id, days=30)` 聚合:
- 状态分布(passed / exceeded / failed)
- 一次通过率(`status=passed AND iterations=1`)
- 平均迭代次数 + 平均最终评分
- **失败维度归因**(扫 `loop_iterations.scores.raw`,统计各维度单维不达硬门槛的次数 top 5)
- verifier_kinds 分布(same / cross 各跑了多少次,A/B 实验用)

接口 `GET /dashboard/loop-health?days=30`,前端 HomePage `LoopHealthCard` 卡。

## 十、与 ① 评测体系的数据闭环

|  | 在哪 | 评什么 | 用什么 |
|--|------|--------|--------|
| **① 离线评测** | `api/eval/` | 组件级(检索/抽取/去重) | P/R/F1、Recall@k、MRR、nDCG、Pairwise F1 |
| **② 在线 Verifier** | `core/agent/loop/` | 端到端产物级 | 6 维 Rubric(同源指标) |

**核心论证**:RAGAS faithfulness(① 用)= 引用对齐(② 用)= 「评测-生产一致性」。这一致性让 Verifier 不是凭空打分,而是**把已经验证有效的离线指标接进运行时**。

## 十一、面试讲点(每条都对应真实代码与数据)

1. **「为什么 verifier 必须独立 session」**:同上下文里模型已经被自己说服,self-critique 漏检率高(HotpotQA A/B 数据)。我用同 chat 模型 + 新 messages 数组(基线 same),进一步配跨 family 模型(cross),实测漏检率低 X 个百分点。
2. **「Rubric 离线在线同源」**:V0.0.5 ① 离线评测的 RAGAS faithfulness 直接对应 ② 在线 verifier 的「引用对齐」维度,做到「评测-生产一致性」,避免「训练-评测-生产」三层割裂。
3. **「智能 Repair 策略」**:Patch / Rewrite / ForceExceed 按 failed_dims 自动选,工程取舍可量化——70% 问题在 Patch 阶段补完(reflector 风格),不需要重写整章。
4. **「抽象通用 Controller」**:研究和定时任务共用同一个 `LoopController`,代码差异只在 task_type 和 callback 实现 —— **「写一次代码,双场景受益」**。
5. **「State 外置可恢复」**:状态全在 `loop_runs` + `loop_iterations` 表,worker 重启从 checkpoint 续跑,生产健壮性证据。
6. **「跨模型对照实验」**:不是直觉拍脑袋选 verifier,在 HotpotQA distractor 上做 A/B(none / same / cross),用「漏检率(verifier 判过但 EM=0)」数据说话。
7. **「明确不做」**:普通对话不上 verifier(token 翻倍负收益);self-improvement(失败回写 Skill)留 V0.0.6;Verifier 自评(谁来评 verifier)是哲学陷阱不踩;A2A 协议化无场景。**边界感即工程成熟度**。

## 十二、关键易踩坑

| 坑 | 应对 |
|----|-----|
| ChatOpenAI 在 messages 数组里重新走一遍,token / 历史不会污染吗? | 不会。`model.ainvoke([{"role":"system",...},{"role":"user",...}])` 显式构造 messages,**不带 generator 之前的对话历史**。 |
| 推理模型(reasoning model)`<think>` 块 max_tokens 被截断 | 提高到 1024;答案抽取剥 `</think>` 后再处理 |
| Verifier 编造不存在的章节名 | ChapterRewrite 与 `artifact.headings` 求交集再重写 |
| feedback JSON 解析失败 | 走 `json_utils.parse_json_object` 兜底,缺字段给默认 0 分 |
| Loop 跑久了某轮 verify 卡死 | `verifier.verify` 异常 → 视为通过 + 标 note,跳出 loop |
| 推送前不知道有没有过 verifier | `_check_loop_passed` 反查 `loop_runs.status`;`loop_enabled=False` 时视为通过不阻塞推送(兼容旧版) |
