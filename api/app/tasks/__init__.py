"""Celery 任务包。各阶段在此新增任务模块：

- parse   文档/图片解析（阶段3）
- memory  记忆萃取/去重（阶段4）
- beat    聚类/每日回顾（阶段7/8）
"""
from app.celery_app import celery_app


@celery_app.task(name="app.tasks.ping")
def ping() -> str:
    """连通性自检任务。"""
    return "pong"
