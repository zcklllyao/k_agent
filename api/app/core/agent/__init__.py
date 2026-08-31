"""Agent 工具编排子系统（阶段5 智能问答）。

把知识库检索、记忆检索、联网搜索做成工具，由 LangChain Agent 自主决定调用（方案B）：
- 强模型（支持 function calling）走原生工具循环
- 弱模型走 ToolOrchestrator（prompt 模拟 ReAct）降级
两条路径都以 SSE 流式输出，并收集引用与工具调用事件。
"""
