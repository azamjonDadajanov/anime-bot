import axios from 'axios'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'
const ACCESS_TOKEN_KEY = 'anichopar_access'
const REFRESH_TOKEN_KEY = 'anichopar_refresh'

export const api = axios.create({
  baseURL: apiBaseUrl,
  headers: { 'Content-Type': 'application/json' },
})

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

export const authApi = {
  async login(credentials) {
    const { data } = await api.post('/auth/token/', credentials)
    localStorage.setItem(ACCESS_TOKEN_KEY, data.access)
    localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh)
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
    const { data } = await api.get('/catalog/', { params })
    return data
  },
  async favorites(params = {}) {
    const { data } = await api.get('/auth/favorites/', { params })
    return data
  },
  async detail(slug) {
    const { data } = await api.get(`/catalog/${encodeURIComponent(slug)}/`)
    return data
  },
  async recordView(slug, part) {
    const { data } = await api.post(
      `/catalog/${encodeURIComponent(slug)}/view/`,
      part ? { part } : {},
    )
    return data
  },
  async latest(params = {}) {
    const { data } = await api.get('/catalog/latest/', { params })
    return data
  },
  async popular(params = {}) {
    const { data } = await api.get('/catalog/popular/', { params })
    return data
  },
  async upcoming(params = {}) {
    const { data } = await api.get('/catalog/upcoming/', { params })
    return data
  },
  async movies(params = {}) {
    const { data } = await api.get('/catalog/movies/', { params })
    return data
  },
  async anime(params = {}) {
    const { data } = await api.get('/catalog/anime/', { params })
    return data
  },
  async manga(params = {}) {
    const { data } = await api.get('/catalog/manga/', { params })
    return data
  },
  async series(params = {}) {
    const { data } = await api.get('/catalog/series/', { params })
    return data
  },
  async random(params = {}) {
    const { data } = await api.get('/catalog/random/', { params })
    return data
  },
  partPdfUrl(partId) {
    return `${apiBaseUrl}/parts/${partId}/pdf/`
  },
  async partPdfMeta(partId) {
    const { data } = await api.get(`/parts/${partId}/pdf/`, { params: { meta: 1 } })
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

export const subscriptionApi = {
  async plans() {
    const { data } = await api.get('/auth/subscription/plans/')
    return data
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
    const { data } = await api.get('/game/titles/', { params: query ? { q: query } : {} })
    return data
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