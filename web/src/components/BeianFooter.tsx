// 备案信息页脚：ICP 备案号（必须链接到工信部官网）+ 公安联网备案号（链接到公安备案查询）
// 合规要求：网站首页显著位置展示 ICP 备案号并链接工信部；公安备案通过后展示公安备案号 + 图标
import gaImg from '@/images/logo.png'

// ICP 备案号（工信部）
const ICP_NUMBER = '浙ICP备2026043254号-1'
// 公安联网备案号：审核通过后填写（形如「浙公网安备 33xxxxxxxxxxxx 号」），留空则不展示
const POLICE_NUMBER = ''
// 公安备案号里的数字 code（用于拼查询链接），留空则不展示
const POLICE_CODE = ''

interface Props {
  dark?: boolean // 深色背景下用浅色文字
}

export default function BeianFooter({ dark }: Props) {
  const color = dark ? 'rgba(255,255,255,0.55)' : '#98A2B3'
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
        fontSize: 12,
        lineHeight: 1.6,
        color,
      }}
    >
      <a
        href="https://beian.miit.gov.cn/"
        target="_blank"
        rel="noreferrer"
        style={{ color, textDecoration: 'none' }}
      >
        {ICP_NUMBER}
      </a>
      {POLICE_NUMBER && (
        <a
          href={`https://beian.mps.gov.cn/#/query/webSearch?code=${POLICE_CODE}`}
          target="_blank"
          rel="noreferrer"
          style={{ color, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4 }}
        >
          <img src={gaImg} alt="" style={{ width: 14, height: 14, objectFit: 'contain' }} />
          {POLICE_NUMBER}
        </a>
      )}
    </div>
  )
}
