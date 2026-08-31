# Agent 全链路可观测(Tracing + 成本核算)后端设计

> V0.0.5 ③ 的后端设计与面试讲点归档。只写后端,前端组件不写。

## 一、问题与设计动机

### 真问题

V0.0.5 的 ② Verifier Loop 把「自我审视」做到了**产物层**(评分合格/不合格 → 回炉),但回答不了:

- 第 1 轮 Verifier 评 0.6 不通过 → PatchRepair → 第 2 轮 0.78 通过,**中间到底调了哪些工具、reflector 补搜了什么、每个 LLM 调用花了多少 token**?
- 用户报告说「报告引用错了」,具体是哪个 retriever 召回时漏了源?
- 月底账单一堆钱,**花在哪个 model、哪类任务**上 7/30 天累计多少?
- 「这次研究跑了 40 秒」中,planner 占多少 / writer 占多少 / verifier 占多少 —— **瓶颈在哪**?

只看产物答不上这些。需要把「自我审视」**下沉到执行链路层**。

### 行业范式

业界事实标准是 **LangSmith / Langfuse / Arize Phoenix / Helicone** 这套 LLM 可观测性平台,但都要么收费要么外部依赖。我们做**自有最小可行版**:

- 数据落自己的 PG(`agent_traces` + `agent_spans` 两张表)
- 字段名遵循 **OpenTelemetry GenAI semantic convention**(`gen_ai.system / gen_ai.usage.input_tokens` 等)
- 未来要导出到 OTel Collector / Jaeger / Tempo / LangSmith,改输出格式即可,无需重做数据模型

## 二、模块结构

```
api/app/core/agent/tracing/
├── __init__.py
├── tracer.py            # 全局 Tracer 单例,async with 上下文管理器埋点(span / trace / llm_span)
├── span_recorder.py     # 异步批量落库:asyncio.Queue + 后台 task + 写失败只 warning
├── pricing.py           # 内置 model 单价表 + estimate_cost_cny(单价 × tokens)
├── otel_attrs.py        # OTel GenAI 标准属性常量 + provider→system 映射
└── models.py            # Pydantic 运行时结构:SpanRecord / TraceRecord

api/app/repositories/agent_trace_repository.py
api/app/services/trace_service.py
api/app/controllers/trace_controller.py   # GET /traces 列表 + /{id} 详情 + /cost-summary 聚合
api/app/models/agent_trace_model.py        # ORM:AgentTrace / AgentSpan
```

## 三、数据模型

```sql
agent_traces(
  id, trace_id,             -- 全局 trace_id(展示用,与 id 同源 UUID)
  user_id, task_type,       -- research | chat | agent_task | verify | repair
  task_id,                  -- research_reports.id / conversations.id / agent_tasks.id(无 FK 解耦)
  task_name,                -- 人话名(供列表展示)
  root_span_id,
  status[running|ok|error],
  started_at, finished_at, duration_ms,
  total_input_tokens, total_output_tokens, total_cached_tokens, total_cost_cny,
  models_used jsonb,        -- 这次任务用到的所有模型(便于按 model 聚合)
  loop_run_id              -- 关联 ② Verifier Loop 的 loop_runs.id(打开黑盒的钩子)
)

agent_spans(
  id, span_id, parent_span_id, trace_id,
  span_type[planner|retriever|writer|tool_call|verifier|repair|mcp_call|llm_call|other],
  name,                    -- 人话名(如「写章节 1/5: 引言」/「工具:web_search」)
  payload jsonb,           -- 输入输出摘要(不存全文,存 request_summary / response_preview / output_preview 等前 600 字)
  attributes jsonb,        -- OTel GenAI 标准属性 + k-agent.* 业务扩展
  model_name, input_tokens, output_tokens, cached_tokens, cost_cny,
  status, error_message,
  started_at, finished_at, duration_ms,
  iteration_id             -- 关联 ② loop_iterations.id(verifier/repair span 时填,实现精确定位某一轮)
)
```

索引:`(user_id, started_at desc)` / `trace_id` / `(span_type, status)` / `iteration_id`(全部命中常用查询模式)。

## 四、Tracer:非侵入式埋点 API

业务侧代码:

```python
tracer = get_tracer()
async with tracer.trace(user_id, task_type="research", task_id=report_id, task_name=topic) as tctx:
    async with tracer.span("规划:多视角子问题", span_type="planner") as sp:
        plan = await make_plan(model, topic)
        sp.set_attribute("section_count", len(plan.sections))

    async with tracer.span("检索资料", span_type="retriever"):
        # 内部:每个工具自己 包 sub-span
        async with tracer.span("检索:联网", span_type="tool_call"):
            ...

    # ② Verifier Loop 内部自动包 verifier/repair sub-span,关联 iteration_id
```

关键设计:

1. **ContextVar 自动 parent 关联** —— `_current_trace` / `_current_span` 用 `contextvars.ContextVar`,asyncio 任务安全。嵌套 `async with` 自动构建 span 树,业务代码无需手动传 parent
2. **采样开关零开销** —— `settings.tracing_enabled=False` 或 `random.random() > tracing_sample_rate` 时,返回 `_NoopTraceCtx / _SpanHandle(None)`,所有方法转空操作,生产关闭无任何开销
3. **NoOp 路径不计 token / 不入队** —— 关闭时 tracer.set_tokens / set_attribute 等全部跳过,只判一次 self.\_noop bool
4. **token / cost 自动累加到 trace** —— `sp.set_tokens(...)` 在 SpanHandle 里自动找 `_current_trace.get()` 累加到 `total_*` 字段,业务无感
5. **采样按 trace 级别决定** —— 一旦 trace 决定不采,内部所有 span 也走 NoOp,保证 trace 完整性

## 五、异步批量落库

`SpanRecorder` 是模块级单例,生命周期挂 FastAPI lifespan:

```python
# main.py
await get_recorder().start()   # 应用启动:开后台 task
...
await get_recorder().stop()    # 应用关闭:排空残留再退
```

工作流:

```
业务调 tracer.span() / set_tokens() → SpanRecorder.push_span/trace
                                       ↓
                                       asyncio.Queue(maxsize=5000)
                                       ↓
                                       后台 consume_loop:
                                       - 凑够 batch_size(默认 20)→ flush
                                       - 或超 flush_interval(默认 2s)→ flush
                                       - 写库失败只 warning,业务不感知
                                       - 队列满丢最旧并 warning(内存安全 > 完整 trace)
```

四个关键决策:

| 决策 | 理由 |
|------|------|
| **不阻塞主流程** | span 数据全异步进队列,业务路径零等待。即使 PG 抖动,业务也不阻塞 |
| **批量落库** | 单次 trace 可能产 30+ span,逐条 INSERT 浪费连接 |
| **失败只 warning** | trace 数据是辅助观测,丢一些 span 无所谓,但绝不能因此影响主业务 |
| **队列上限丢最旧** | 极端高峰下保护进程内存,丢失老 trace 比 OOM 优先级低 |

## 六、Pricing:模型单价表 + 成本核算

`pricing.py` 内置 20+ 主流模型单价(2026.06 公开价 + 7 CNY 汇率),覆盖:

- OpenAI(gpt-4o / gpt-4o-mini / gpt-4-turbo / gpt-3.5-turbo)
- DeepSeek(v4-pro / v3 / chat / reasoner)
- 智谱 GLM(4.6 / 4-plus / 4-air / 4-flash / 4v)
- 通义千问(qwen-max/plus/turbo + qwen-vl-max/plus)
- 豆包 / Embedding / Rerank 系列

公式:

```python
cost_cny = (input_tokens - cached_tokens) × input单价/1000
         + output_tokens × output单价/1000
         + cached_tokens × cached单价/1000
```

特点:

- **精确匹配优先 → 前缀匹配兜底**:`deepseek-chat-v3-pro` 命中 `deepseek-chat`(取最长前缀)
- **cached_tokens 不与 input 重复计费**:`fresh_input = max(0, input - cached)`
- **未命中走默认兜底**:`(0.005, 0.015, 0.0025)` 中等档位,宁可高估不让 cost=0 误导

承认的局限(文档显式声明):

- 各家会调价、汇率会变,这是估算不是财务级精确
- 没有统一 pricing API,定时自动同步成本高、维护脆,**明确不做**
- 误差 ±5~30%,作为「相对成本对比 + token 用量真实」足够,**不作为对外财务依据**

## 七、关键埋点接入

非侵入式接入了 5 个关键位置:

### 1. `LLMClient.chat / embed / vision / rerank`(底层网络层)

每次对外 HTTP 调用自动包 `llm_call` span:

```python
async with tracer.llm_span(f"chat:{self.model_name}", model_name=...) as sp:
    sp.set_payload("request_summary", last_user[:600])   # 请求摘要
    data = await _post_with_retry(...)
    in_t, out_t, cached = _extract_usage(data)            # 抽 usage
    sp.set_tokens(input=in_t, output=out_t, cached=cached, model_name=...)
    sp.set_payload("response_preview", text[:600])        # 回复前 600 字
    return text
```

`_extract_usage` 兼容多种 provider 返回格式:`prompt_tokens / completion_tokens / input_tokens / output_tokens / prompt_tokens_details.cached_tokens` 都能识别。

### 2. `orchestrator`(对话编排器,LangChain 调用层)

**这里是大坑**:LangChain 的 `ChatOpenAI.astream()` 走 OpenAI SDK,**不经过我们的 `LLMClient`**,token 用量需要从 `gathered.usage_metadata` 抽,**且 LangChain 默认不在流式响应里带 usage**。

修复:
1. `chat_model.py` 构造 `ChatOpenAI(stream_usage=True, ...)` —— 让流尾 chunk 带 `usage_metadata`
2. orchestrator 每轮工具循环都包 `llm_span`,流完后从 `gathered.usage_metadata` 抽 input_tokens / output_tokens / cache_read
3. 每次 `tool.ainvoke(args)` 包 `tool_call` span,记 tool name / query / output_preview

```python
async with tracer.llm_span(f"chat:{model_name} (轮 {iter})", model_name=...) as lsp:
    gathered = None
    async for chunk in model_with_tools.astream(messages):
        gathered = chunk if gathered is None else gathered + chunk
    usage = getattr(gathered, "usage_metadata", None) or {}
    lsp.set_tokens(input=usage["input_tokens"], output=usage["output_tokens"], cached=cached)
```

### 3. `research engine`(深度研究流水线)

8 个阶段全埋点:

```
trace(task_type="research")
├─ span("规划:多视角子问题", planner)
├─ span("检索:N 个角度", retriever)
│  ├─ span("检索:联网", tool_call)
│  ├─ span("检索:知识库", tool_call)
│  └─ span("检索:MCP 增强", mcp_call)
├─ span("逐源提炼:N 个来源", writer)
├─ span("反思:找缺口子查询", planner)
├─ span("补提炼:M 个新来源", writer)
├─ span("大纲整理:论点+证据分配", planner)
├─ span("写章节 i/N: <heading>", writer)  × N 章
├─ span("汇总:摘要与核心要点", writer)
└─ LoopController.run() 内部:
   ├─ span("verifier 第 N 轮", verifier) + iteration_id 关联
   └─ span("repair: <kind> 第 N 轮", repair) + iteration_id 关联
```

捕获 `loop_started` 事件的 `run_id` 后:`tctx.set_loop_run_id(uuid.UUID(run_id))`,把 trace **关联到 ② LoopRun**,实现「报告页 → 评分卡 → 查看执行轨迹 → 看 verifier 每轮判分理由」全链路下钻。

### 4. `chat_service._run_chat_turn_bg`(对话主流程)

```python
async with tracer.trace(user_id, task_type="chat", task_id=conv_id, task_name=user_text[:120]) as tctx:
    await bus.publish(cid, "trace", {"trace_id": str(tctx.trace_id)})
    ...
    # 落库 assistant 消息时把 trace_id 写进 meta_data,前端历史加载能恢复「查看执行轨迹」按钮
    await svc.msg_repo.add(Message(meta_data={..., "trace_id": str(tctx.trace_id)}))
```

效果:**每条 AI 消息底部直接挂「执行轨迹」按钮**,点击跳 `/traces?trace_id=xxx`,不再让用户去全局列表里翻。

### 5. LoopController(打开 ② 黑盒的关键)

verifier / repair 各包一个 sub-span,并通过 `set_iteration_id(iter_id)` 关联到 `loop_iterations.id`:

```python
iter_id = uuid.uuid4()
async with tracer.span(f"verifier 第 {iteration_no} 轮", span_type="verifier") as vsp:
    vsp.set_iteration_id(iter_id)
    score = await verifier.verify(...)

# store 落库 LoopIteration 时用同一个 iter_id
outcome = IterationOutcome(id=iter_id, ...)
await self.store.record_iteration(run_id, outcome)
```

这样前端可以从「报告页 → 评分卡 → 第 N 轮」一键下钻到「时间线 → verifier/repair span」精确高亮该轮。

## 八、HTTP 接口

```
GET /api/traces                  列表(按时间倒序),支持 task_type / task_id / status / days 过滤
GET /api/traces/{trace_id}       详情(trace 字段 + 全部 span)
GET /api/traces/cost-summary     按 task_type / model 聚合的成本面板数据(days 参数)
```

注意路由顺序:`/cost-summary` 静态路径必须注册在 `/{trace_id}` 之前,防止被 UUID 路由捕获(同 D 批次踩过的坑)。

## 九、面试讲点(每条都对应真实决策)

1. **OTel GenAI semantic convention**:不自造土字段,字段名兼容业界标准,未来导出零成本
2. **三层观测穿透**:产物层(② Verifier Loop)→ 执行层(③ Trace)→ 调用层(单 LLM span 的 request/response preview),逐层 audit
3. **打开 Verifier 黑盒**:trace 与 `loop_runs` 强关联,verifier/repair span 关联具体 `iteration_id`,每一轮回炉的决策路径完整可重现
4. **精确成本核算**:每个 LLM span 按 model + tokens 算 CNY 成本,trace 自动累加;缓存命中单独计费,反映真实账单(部分 provider 缓存 5 折以下)
5. **异步落库不阻塞**:asyncio.Queue + 后台 task 批量消费,失败只 warning,业务零开销
6. **采样开关 NoOp 零开销**:`settings.tracing_enabled=False` 时所有 API 转空操作,生产可关
7. **解耦原则**:数据模型与传输层(OTel)解耦、Tracer 与业务代码解耦(ContextVar 自动 parent)、span 写库与业务路径解耦
8. **诚实边界**:不接外部 trace 后端(Jaeger / Tempo)、不做 Replay、定价是估算不是财务级精确,**明确不做的事比做的事更能体现工程判断力**

## 十、易踩坑(已踩过)

| 坑 | 现象 | 解决 |
|----|------|------|
| LangChain stream 不带 usage | 流式 chat 调用,output_tokens 一直 0 | `ChatOpenAI(stream_usage=True)`,流尾 chunk 才带 `usage_metadata` |
| LangChain 不经过 LLMClient | 我们的 chat span 没埋,只有 embedding span 在 | 在 orchestrator 层自己包 `llm_span`,从 `gathered.usage_metadata` 抽 |
| iteration_id 关联问题 | verifier span 想关联 loop_iterations 但 store 还没插入 | IterationOutcome 加 `id: UUID = Field(default_factory=uuid.uuid4)`,在 controller 预生成后 verifier span 和 store.record_iteration 共用同一个 id |
| 静态路由被 UUID 路由吞 | `GET /traces/cost-summary` 命中 `/{trace_id}` 返回 404 | 静态路由必须先注册 |
| span recorder 关闭时数据丢失 | 应用关闭时队列里有未 flush 的 span | `stop()` 先 `await queue.join(timeout=5s)` 排空再 cancel task |
| 模型名拿不到 | LangChain ChatOpenAI 用 `model_name` 字段,有些用 `model` | `getattr(model, "model_name", None) or getattr(model, "model", "chat")` 双兜底 |
| trace_id 用户找不到 | 每发一条消息都创建新 trace,用户去 `/traces` 列表里翻 | 后端把 trace_id 写进 assistant `message.meta_data`,前端每条 AI 消息底部加「执行轨迹」按钮 |
| 字段太多用户看不懂 | trace 详情面板展示 `gen_ai.usage.input_tokens` 等 | 加 `KEY_LABELS` 中文映射 + 隐藏顶部 KPI 已展示的冗余字段 + 长文本(request_summary / response_preview)单独大块展示 |

## 十一、配置项

```python
# api/app/config.py
tracing_enabled: bool = True          # 总开关
tracing_sample_rate: float = 1.0      # 采样率(0~1)
tracing_batch_size: int = 20          # 单次批量落库条数
tracing_flush_interval: float = 2.0   # 强制 flush 间隔(秒)
tracing_queue_maxsize: int = 5000     # 队列上限(满了丢最旧)
```

`K_AGENT_PRICING_OVERRIDES` 环境变量(后续可扩):JSON 覆盖内置单价表,无需改代码。

## 十二、未来演进路径

| 候选 | 价值 | 优先级 |
|------|------|--------|
| 用户自配单价(model_configs 加 input/output_price_per_1k_cny 三字段) | 财务级精确 | V0.0.6+ |
| Trace Replay(改 prompt/换模型重跑历史 trace) | LangSmith 高级功能 | backlog |
| 导出 OTel Collector / Jaeger / Tempo | 接入业界标准后端 | 可演进 |
| 跨用户聚合面板(管理员视角) | 个人项目暂不需要 | 商业化时 |
| 实时大屏(秒级刷新) | 个人项目过重 | 不做 |

---

V0.0.5 ③ Tracing 完整把「Agent 怎么做的」从黑盒变成 audit trail,与 ② Verifier Loop「Agent 做得对不对」叠加,形成「产物层 + 执行层 + 调用层」三层可观测穿透。
