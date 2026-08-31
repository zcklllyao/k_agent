import { useEffect, useRef, useState } from 'react'
import { Button, Tooltip, Upload, message } from 'antd'
import { AudioOutlined, LoadingOutlined } from '@ant-design/icons'
import { chatApi } from '@/api/chat'

// 语音输入按钮：统一入口，内部自动选路
// 路 B（优先）：录音 → 上传后端 ASR 模型转写
// 路 A（降级）：未配 ASR 模型 + 浏览器支持 Web Speech → 前端直接识别
// HTTP 兜底：拿不到麦克风时提供「上传音频文件」入口
// 转写结果通过 onResult 回填输入框（不自动发送）
interface Props {
  onResult: (text: string) => void
  disabled?: boolean
  size?: number // 图标字号
}

const MAX_RECORD_MS = 60_000 // 单次录音≤60s

type SpeechRecognitionLike = {
  lang: string
  continuous: boolean
  interimResults: boolean
  start: () => void
  stop: () => void
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null
  onerror: ((e: { error?: string }) => void) | null
  onend: (() => void) | null
}

function getSpeechRecognition(): SpeechRecognitionLike | null {
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike
    webkitSpeechRecognition?: new () => SpeechRecognitionLike
  }
  const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition
  return Ctor ? new Ctor() : null
}

export default function VoiceInputButton({ onResult, disabled, size = 19 }: Props) {
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const timerRef = useRef<number | null>(null)
  const speechRef = useRef<SpeechRecognitionLike | null>(null)

  useEffect(() => {
    return () => {
      // 卸载清理
      if (timerRef.current) window.clearTimeout(timerRef.current)
      streamRef.current?.getTracks().forEach((t) => t.stop())
      try {
        speechRef.current?.stop()
      } catch {
        /* ignore */
      }
    }
  }, [])

  // 路 A：浏览器 Web Speech 直接识别
  const startWebSpeech = () => {
    const rec = getSpeechRecognition()
    if (!rec) {
      message.warning('当前环境不支持语音输入，可在「模型配置」添加 ASR 模型，或换用 Chrome')
      return false
    }
    rec.lang = 'zh-CN'
    rec.continuous = false
    rec.interimResults = false
    rec.onresult = (e) => {
      const text = e.results?.[0]?.[0]?.transcript || ''
      if (text) onResult(text)
    }
    rec.onerror = (e) => {
      if (e.error === 'not-allowed') message.error('麦克风权限被拒绝')
      else if (e.error !== 'aborted') message.error('语音识别失败，请重试')
      setRecording(false)
    }
    rec.onend = () => setRecording(false)
    speechRef.current = rec
    setRecording(true)
    rec.start()
    return true
  }

  // 路 B：录音 → 后端 ASR 转写
  const stopAndTranscribe = async () => {
    const mr = mediaRecorderRef.current
    if (!mr) return
    mr.stop()
  }

  const onClick = async () => {
    if (busy) return
    // 正在录音 → 停止
    if (recording) {
      if (speechRef.current) {
        try {
          speechRef.current.stop()
        } catch {
          /* ignore */
        }
        return
      }
      stopAndTranscribe()
      return
    }

    // 没有麦克风 API（多为 HTTP 非安全上下文）→ 直接试 Web Speech，否则提示用上传
    if (typeof navigator.mediaDevices?.getUserMedia !== 'function') {
      if (!startWebSpeech()) {
        message.info('当前为非安全连接（HTTP），可用下方「上传音频」按钮，或换 HTTPS 访问')
      }
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const mr = new MediaRecorder(stream)
      chunksRef.current = []
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      mr.onstop = async () => {
        streamRef.current?.getTracks().forEach((t) => t.stop())
        streamRef.current = null
        if (timerRef.current) window.clearTimeout(timerRef.current)
        const blob = new Blob(chunksRef.current, { type: mr.mimeType || 'audio/webm' })
        setRecording(false)
        if (blob.size < 1000) {
          message.warning('录音太短了')
          return
        }
        await transcribeBlob(blob)
      }
      mediaRecorderRef.current = mr
      mr.start()
      setRecording(true)
      timerRef.current = window.setTimeout(() => {
        if (mediaRecorderRef.current?.state === 'recording') stopAndTranscribe()
      }, MAX_RECORD_MS)
    } catch {
      message.error('无法访问麦克风，请检查权限或换用 HTTPS 访问')
    }
  }

  // 上传音频走后端 ASR（路 B）
  const transcribeBlob = async (blob: Blob) => {
    setBusy(true)
    const hide = message.loading('正在识别语音…', 0)
    try {
      const { data } = await chatApi.transcribe(blob)
      hide()
      if (data.text) {
        onResult(data.text)
        message.success('已转写，可编辑后发送')
      }
    } catch (e) {
      hide()
      // 未配 ASR 模型 → 降级到浏览器 Web Speech
      const msg = (e as Error).message || ''
      if (msg.includes('语音识别') || msg.includes('模型')) {
        message.info('未配置 ASR 模型，尝试用浏览器识别…')
        startWebSpeech()
      } else {
        message.error(msg || '语音识别失败')
      }
    } finally {
      setBusy(false)
    }
  }

  const beforeUpload = (file: File) => {
    transcribeBlob(file)
    return Upload.LIST_IGNORE
  }

  return (
    <Tooltip title={recording ? '点击停止录音' : '语音输入'}>
      <span style={{ display: 'inline-flex' }}>
        {/* 有麦克风走录音；非安全上下文(HTTP)拿不到麦克风时，改为音频文件上传 */}
        {typeof navigator.mediaDevices?.getUserMedia === 'function' ? (
          <Button
            type="text"
            shape="circle"
            disabled={disabled}
            onClick={onClick}
            icon={
              busy ? (
                <LoadingOutlined style={{ fontSize: size }} />
              ) : (
                <AudioOutlined
                  style={{ fontSize: size, color: recording ? '#FF5D34' : undefined }}
                />
              )
            }
            className={recording ? 'voice-btn-recording' : undefined}
          />
        ) : (
          <Upload accept="audio/*" showUploadList={false} beforeUpload={beforeUpload}>
            <Button
              type="text"
              shape="circle"
              disabled={disabled || busy}
              icon={
                busy ? (
                  <LoadingOutlined style={{ fontSize: size }} />
                ) : (
                  <AudioOutlined style={{ fontSize: size }} />
                )
              }
            />
          </Upload>
        )}
      </span>
    </Tooltip>
  )
}
