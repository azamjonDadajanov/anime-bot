// Shared catalogue vocabulary and formatting. Every card, rail and detail
// screen reads its labels from here so the interface never drifts apart.

export const MEDIA_TYPE_LABELS = {
  movie: 'Kino',
  anime: 'Anime',
  series: 'Serial',
  manga: 'Manga',
  podcast: 'Podcast',
}

export const MEDIA_TYPE_ICONS = {
  movie: 'bi-film',
  anime: 'bi-stars',
  series: 'bi-collection-play',
  manga: 'bi-journal-bookmark',
  podcast: 'bi-mic',
}

export const MEDIA_TYPE_JP = {
  movie: '映画',
  anime: 'アニメ',
  series: 'ドラマ',
  manga: '漫画',
  podcast: '音声',
}

export const STATUS_LABELS = {
  upcoming: 'Kutilmoqda',
  ongoing: 'Davom etmoqda',
  completed: 'Tugallangan',
}

export function typeLabel(item) {
  return MEDIA_TYPE_LABELS[item?.type] || item?.type || 'Media'
}

export function typeIcon(item) {
  return MEDIA_TYPE_ICONS[item?.type] || 'bi-film'
}

export function statusLabel(item) {
  return STATUS_LABELS[item?.status] || item?.status || "Noma'lum"
}

/**
 * Genre labels of a title. The API adds `genre_names` next to the editable id
 * list; older cached payloads may still hold display strings in `genres`.
 */
export function genreNames(item) {
  if (!item) return []
  if (Array.isArray(item.genre_names)) return item.genre_names.filter(Boolean)
  if (Array.isArray(item.genres)) return item.genres.filter((value) => typeof value === 'string')
  return []
}

export function releaseLabel(item) {
  return item?.release_year ? String(item.release_year) : "Yil yo'q"
}

export function episodeLabel(item) {
  const count = Number(item?.episode_count) || 0
  return count ? `${count} qism` : "Qismlar yo'q"
}

const MONTHS = ['YAN', 'FEV', 'MAR', 'APR', 'MAY', 'IYN', 'IYL', 'AVG', 'SEN', 'OKT', 'NOY', 'DEK']

/** `2026-10-17T…` → `{ day: '17', month: 'OKT' }` for the drop timeline. */
export function dateStamp(value) {
  if (!value) return { day: '—', month: '—' }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return { day: '—', month: '—' }
  return {
    day: String(date.getDate()).padStart(2, '0'),
    month: MONTHS[date.getMonth()],
  }
}

export function sortByNewest(items) {
  return [...items].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
}

export function sortByRating(items) {
  return [...items].sort((a, b) => (Number(b.rating) || 0) - (Number(a.rating) || 0))
}

/**
 * A title's live score: the average of the 1-10 votes people actually gave.
 * Titles nobody has scored yet have no average (null) — the catalogue's own
 * `rating` stays a fallback only.
 */
export function ratingAverage(item) {
  const count = Number(item?.rating_count) || 0
  const average = Number(item?.rating_average) || 0
  return count > 0 && average > 0 ? average : null
}

/** How many accounts scored the title. */
export function ratingVotes(item) {
  return Number(item?.rating_count) || 0
}

/** `8.0 → 8`, `8.45 → 8.5`, `7.50 → 7.5` — the score the UI prints. */
export function formatScore(value) {
  const number = Number(value)
  if (!Number.isFinite(number) || number <= 0) return null
  return number.toFixed(1).replace(/\.0$/, '')
}

/**
 * «Top reyting» ordering: the highest score first, the most votes on a tie.
 * Scored titles always outrank unscored ones, which keep their catalogue
 * order at the bottom of the list.
 */
export function sortByTopRating(items) {
  return [...items].sort((a, b) => {
    const scoreA = ratingAverage(a)
    const scoreB = ratingAverage(b)
    if (scoreA !== null && scoreB === null) return -1
    if (scoreA === null && scoreB !== null) return 1
    if (scoreA !== null && scoreB !== null) {
      if (scoreB !== scoreA) return scoreB - scoreA
      const votes = ratingVotes(b) - ratingVotes(a)
      if (votes) return votes
    }
    return (Number(b.rating) || 0) - (Number(a.rating) || 0)
  })
}

export function normalizeList(data) {
  if (Array.isArray(data)) return data
  return data?.results || []
}
