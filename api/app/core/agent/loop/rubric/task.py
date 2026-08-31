"""定时任务结果 Rubric:复用 research rubric。

定时任务的产物本质也是研究报告(经 research engine 生成),复用 RESEARCH_RUBRIC 即可。
这里单独留一个名字是为了:
- 未来定时任务可能有不同的评分侧重(如更看重「时效性」)
- 让 controller 用 task_type 取 rubric 时语义清晰(task_type=agent_task → rubric=task)
"""
from app.core.agent.loop.rubric.research import RESEARCH_RUBRIC

# 当前直接复用,字段定义见 research.py
TASK_RUBRIC = RESEARCH_RUBRIC.model_copy(update={"name": "task"})
