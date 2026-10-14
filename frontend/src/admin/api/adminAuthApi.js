import { api, authApi, hasAccessToken } from '../../apis/api'

export const adminAuthApi = {
  hasTokens() {
    return Promise.resolve(hasAccessToken())
  },
  async login(credentials) {
    return authApi.login(credentials)
  },
  async currentUser() {
    return authApi.currentUser()
  },
  logout() {
    authApi.logout()
  },
  async me() {
    const { data } = await api.get('/auth/me/')
    return data
  },
}
