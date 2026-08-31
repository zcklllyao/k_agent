"""语音识别（ASR）：音频 → 文字。按 provider 适配。

- DashScope Paraformer（provider=qwen）：录音文件识别，**异步**接口
  （提交任务 → 轮询 task 状态 → 取结果 JSON → 下载 transcription_url 拿文本）。
  需要可公网访问的音频 URL（file_urls），故音频先存储拿 URL 再提交。
- OpenAI Whisper（provider=openai）：下载音频字节 → multipart 上传 → 同步返回文本。

统一入口 transcribe()，失败抛 BizError（中文提示），由上层兜底。
"""
import asyncio

import httpx

from app.core.exceptions import BizError
from app.core.logging import get_logger

logger = get_logger(__name__)

# DashScope 录音文件识别（异步）端点
_DASHSCOPE_SUBMIT = (
    "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
)
_DASHSCOPE_TASK = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
# 轮询：最多等约 60s（语音输入≤60s，转写一般几秒）
_POLL_INTERVAL = 1.5
_POLL_MAX = 40


async def transcribe(
    provider: str,
    api_key: str,
    model_name: str,
    audio_url: str,
) -> str:
    """把音频转文字。audio_url 须可公网访问（DashScope 拉取）。"""
    if provider in ("qwen",):
        return await _transcribe_dashscope(api_key, model_name or "paraformer-v2", audio_url)
    if provider in ("openai",):
        return await _transcribe_whisper(api_key, model_name or "whisper-1", audio_url)
    raise BizError(f"暂不支持的 ASR 服务商：{provider}", code=2030)


async def _transcribe_dashscope(api_key: str, model: str, audio_url: str) -> str:
    """DashScope Paraformer 异步录音文件识别。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    payload = {
        "model": model,
        "input": {"file_urls": [audio_url]},
        "parameters": {"language_hints": ["zh", "en"]},
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # 1) 提交任务
            resp = await client.post(_DASHSCOPE_SUBMIT, headers=headers, json=payload)
            if resp.status_code in (401, 403):
                raise BizError("ASR 模型 API Key 无效或无权限", code=2031)
            resp.raise_for_status()
            task_id = (resp.json().get("output") or {}).get("task_id")
            if not task_id:
                raise BizError("ASR 任务提交失败，请稍后重试", code=2032)

            # 2) 轮询任务结果
            task_url = _DASHSCOPE_TASK.format(task_id=task_id)
            for _ in range(_POLL_MAX):
                await asyncio.sleep(_POLL_INTERVAL)
                poll = await client.get(task_url, headers={"Authorization": f"Bearer {api_key}"})
                poll.raise_for_status()
                output = poll.json().get("output") or {}
                status = output.get("task_status")
                if status == "SUCCEEDED":
                    return await _extract_dashscope_text(client, output)
                if status in ("FAILED", "CANCELED"):
                    msg = output.get("message") or "识别失败"
                    raise BizError(f"语音识别失败：{msg}", code=2033)
            raise BizError("语音识别超时，请重试或缩短录音", code=2034)
    except BizError:
        raise
    except httpx.HTTPError as e:
        logger.warning("DashScope ASR 请求失败: %s", e)
        raise BizError("语音识别服务连接失败，请稍后重试", code=2035) from e


async def _extract_dashscope_text(client: httpx.AsyncClient, output: dict) -> str:
    """从成功的任务结果里取转写文本：结果是 transcription_url 指向的 JSON。"""
    results = output.get("results") or []
    texts: list[str] = []
    for item in results:
        if item.get("subtask_status") and item.get("subtask_status") != "SUCCEEDED":
            continue
        url = item.get("transcription_url")
        if not url:
            continue
        try:
            r = await client.get(url, timeout=20)
            r.raise_for_status()
            data = r.json()
            # transcripts: [{text, sentences:[...]}]
            for t in data.get("transcripts") or []:
                txt = (t.get("text") or "").strip()
                if txt:
                    texts.append(txt)
        except httpx.HTTPError as e:
            logger.warning("拉取 ASR 转写结果失败: %s", e)
    text = "".join(texts).strip()
    if not text:
        raise BizError("未识别到语音内容，请说清楚后重试", code=2036)
    return text


async def _transcribe_whisper(api_key: str, model: str, audio_url: str) -> str:
    """OpenAI Whisper：下载音频 → multipart 上传 → 同步返回。"""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            audio = await client.get(audio_url, follow_redirects=True)
            audio.raise_for_status()
            files = {"file": ("audio.mp3", audio.content, "audio/mpeg")}
            data = {"model": model}
            resp = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files=files,
                data=data,
            )
            if resp.status_code in (401, 403):
                raise BizError("ASR 模型 API Key 无效或无权限", code=2031)
            resp.raise_for_status()
            text = (resp.json().get("text") or "").strip()
            if not text:
                raise BizError("未识别到语音内容，请说清楚后重试", code=2036)
            return text
    except BizError:
        raise
    except httpx.HTTPError as e:
        logger.warning("Whisper ASR 请求失败: %s", e)
        raise BizError("语音识别服务连接失败，请稍后重试", code=2035) from e


__all__ = ["transcribe"]
