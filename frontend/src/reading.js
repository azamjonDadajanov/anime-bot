import { hasAccessToken, readingApi } from './apis/api'

const STORAGE_KEY = 'kino_top_reading'

function readStore() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function writeStore(store) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store))
  } catch {
    /* ignore quota / privacy mode errors */
  }
}

function toMillis(value) {
  if (!value) return 0
  const time = typeof value === 'number' ? value : Date.parse(value)
  return Number.isFinite(time) ? time : 0
}

export function orderParts(parts = []) {
  return [...parts].sort((a, b) => {
    const seasonA = a.season_number || 0
    const seasonB = b.season_number || 0
    if (seasonA !== seasonB) return seasonA - seasonB
    return a.number - b.number
  })
}

export function getLocalTitleProgress(slug) {
  return readStore()[slug] || {}
}

export function saveLocalProgress(slug, part, { page, isRead } = {}) {
  const store = readStore()
  const title = store[slug] || {}
  const existing = title[part.id] || {}
  title[part.id] = {
    partNumber: part.number,
    seasonNumber: part.season_number ?? null,
    page: page !== undefined ? page : existing.page || 1,
    isRead: isRead !== undefined ? isRead : existing.isRead || false,
    updatedAt: Date.now(),
  }
  store[slug] = title
  writeStore(store)
  return title[part.id]
}

export function mergeRecords(local, server) {
  const localTime = toMillis(local?.updatedAt)
  const serverTime = toMillis(server?.updatedAt)
  const newest = serverTime > localTime ? server : local
  return {
    partNumber: server?.partNumber ?? local?.partNumber,
    seasonNumber: server?.seasonNumber ?? local?.seasonNumber ?? null,
    page: newest?.page || 1,
    isRead: Boolean(local?.isRead || server?.isRead),
    updatedAt: Math.max(localTime, serverTime),
  }
}

export async function loadTitleProgress(slug) {
  const local = getLocalTitleProgress(slug)
  const server = {}
  if (hasAccessToken()) {
    try {
      const records = await readingApi.list(slug)
      records.forEach((record) => {
        server[record.part] = {
          partNumber: record.part_number,
          seasonNumber: record.season_number,
          page: record.page,
          isRead: record.is_read,
          updatedAt: record.updated_at,
        }
      })
    } catch {
      /* offline or expired session — fall back to local progress */
    }
  }
  const ids = new Set([...Object.keys(local), ...Object.keys(server)])
  const merged = {}
  ids.forEach((id) => {
    merged[id] = mergeRecords(local[id], server[id])
  })
  return merged
}

export function computeResume(progress, parts) {
  const entries = Object.entries(progress || {})
    .map(([id, record]) => ({ partId: Number(id), ...record }))
    .filter((entry) => entry.partNumber)
  if (!entries.length) return null

  entries.sort((a, b) => b.updatedAt - a.updatedAt)
  const latest = entries[0]
  const ordered = orderParts(parts)
  const index = ordered.findIndex((part) => part.number === latest.partNumber)
  if (index === -1) return null

  if (latest.isRead) {
    const next = ordered[index + 1]
    if (next) return { part: next, page: 1 }
  }
  return { part: ordered[index], page: latest.page }
}
