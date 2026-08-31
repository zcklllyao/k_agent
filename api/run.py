"""本地开发启动入口：python run.py"""
import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
        # SSE 是长连接，停止/热重载时若等其自然关闭会卡住；
        # 限定优雅关闭最多等 3 秒，超时强制断开，避免 reload 挂死。
        timeout_graceful_shutdown=3,
    )
