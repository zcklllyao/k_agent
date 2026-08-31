"""Verifier Loop —— Loop Engineering 在 k-agent 的完整落地(V0.0.5 ②)。

把 Agent 从「LLM 自循环」升级为「外部系统驱动的循环 + 独立验证 + 智能修复 + 状态持久化」。

模块结构:
- models      Pydantic 中间数据结构(LoopRunSnapshot / IterationOutcome 等)
- store       落库 / 恢复 / 历史查询(SQLAlchemy)
- rubric/     评分维度定义(基类 + research / task)
- verifier/   独立 LLM-as-judge(基类 + 同模型 self-critique + 跨 family critic)
- repair/     修复策略(基类 + 贪心补丁 + 章节重写)
- policy      决策器:何时回炉 / 用哪个 repair / 何时停
- controller  状态机:generate → verify → decide 三段式 + 异常护栏

设计核心(三个解耦):
1. Verify ⊥ Generate    Verifier 独立 session,不带 Generator 上下文(避免自夸偏见)
2. Controller ⊥ Task    通用状态机原语,wire-up 不同任务只是一行
3. State ⊥ Process      状态全在 loop_runs/loop_iterations 表,可中断恢复 + audit trail
"""
