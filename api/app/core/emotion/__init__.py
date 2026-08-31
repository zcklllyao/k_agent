"""情绪记忆子系统：对话情绪结构化分析 + 画像聚合。

- ontology：情绪受控词表（离散情绪 + valence-arousal 参考坐标）
- prompts/：情绪抽取提示词模板
- analyzer：调用 LLM 结构化分析单段用户文本的情绪
- aggregator：把最近 N 条情绪记录聚合成「当前情绪画像」
情绪数据独立于 Neo4j 记忆图谱，仅存 PG。
"""
