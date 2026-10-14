import { useCallback, useEffect, useState } from 'react'
import { adminAuthApi } from '../api/adminAuthApi'
import { AdminAuthContext } from './adminAuthContext'

export function AdminAuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadUser = useCallback(async () => {
    try {
      const profile = await adminAuthApi.currentUser()
      if (!profile?.is_staff) {
        setUser(null)
        setError('Bu panel faqat adminlar uchun.')
        return null
      }
      setUser(profile)
      setError(null)
      return profile
    } catch {
      setUser(null)
      return null
    }
  }, [])

  useEffect(() => {
    let active = true
    adminAuthApi
      .hasTokens()
      .then(async (hasTokens) => {
        if (!hasTokens) {
          if (active) setLoading(false)
          return
        }
        await loadUser()
        if (active) setLoading(false)
      })
      .catch(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [loadUser])

  async function login(credentials) {
    setError(null)
    const data = await adminAuthApi.login(credentials)
    const profile = await adminAuthApi.currentUser()
    if (!profile?.is_staff) {
      adminAuthApi.logout()
      throw new Error('Bu hisob admin huquqiga ega emas.')
    }
    setUser(profile)
    return data
  }

  function logout() {
    adminAuthApi.logout()
    setUser(null)
  }

  return (
    <AdminAuthContext.Provider value={{ user, loading, error, login, logout, refreshUser: loadUser }}>
      {children}
    </AdminAuthContext.Provider>
  )
}
