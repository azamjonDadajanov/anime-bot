export const TELEGRAM_BOT_URL = 'https://t.me/adgfdsfbot'

export const MEDIA_TYPE_LABELS = {
  movie: 'Kino',
  anime: 'Anime',
  series: 'Serial',
  manga: 'Manga',
}

export const PLAN_STATUS_LABELS = {
  pending: "Ko'rib chiqilmoqda",
  approved: 'Tasdiqlangan',
  rejected: 'Rad etilgan',
  cancelled: 'Bekor qilingan',
}

export const PLAN_STATUS_COLORS = {
  pending: 'yellow',
  approved: 'green',
  rejected: 'red',
  cancelled: 'gray',
}

export function errorText(error) {
  const data = error.response?.data
  if (!data) return "Server bilan bog'lanishda xatolik yuz berdi."
  if (typeof data.detail === 'string') return data.detail
  if (typeof data === 'string') return data
  return Object.values(data).flat().map(String).join(' ')
}

export function formatPrice(value) {
  const amount = Number(value) || 0
  if (amount <= 0) return 'Bepul'
  return `${amount.toLocaleString('uz-UZ')} so'm`
}

export function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString('uz-UZ', { day: '2-digit', month: 'long', year: 'numeric' })
}

export function formatDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('uz-UZ', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function coverUrl(item) {
  if (!item?.cover) return ''
  return `data:${item.cover_content_type || 'image/jpeg'};base64,${item.cover}`
}
