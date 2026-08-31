import type { ModelType, Provider } from '@/api/models'

export const TYPE_OPTIONS: { label: string; value: ModelType }[] = [
  { label: '对话模型', value: 'chat' },
  { label: '多模态模型', value: 'multimodal' },
  { label: 'Embedding 模型', value: 'embedding' },
  { label: 'Rerank 模型', value: 'rerank' },
  { label: '联网搜索', value: 'websearch' },
  { label: '语音识别 ASR', value: 'asr' },
  { label: '审稿模型 Verifier', value: 'verifier' },
]

export const TYPE_LABEL: Record<ModelType, string> = {
  chat: '对话',
  multimodal: '多模态',
  embedding: 'Embedding',
  rerank: 'Rerank',
  websearch: '联网搜索',
  asr: '语音识别',
  verifier: '审稿 Verifier',
}

export const PROVIDER_OPTIONS: { label: string; value: Provider }[] = [
  { label: 'OpenAI', value: 'openai' },
  { label: '通义千问', value: 'qwen' },
  { label: '豆包', value: 'doubao' },
  { label: 'DeepSeek', value: 'deepseek' },
  { label: '智谱', value: 'zhipu' },
  { label: '百度千帆（联网搜索）', value: 'qianfan' },
  { label: 'Tavily（联网搜索）', value: 'tavily' },
]

// 各 provider 默认 base_url，与后端 provider.py 保持一致
export const PROVIDER_DEFAULT_BASE_URL: Record<Provider, string> = {
  openai: 'https://api.openai.com/v1',
  qwen: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  doubao: 'https://ark.cn-beijing.volces.com/api/v3',
  deepseek: 'https://api.deepseek.com',
  zhipu: 'https://open.bigmodel.cn/api/paas/v4',
  qianfan: '',
  tavily: '',
}

export const CAPABILITY_OPTIONS = [
  { label: 'Function Call（工具调用）', value: 'function_call' },
  { label: 'Vision（图片理解）', value: 'vision' },
]

// 各供应商获取 API Key 的官网地址（密钥管理控制台）
export const PROVIDER_LINKS: {
  label: string
  desc: string
  url: string
}[] = [
  {
    label: '智谱 AI',
    desc: '国内，注册即送额度，chat / embedding / 多模态 / rerank 齐全，推荐新手首选',
    url: 'https://open.bigmodel.cn/usercenter/apikeys',
  },
  {
    label: 'DeepSeek',
    desc: '国内，对话与推理性价比高，仅 chat（不提供向量模型）',
    url: 'https://platform.deepseek.com/api_keys',
  },
  {
    label: '通义千问（阿里云百炼）',
    desc: '国内，chat / 多模态 / embedding / rerank 都有，OpenAI 兼容',
    url: 'https://bailian.console.aliyun.com/?apiKey=1#/api-key',
  },
  {
    label: '豆包（火山方舟）',
    desc: '国内，字节跳动，chat / 多模态，需在控制台开通模型',
    url: 'https://console.volcengine.com/ark',
  },
  {
    label: 'OpenAI',
    desc: '海外，需科学上网与海外支付，GPT 系列',
    url: 'https://platform.openai.com/api-keys',
  },
  {
    label: '百度千帆（联网搜索）',
    desc: '联网搜索数据源，中文实时信息效果好',
    url: 'https://console.bce.baidu.com/iam/#/iam/apikey/list',
  },
  {
    label: 'Tavily（联网搜索）',
    desc: '海外联网搜索，每月有免费额度',
    url: 'https://app.tavily.com/home',
  },
  {
    label: '语音识别 ASR（通义千问 DashScope）',
    desc: '语音转文字，与通义共用一个 DashScope Key，模型名填 paraformer-v2；也可用 OpenAI whisper-1',
    url: 'https://bailian.console.aliyun.com/?apiKey=1#/api-key',
  },
]
