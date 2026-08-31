"""创建定时任务工具：对话里说"每天9点帮我查X"，Agent 调用本工具落一条定时研究任务。

依赖 agent_tasks 表与调度（批次②）。只在支持 function calling 的强模型路径下有意义，
弱模型默认不开（default_enabled=False）。
"""
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.agent.tools.base import ToolBuildContext, ToolSpec, register_tool
from app.core.logging import get_logger

logger = get_logger(__name__)

KEY = "create_scheduled_task"


class _ScheduleInput(BaseModel):
    instruction: str = Field(..., description="要定时研究的主题/指令，如'汇总AI Agent秋招岗位与投递链接'")
    trigger_type: str = Field(
        "daily", description="触发方式：daily(每天) / weekly(每周) / interval(每隔N小时)"
    )
    time: str | None = Field(
        None, description="触发时间 HH:MM（daily/weekly 必填），如 '09:00'"
    )
    weekday: int | None = Field(
        None, description="周几触发，0=周一..6=周日（weekly 必填）"
    )
    interval_hours: int | None = Field(
        None, description="间隔小时数（interval 必填）"
    )
    name: str | None = Field(None, description="任务名，可选，不填用指令前段")


async def _build(ctx: ToolBuildContext) -> StructuredTool:
    session = ctx.session
    user_id = ctx.user_id

    async def _run(
        instruction: str,
        trigger_type: str = "daily",
        time: str | None = None,
        weekday: int | None = None,
        interval_hours: int | None = None,
        name: str | None = None,
    ) -> str:
        from app.core.exceptions import BizError
        from app.schemas.agent_task_schema import AgentTaskUpsertRequest
        from app.services.agent_task_service import AgentTaskService

        ttype = (trigger_type or "daily").lower()
        if ttype not in ("daily", "weekly", "interval"):
            ttype = "daily"
        body = AgentTaskUpsertRequest(
            name=(name or instruction[:20] or "定时研究").strip(),
            instruction=instruction.strip(),
            trigger_type=ttype,
            trigger_time=time or ("09:00" if ttype != "interval" else None),
            trigger_weekday=weekday,
            trigger_interval_hours=interval_hours,
            enabled=True,
        )
        try:
            task = await AgentTaskService(session).create(user_id, body)
        except BizError as e:
            return f"创建定时任务失败：{e.message}"
        except Exception as e:
            logger.warning("对话创建定时任务失败: %s", e)
            return f"创建定时任务失败：{e}"
        when = task.next_run_at.strftime("%m-%d %H:%M") if task.next_run_at else "稍后"
        return (
            f"已创建定时任务「{task.name}」，将于 {when} 首次自动运行深度研究，"
            f"结果可在「深度研究」或首页查看。"
        )

    return StructuredTool.from_function(
        coroutine=_run,
        name=KEY,
        description=(
            "当用户要求定时/每天/每周/定期帮他研究、追踪、监控某个主题时，"
            "调用本工具创建一个定时研究任务。需从用户话里解析出研究主题与触发时间。"
        ),
        args_schema=_ScheduleInput,
    )


register_tool(
    ToolSpec(
        key=KEY,
        name="创建定时任务",
        description="对话里说每天X点帮我查…，自动建一个定时研究任务。",
        icon="⏰",
        builder=_build,
        default_enabled=True,
    )
)
