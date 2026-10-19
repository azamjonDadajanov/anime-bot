import axios from 'axios'

import { cacheKey, clearCache, dropCache, readCache, revalidate, writeCache } from './apiCache'
import { chapterPageUrl } from './mediaUrl'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'
const ACCESS_TOKEN_KEY = 'anichopar_access'
const REFRESH_TOKEN_KEY = 'anichopar_refresh'

export const api = axios.create({
  baseURL: apiBaseUrl,
  headers: { 'Content-Type': 'application/json' },
})

// How long a GET response may be reused without asking the server again.
// Anything not listed here (views, reading progress, profile activity, AI
// chat) is always fetched live.
const CACHE_RULES = [
  { match: /^\/catalog\/random\/?$/, ttl: 0 },
  { match: /^\/catalog\/(latest|popular|upcoming|movies|anime|manga|series)\/?$/, ttl: 45_000 },
  { match: /^\/catalog\/[^/]+\/$/, ttl: 5 * 60_000 },
  { match: /^\/catalog\/?$/, ttl: 45_000 },
  { match: /^\/auth\/favorites\/?$/, ttl: 45_000 },
  { match: /^\/auth\/subscription\/plans\/?$/, ttl: 10 * 60_000 },
  { match: /^\/game\/titles\/?$/, ttl: 10 * 60_000 },
]

function cacheTtl(url) {
  const rule = CACHE_RULES.find((entry) => entry.match.test(url))
  return rule ? rule.ttl : 0
}

/**
 * GET with a memory cache: a fresh hit answers instantly, a stale hit answers
 * immediately too while one background request refreshes it. Used by every
 * catalogue screen, so flipping between pages costs no network round trip and
 * no re-download of the (now cached) cover files.
 */
async function cachedGet(url, params) {
  const ttl = cacheTtl(url)
  const key = cacheKey(url, params)
  const hit = readCache(key, ttl)
  if (hit) {
    if (!hit.fresh) {
      revalidate(key, async () => (await api.get(url, { params })).data, ttl)
    }
    return hit.data
  }
  const { data } = await api.get(url, { params })
  writeCache(key, data, ttl)
  return data
}

let refreshRequest

api.interceptors.request.use((config) => {
  const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY)
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const request = error.config
    const isAuthRequest = request?.url?.includes('/auth/token/')
      || request?.url?.includes('/auth/register/')
      || request?.url?.includes('/auth/token/refresh/')

    if (error.response?.status !== 401 || !request || request._retry || isAuthRequest) {
      return Promise.reject(error)
    }

    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)
    if (!refreshToken) return Promise.reject(error)

    request._retry = true
    try {
      refreshRequest ??= axios.post(`${apiBaseUrl}/auth/token/refresh/`, { refresh: refreshToken })
      const { data } = await refreshRequest
      localStorage.setItem(ACCESS_TOKEN_KEY, data.access)
      request.headers.Authorization = `Bearer ${data.access}`
      return api(request)
    } catch (refreshError) {
      localStorage.removeItem(ACCESS_TOKEN_KEY)
      localStorage.removeItem(REFRESH_TOKEN_KEY)
      window.dispatchEvent(new Event('anichopar:auth-expired'))
      return Promise.reject(refreshError)
    } finally {
      refreshRequest = undefined
    }
  },
)

// An expired refresh token means the session is gone; nothing cached for that
// viewer may be shown to whoever signs in next.
if (typeof window !== 'undefined') {
  window.addEventListener('anichopar:auth-expired', () => clearCache())
}

export const authApi = {
  async login(credentials) {
    const { data } = await api.post('/auth/token/', credentials)
    localStorage.setItem(ACCESS_TOKEN_KEY, data.access)
    localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh)
    // A different viewer: everything cached for the previous one is wrong.
    clearCache()
    return data
  },
  async register(details) {
    await api.post('/auth/register/', details)
    return this.login({ username: details.username, password: details.password })
  },
  async loginWithTelegram(credentials) {
    const { data } = await api.post('/auth/telegram/mini-app/', credentials)
    localStorage.setItem(ACCESS_TOKEN_KEY, data.access)
    localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh)
    clearCache()
    return data
  },
  async currentUser() {
    const { data } = await api.get('/auth/me/')
    return data
  },
  async updateProfile(profile) {
    const { data } = await api.patch('/auth/me/', profile)
    return data
  },
  logout() {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
    clearCache()
  },
}

export function hasAccessToken() {
  return Boolean(localStorage.getItem(ACCESS_TOKEN_KEY))
}

export function getAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function getApiBaseUrl() {
  return apiBaseUrl
}

export const mediaApi = {
  async catalog(params = {}) {
    return cachedGet('/catalog/', params)
  },
  async favorites(params = {}) {
    return cachedGet('/auth/favorites/', params)
  },
  async toggleFavorite(slug) {
    const { data } = await api.post('/auth/favorites/toggle/', { slug })
    // The catalogue embeds favourite flags: drop both so the hearts re-render.
    dropCache('/auth/favorites')
    dropCache('/catalog')
    return data
  },
  async detail(slug) {
    return cachedGet(`/catalog/${encodeURIComponent(slug)}/`)
  },
  async recordView(slug, part) {
    const { data } = await api.post(
      `/catalog/${encodeURIComponent(slug)}/view/`,
      part ? { part } : {},
    )
    // "Popular" is derived from views; a fresh one should show the change.
    dropCache('/catalog/popular')
    return data
  },
  async latest(params = {}) {
    return cachedGet('/catalog/latest/', params)
  },
  async popular(params = {}) {
    return cachedGet('/catalog/popular/', params)
  },
  async upcoming(params = {}) {
    return cachedGet('/catalog/upcoming/', params)
  },
  async movies(params = {}) {
    return cachedGet('/catalog/movies/', params)
  },
  async anime(params = {}) {
    return cachedGet('/catalog/anime/', params)
  },
  async manga(params = {}) {
    return cachedGet('/catalog/manga/', params)
  },
  async series(params = {}) {
    return cachedGet('/catalog/series/', params)
  },
  async random(params = {}) {
    return cachedGet('/catalog/random/', params)
  },
  /**
   * Rendered page from the API (Django renders it on demand). The reader
   * prefers `partPageFileUrl` — the nginx URL — and falls back to this one
   * when the file is not on disk yet.
   */
  partPageUrl(partId, number) {
    return `${apiBaseUrl}/parts/${partId}/pages/${number}/`
  },
  /**
   * Same page straight from nginx (`/media/manga/pages/...`), cache-busted
   * with the version token from the page metadata. Returns '' until the
   * metadata for the part has loaded.
   */
  partPageFileUrl(meta, partId, number) {
    return chapterPageUrl(meta, number) || this.partPageUrl(partId, number)
  },
  async partPagesMeta(partId) {
    const { data } = await api.get(`/parts/${partId}/pages/`)
    return data
  },
  async uploadPartPdf(partId, file, onProgress) {
    const form = new FormData()
    form.append('file', file)
    const { data } = await api.post(`/parts/${partId}/pdf/upload/`, form, {
      onUploadProgress: (event) => {
        if (onProgress && event.total) {
          onProgress(Math.round((event.loaded * 100) / event.total))
        }
      },
    })
    return data
  },
  async deletePartPdf(partId) {
    await api.delete(`/parts/${partId}/pdf/`)
  },
}

export const profileApi = {
  async overview() {
    const { data } = await api.get('/auth/profile/')
    return data
  },
  async activity() {
    const { data } = await api.get('/auth/profile/activity/')
    return data
  },
  async history(params = {}) {
    const { data } = await api.get('/auth/profile/history/', { params })
    return data
  },
  async subscription() {
    const { data } = await api.get('/auth/profile/subscription/')
    return data
  },
  async settings() {
    const { data } = await api.get('/auth/settings/')
    return data
  },
  async updateSettings(settings) {
    const { data } = await api.patch('/auth/settings/', settings)
    return data
  },
}

export const readingApi = {
  async list(titleSlug) {
    const { data } = await api.get('/reading/', { params: { title: titleSlug } })
    return Array.isArray(data) ? data : data.results || []
  },
  async save({ part, page, isRead }) {
    const payload = { part }
    if (page !== undefined) payload.page = page
    if (isRead !== undefined) payload.is_read = isRead
    const { data } = await api.post('/reading/', payload)
    return data
  },
}

export const aiApi = {
  // AI yordamchi (AniVoy): an online chat model with catalogue functions. It
  // decides which lookups it needs (search, title details, parts, genres,
  // popular titles, and the user's taste when `taste` is on) and answers.
  // Subscribers only — a free account gets a 403 with `code`
  // `subscription_required`, and an outage a 503 (`ai_unavailable`).
  // `history` is the last turns of the chat (`{role, text}`), so a follow-up
  // question like "nima aytgandingiz?" still means something to the model.
  // `support` switches the assistant to the technical-support persona
  // ("adminga xabar"): a problem is answered with fix-it steps and advice.
  async ask(query, { type = '', limit = 0, history = [], support = false, taste = false } = {}) {
    const payload = { query }
    if (type) payload.type = type
    if (limit) payload.limit = limit
    if (history.length) payload.history = history
    if (support) payload.support = true
    // `taste` ("Sevimlilar" mode): the server enables the assistant's
    // personal_taste function, so the answer is grounded in the user's own
    // favourites and last watched titles.
    if (taste) payload.taste = true
    const { data } = await api.post('/catalog/ai-assistant/', payload)
    return data
  },
}

export const supportApi = {
  // "Adminga xabar": the message is stored server-side and then forwarded to
  // every administrator, so `delivered` tells the panel the real outcome.
  async send(text) {
    const { data } = await api.post('/auth/support/', { text })
    return data
  },
}

export const subscriptionApi = {
  async plans() {
    return cachedGet('/auth/subscription/plans/')
  },
  async card() {
    const { data } = await api.get('/auth/subscription/card/')
    return data
  },
  async submit({ plan, screenshot }) {
    const form = new FormData()
    form.append('plan', plan)
    form.append('screenshot', screenshot)
    const { data } = await api.post('/auth/subscription/request/', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
  async status(requestId) {
    const { data } = await api.get(`/auth/subscription/requests/${requestId}/`)
    return data
  },
}

export const gameApi = {
  async status() {
    const { data } = await api.get('/game/status/')
    return data
  },
  async titles(query = '') {
    return cachedGet('/game/titles/', query ? { q: query } : {})
  },
  async startQuiz(titleId) {
    const { data } = await api.post('/game/quiz/start/', { title_id: titleId })
    return data
  },
  async submitQuiz({ attemptId, answers, elapsedMs }) {
    const { data } = await api.post('/game/quiz/submit/', {
      attempt_id: attemptId,
      answers,
      elapsed_ms: elapsedMs,
    })
    return data
  },
  async leaderboard(limit = 50) {
    const { data } = await api.get('/game/leaderboard/', { params: { limit } })
    return data
  },
}