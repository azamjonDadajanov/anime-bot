// Media files (posters, screenshots, rendered chapter pages) are ordinary
// files under /media/, written by Django and served by nginx with long-lived
// cache headers — the API only ever reports their path. The browser therefore
// needs the right origin: every server block (anichopar.uz,
// admin.anichopar.uz) serves /media/, so media stays on the page's own origin
// even though the API itself moved to api.anichopar.uz — a scheme-relative
// base like //api.anichopar.uz/api therefore resolves to the page origin here.
// During development Vite serves the SPA on its own port and Django serves
// /media/ on 8000.

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'

function apiOrigin() {
  if (typeof window === 'undefined') return ''
  // '/api' and '//api.anichopar.uz/api' both name the page's own origin for
  // media purposes (see the file header).
  if (apiBaseUrl.startsWith('/')) return window.location.origin
  try {
    return new URL(apiBaseUrl, window.location.origin).origin
  } catch {
    return window.location.origin
  }
}

/** Origin that serves /media/ (nginx in production, Django in development). */
export function mediaOrigin() {
  return apiOrigin()
}

/**
 * Absolute URL for a media path. Values that are already URLs (`http(s)`,
 * `data:`, `blob:`) are returned untouched, so a stale bundle with an old
 * payload keeps rendering.
 */
export function mediaUrl(path) {
  if (!path) return ''
  if (/^(?:https?:|data:|blob:)/.test(path)) return path
  if (path.startsWith('/')) return `${apiOrigin()}${path}`
  return `${apiOrigin()}/${path}`
}

/**
 * Poster URL of a catalogue item. The normal case is a `/media/covers/...`
 * file, which nginx caches per URL; a base64 payload is only decoded for
 * bundles or cached JSON written before covers moved to media files.
 */
export function coverSrc(item) {
  const cover = item?.cover
  if (!cover) return ''
  if (cover.startsWith('/media/') || /^(?:https?:|data:|blob:)/.test(cover)) {
    return mediaUrl(cover)
  }
  return `data:${item.cover_content_type || 'image/jpeg'};base64,${cover}`
}

/**
 * URL of one rendered chapter page, straight from nginx with the version
 * token that busts the cache when the PDF behind it is re-rendered.
 */
export function chapterPageUrl(meta, pageNumber) {
  if (!meta?.base_url) return ''
  const version = meta.version ? `?v=${meta.version}` : ''
  return mediaUrl(`${meta.base_url}page_${pageNumber}.jpg${version}`)
}
