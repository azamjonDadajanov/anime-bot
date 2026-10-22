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

// Barcha datelar dd.mm.YYYY ko'rinishida (frontend/src/utils/dates.js).
export { formatDate, formatDateTime } from '../../utils/dates'

// Covers are media files now; re-exported under the name the profile screens
// already use.
export { coverSrc as coverUrl } from '../../apis/mediaUrl'
