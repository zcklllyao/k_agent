"""健康检查：hello 接口 + 四存储连通性探测。"""
from fastapi import APIRouter

from app.config import settings
from app.core.response import success
from app.db import elastic, neo4j, postgres, redis

router = APIRouter(tags=["health"])


@router.get("/hello")
async def hello():
    """阶段0验证点：前后端跑通的 hello 接口。"""
    return success({"app": settings.app_name, "message": "你好，k-agent"})


@router.get("/health")
async def health():
    """探测四个存储是否连得上。"""
    checks = {
        "postgres": await postgres.ping(),
        "elasticsearch": await elastic.ping(),
        "neo4j": await neo4j.ping(),
        "redis": await redis.ping(),
    }
    all_ok = all(checks.values())
    return success(
        {"healthy": all_ok, "checks": checks},
        message="ok" if all_ok else "部分存储未就绪",
    )
