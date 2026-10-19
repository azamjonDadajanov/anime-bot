import { api } from '../../apis/api'

export const adminDashboardApi = {
  async stats() {
    const { data } = await api.get('/admin/dashboard/')
    return data
  },
}

export const adminMediaApi = {
  async list(params = {}) {
    const { data } = await api.get('/catalog/', { params })
    return data
  },
  async detail(slug) {
    const { data } = await api.get(`/catalog/${encodeURIComponent(slug)}/`)
    return data
  },
  async create(payload) {
    const { data } = await api.post('/catalog/', payload)
    return data
  },
  async update(slug, payload) {
    const { data } = await api.patch(`/catalog/${encodeURIComponent(slug)}/`, payload)
    return data
  },
  async remove(slug) {
    await api.delete(`/catalog/${encodeURIComponent(slug)}/`)
  },
  async stats(params = {}) {
    const { data } = await api.get('/admin/media-stats/', { params })
    return data
  },
  async parts(contentId, params = {}) {
    const { data } = await api.get('/parts/', { params: { ...params, content: contentId } })
    return data
  },
  async createPart(payload) {
    const { data } = await api.post('/parts/', payload)
    return data
  },
  async updatePart(id, payload) {
    const { data } = await api.patch(`/parts/${id}/`, payload)
    return data
  },
  async deletePart(id) {
    await api.delete(`/parts/${id}/`)
  },
  async telegramMedia(partId) {
    const { data } = await api.get('/telegram-media/', { params: { part: partId } })
    return Array.isArray(data) ? data : data.results || []
  },
  async addTelegramMedia(payload) {
    const { data } = await api.post('/telegram-media/', payload)
    return data
  },
  async deleteTelegramMedia(id) {
    await api.delete(`/telegram-media/${id}/`)
  },
  async uploadPdf(partId, file, onProgress) {
    const form = new FormData()
    form.append('file', file)
    const { data } = await api.post(`/parts/${partId}/pdf/upload/`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (event) => {
        if (onProgress && event.total) {
          onProgress(Math.round((event.loaded * 100) / event.total))
        }
      },
    })
    return data
  },
  async deletePdf(partId) {
    await api.delete(`/parts/${partId}/pdf/`)
  },
  async pdfMeta(partId) {
    const { data } = await api.get(`/parts/${partId}/pdf/`, { params: { meta: 1 } })
    return data
  },
}

export const adminGenreApi = {
  async list(params = {}) {
    const { data } = await api.get('/admin/genres/', { params })
    return Array.isArray(data) ? data : data.results || []
  },
  async create(name) {
    const { data } = await api.post('/admin/genres/', { name })
    return data
  },
  async update(id, payload) {
    const { data } = await api.patch(`/admin/genres/${id}/`, payload)
    return data
  },
  async remove(id) {
    await api.delete(`/admin/genres/${id}/`)
  },
}

export const adminCouponApi = {
  async list(params = {}) {
    const { data } = await api.get('/admin/coupons/', { params })
    return data
  },
  async create(payload) {
    const { data } = await api.post('/admin/coupons/', payload)
    return data
  },
  async update(id, payload) {
    const { data } = await api.patch(`/admin/coupons/${id}/`, payload)
    return data
  },
  async remove(id) {
    await api.delete(`/admin/coupons/${id}/`)
  },
  async toggle(id) {
    const { data } = await api.post(`/admin/coupons/${id}/toggle/`)
    return data
  },
  async publish(id) {
    const { data } = await api.post(`/admin/coupons/${id}/publish/`)
    return data
  },
  async redemptions(id) {
    const { data } = await api.get(`/admin/coupons/${id}/redemptions/`)
    return Array.isArray(data) ? data : data.results || []
  },
}

export const adminUsersApi = {
  async list(params = {}) {
    const { data } = await api.get('/admin/users/', { params })
    return data
  },
  async detail(id) {
    const { data } = await api.get(`/admin/users/${id}/`)
    return data
  },
  async setPlan(id, plan) {
    const { data } = await api.post(`/admin/users/${id}/plan/`, { plan })
    return data
  },
  async setBlock(id, isBlocked) {
    const { data } = await api.post(`/admin/users/${id}/block/`, { is_blocked: isBlocked })
    return data
  },
}

export const adminSubscriptionApi = {
  async list(params = {}) {
    const { data } = await api.get('/admin/subscription-requests/', { params })
    return data
  },
  async approve(id, notes = '') {
    const { data } = await api.post(`/admin/subscription-requests/${id}/approve/`, { notes })
    return data
  },
  async reject(id, notes = '') {
    const { data } = await api.post(`/admin/subscription-requests/${id}/reject/`, { notes })
    return data
  },
}

export const adminIncomeApi = {
  async list(params = {}) {
    const { data } = await api.get('/admin/income/', { params })
    return data
  },
  async create(payload) {
    const { data } = await api.post('/admin/income/', payload)
    return data
  },
  async update(id, payload) {
    const { data } = await api.patch(`/admin/income/${id}/`, payload)
    return data
  },
  async remove(id) {
    await api.delete(`/admin/income/${id}/`)
  },
  async monthly(year) {
    const { data } = await api.get('/admin/income/monthly/', { params: { year } })
    return data
  },
}

export const adminBroadcastApi = {
  async list(params = {}) {
    const { data } = await api.get('/admin/broadcasts/', { params })
    return data
  },
  async detail(id) {
    const { data } = await api.get(`/admin/broadcasts/${id}/`)
    return data
  },
  async create(payload) {
    const { data } = await api.post('/admin/broadcasts/', payload)
    return data
  },
  async update(id, payload) {
    const { data } = await api.patch(`/admin/broadcasts/${id}/`, payload)
    return data
  },
  async remove(id) {
    await api.delete(`/admin/broadcasts/${id}/`)
  },
  async start(id) {
    const { data } = await api.post(`/admin/broadcasts/${id}/start/`)
    return data
  },
  async cancel(id) {
    const { data } = await api.post(`/admin/broadcasts/${id}/cancel/`)
    return data
  },
  async sendPodcast(payload) {
    const { data } = await api.post('/admin/podcast/send/', payload)
    return data
  },
}

export const adminChannelApi = {
  async list(params = {}) {
    const { data } = await api.get('/channels/', { params })
    return Array.isArray(data) ? data : data.results || []
  },
  async create(payload) {
    const { data } = await api.post('/channels/', payload)
    return data
  },
  async update(id, payload) {
    const { data } = await api.patch(`/channels/${id}/`, payload)
    return data
  },
  async remove(id) {
    await api.delete(`/channels/${id}/`)
  },
}

export const adminSettingsApi = {
  async get() {
    const { data } = await api.get('/admin/settings/')
    return data
  },
  async update(payload) {
    const { data } = await api.patch('/admin/settings/', payload)
    return data
  },
}

export const adminQuizApi = {
  async list(params = {}) {
    const { data } = await api.get('/admin/quiz-questions/', { params })
    return data
  },
  async create(payload) {
    const { data } = await api.post('/admin/quiz-questions/', payload)
    return data
  },
  async update(id, payload) {
    const { data } = await api.patch(`/admin/quiz-questions/${id}/`, payload)
    return data
  },
  async remove(id) {
    await api.delete(`/admin/quiz-questions/${id}/`)
  },
}

export const adminGameApi = {
  async leaderboard(params = {}) {
    const { data } = await api.get('/admin/game/leaderboard/', { params })
    return data
  },
  async attempts(params = {}) {
    const { data } = await api.get('/admin/quiz-attempts/', { params })
    return data
  },
  async updateAttempt(id, payload) {
    const { data } = await api.patch(`/admin/quiz-attempts/${id}/`, payload)
    return data
  },
  async removeAttempt(id) {
    await api.delete(`/admin/quiz-attempts/${id}/`)
  },
  async verifications(params = {}) {
    const { data } = await api.get('/admin/verifications/', { params })
    return data
  },
  async createVerification(payload) {
    const { data } = await api.post('/admin/verifications/', payload)
    return data
  },
  async removeVerification(id) {
    await api.delete(`/admin/verifications/${id}/`)
  },
  async prizes(params = {}) {
    const { data } = await api.get('/admin/monthly-prizes/', { params })
    return data
  },
  async createPrize(payload) {
    const { data } = await api.post('/admin/monthly-prizes/', payload)
    return data
  },
  async removePrize(id) {
    await api.delete(`/admin/monthly-prizes/${id}/`)
  },
  async awardPrize(payload) {
    const { data } = await api.post('/admin/monthly-prizes/award/', payload)
    return data
  },
}

export const adminLogApi = {
  async list(params = {}) {
    const { data } = await api.get('/admin/logs/', { params })
    return data
  },
}

// The panel renders the same /media/covers/ file the site does; it just used
// to decode a base64 blob instead of pointing at the URL.
export { coverSrc as coverDataUrl } from '../../apis/mediaUrl'

export function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result
      const base64 = String(result).split(',')[1] || ''
      resolve(base64)
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}
