// 角色卡默认封面渐变：按组名 hash 稳定取一组高级渐变。
// 同名稳定（每次都同色），不同名分散（视觉上各异）。

const GRADIENTS: [string, string][] = [
  ['#6366F1', '#8B5CF6'], // 靛紫
  ['#155EEF', '#22D3EE'], // 蓝青
  ['#EC4899', '#8B5CF6'], // 粉紫
  ['#F59E0B', '#EF4444'], // 橙红
  ['#10B981', '#06B6D4'], // 翠青
  ['#3B82F6', '#6366F1'], // 蓝靛
  ['#A855F7', '#EC4899'], // 紫粉
  ['#0EA5E9', '#2563EB'], // 天蓝
]

function hashString(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) {
    h = (h << 5) - h + s.charCodeAt(i)
    h |= 0
  }
  return Math.abs(h)
}

// 返回一组渐变色（线性）
export function personaGradient(name: string): [string, string] {
  const key = (name || '?').trim() || '?'
  return GRADIENTS[hashString(key) % GRADIENTS.length]
}

// 返回 CSS linear-gradient 字符串
export function personaGradientCss(name: string, angle = 135): string {
  const [a, b] = personaGradient(name)
  return `linear-gradient(${angle}deg, ${a}, ${b})`
}

// 取名字首字（中文取首字，英文取首字母大写）
export function personaInitial(name: string): string {
  const n = (name || '').trim()
  if (!n) return '?'
  return n.slice(0, 1).toUpperCase()
}
