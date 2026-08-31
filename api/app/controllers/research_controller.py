"""深度研究路由：发起流式研究 + 续传 + 报告管理 + 存知识库。"""
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.exceptions import BizError
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.report_share_schema import ReportShareCreateRequest
from app.schemas.research_schema import (
    OptimizeTopicRequest,
    ResearchStartRequest,
    SaveToKbRequest,
)
from app.services.report_share_service import ReportShareService
from app.services.research_service import ResearchService

router = APIRouter(prefix="/research", tags=["research"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.post("/optimize-topic")
async def optimize_topic(
    body: OptimizeTopicRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """一键润色研究指令（深度研究主题 + 定时任务研究指令共用）。"""
    optimized = await ResearchService(session).optimize_topic(user.id, body.topic)
    return success({"optimized": optimized})


# ── 报告分享（静态路径，必须在 /{report_id} 之前注册避免 uuid 路由冲突）──


@router.get("/shares")
async def list_report_shares(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ReportShareService(session)
    items = await service.list_shares(user.id)
    return success([service.share_out(s) for s in items])


@router.delete("/shares/{share_id}")
async def revoke_report_share(
    share_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await ReportShareService(session).revoke(user.id, share_id)
    return success(message="已取消分享")


@router.post("/stream")
async def start_research_stream(
    body: ResearchStartRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """发起一次深度研究并 SSE 流式推进度（首事件 meta 带 report_id）。"""
    service = ResearchService(session)
    return StreamingResponse(
        service.stream_research(user.id, body),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/{report_id}/notify")
async def notify_report(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """手动将已完成的研究报告推送到飞书。"""
    data = await ResearchService(session).notify_report(user.id, report_id)
    return success(data, "已推送到飞书")


@router.get("/{report_id}/events")
async def research_resume_events(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """断线重连续传：生成中补推快照+续接；已结束回放最终报告。"""
    service = ResearchService(session)
    return StreamingResponse(
        service.resume_events(user.id, report_id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("")
async def list_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    items, total = await ResearchService(session).list_reports(user.id, page, page_size)
    return success({"items": items, "total": total})


@router.get("/{report_id}")
async def get_report(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await ResearchService(session).get_detail(user.id, report_id))


@router.get("/{report_id}/loop")
async def get_report_loop(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """V0.0.5 ② Verifier Loop 详情:LoopRun + 各轮 iteration 明细。

    前端「质量评分卡」用它拉雷达图维度分 + 各轮 feedback + 模型审计。
    报告生成时未跑 verifier(开关关闭或 engine 内部异常)时返回 None,前端不显示评分卡。
    """
    return success(await ResearchService(session).get_loop_detail(user.id, report_id))


@router.delete("/{report_id}")
async def delete_report(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await ResearchService(session).delete(user.id, report_id)
    return success(message="已删除")


@router.post("/{report_id}/save-to-kb")
async def save_report_to_kb(
    report_id: uuid.UUID,
    body: SaveToKbRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    data = await ResearchService(session).save_to_kb(user.id, report_id, body.kb_id)
    return success(data, "已存入知识库，正在解析入库")


@router.post("/{report_id}/share")
async def share_report(
    report_id: uuid.UUID,
    body: ReportShareCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """生成/刷新报告的公开只读分享链接。"""
    service = ReportShareService(session)
    share = await service.create_share(
        user.id, report_id, body.expire_days, body.title
    )
    return success(service.share_out(share), "已生成分享链接")


@router.get("/{report_id}/export/docx")
async def export_report_docx(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """导出报告为 Word(.docx) 文件。"""
    from urllib.parse import quote

    from app.core.export.md_to_docx import markdown_to_docx_bytes

    detail = await ResearchService(session).get_detail(user.id, report_id)
    if detail.get("status") != "done" or not detail.get("report_md"):
        raise BizError("报告尚未完成，无法导出", code=3075)
    title = detail.get("title") or detail.get("topic") or "研究报告"
    data = markdown_to_docx_bytes(title, detail["report_md"])
    filename = quote(f"{title}.docx")
    return Response(
        content=data,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
        },
    )
