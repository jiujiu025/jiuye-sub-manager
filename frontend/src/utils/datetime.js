/**
 * 统一格式化后端时间。
 * SQLite 可能返回不带时区的 UTC 字符串，先按 UTC 解析，再固定显示为上海时间。
 */
export function parseApiDate(value) {
  if (!value) return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  const text = String(value).trim()
  if (!text) return null
  const normalized = text.includes('T') ? text : text.replace(' ', 'T')
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized)
  const date = new Date(hasTimezone ? normalized : `${normalized}Z`)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatApiDate(value, fallback = '-') {
  const date = parseApiDate(value)
  if (!date) return fallback
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).format(date).replaceAll('/', '-')
}
