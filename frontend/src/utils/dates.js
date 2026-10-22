// Barcha sana ko'rishlari bitta shaklda: dd.mm.YYYY (vaqtli joylarda
// dd.mm.YYYY HH:mm). Brauzer locale'siga bog'lanmaydi.

function parse(value) {
  if (!value) return null
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function pad(n) {
  return String(n).padStart(2, '0')
}

/** `2026-10-21T…` → `21.10.2026` */
export function formatDate(value) {
  const date = parse(value)
  if (!date) return '—'
  return `${pad(date.getDate())}.${pad(date.getMonth() + 1)}.${date.getFullYear()}`
}

/** `2026-10-21T14:30:00Z` → `21.10.2026 14:30` */
export function formatDateTime(value) {
  const date = parse(value)
  if (!date) return '—'
  return `${formatDate(date)} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}
