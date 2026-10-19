// Response cache for the catalogue.
//
// Every cover used to travel as base64 inside the JSON, so dropping a response
// on the floor saved the poster too. Covers are media files now, but the JSON
// is still worth keeping: going back to the home page or reopening a title
// answers from memory instead of the network, and the images themselves are
// then already referenced by a URL the browser has cached.
//
// Stale-while-revalidate: an entry older than its TTL is still served (so the
// UI never waits) while one background request refreshes it.

const store = new Map()
const inflight = new Map()

// Bound the cache: the catalogue is the only big payload, so a few dozen
// entries cover every screen without leaking memory across a long session.
const MAX_ENTRIES = 80

const STALE_FACTOR = 10
const MIN_STALE_TTL = 5 * 60_000

export function cacheKey(url, params) {
  if (!params || !Object.keys(params).length) return url
  const query = Object.keys(params)
    .sort()
    .map((key) => `${key}=${encodeURIComponent(params[key])}`)
    .join('&')
  return `${url}?${query}`
}

function remember(key, entry) {
  // Re-insert so Map iteration order stays "least recently written first".
  store.delete(key)
  store.set(key, entry)
  while (store.size > MAX_ENTRIES) {
    const oldest = store.keys().next().value
    store.delete(oldest)
  }
}

/**
 * Cached payload for `key`.
 * `{ data, fresh }` when the entry may be used without touching the network,
 * `null` when it is missing or too old to show.
 */
export function readCache(key, ttl) {
  const entry = store.get(key)
  if (!entry || !ttl) return null
  const age = Date.now() - entry.at
  if (age > Math.max(ttl * STALE_FACTOR, MIN_STALE_TTL)) {
    store.delete(key)
    return null
  }
  remember(key, entry)
  return { data: entry.data, fresh: age <= ttl }
}

export function writeCache(key, data, ttl) {
  if (!ttl || data === undefined || data === null) return
  remember(key, { data, at: Date.now(), ttl })
}

/** Drop every entry whose key starts with `prefix` (after a mutation). */
export function dropCache(prefix) {
  for (const key of [...store.keys()]) {
    if (key.startsWith(prefix)) store.delete(key)
  }
}

/** Everything must go when the viewer changes (login, logout, expiry). */
export function clearCache() {
  store.clear()
  inflight.clear()
}

/**
 * Run `refresh` once for `key` and store its result; concurrent callers share
 * the same request. Failures leave the stale entry in place.
 */
export function revalidate(key, refresh, ttl) {
  const running = inflight.get(key)
  if (running) return running
  const request = Promise.resolve()
    .then(refresh)
    .then((data) => {
      writeCache(key, data, ttl)
      return data
    })
    .catch(() => null)
    .finally(() => inflight.delete(key))
  inflight.set(key, request)
  return request
}
