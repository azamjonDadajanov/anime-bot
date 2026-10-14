import { useEffect, useRef, useState } from 'react'
import { useMantineColorScheme } from '@mantine/core'
import { authApi, hasAccessToken } from './api'
import { AuthContext } from './authContextValue'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(hasAccessToken)
  const { setColorScheme } = useMantineColorScheme()
  const settings = user?.settings

  // `setColorScheme` gets a new identity on every render, so it is read through a
  // ref that is refreshed after each render.
  const schemeRef = useRef(setColorScheme)
  useEffect(() => {
    schemeRef.current = setColorScheme
  })

  // Apply the saved profile settings (Sozlamalar tab) when the session changes.
  // Depending on `settings` alone — not on the scheme setter — is what keeps the
  // header toggle: with the setter in the dependencies this effect ran again on
  // the render the toggle caused and re-applied the (stale) stored theme.
  useEffect(() => {
    if (!settings) return
    schemeRef.current(settings.theme === 'system' ? 'auto' : settings.theme)
    document.documentElement.dataset.reduceMotion = settings.reduce_motion ? 'true' : 'false'
  }, [settings])

  useEffect(() => {
    let active = true
    const clearSession = () => {
      authApi.logout()
      setUser(null)
      setLoading(false)
    }

    window.addEventListener('anichopar:auth-expired', clearSession)
    if (hasAccessToken()) {
      authApi.currentUser()
        .then((profile) => active && setUser(profile))
        .catch(clearSession)
        .finally(() => active && setLoading(false))
    }

    return () => {
      active = false
      window.removeEventListener('anichopar:auth-expired', clearSession)
    }
  }, [])

  async function login(credentials) {
    await authApi.login(credentials)
    setUser(await authApi.currentUser())
  }

  async function register(details) {
    await authApi.register(details)
    setUser(await authApi.currentUser())
  }

  async function loginWithTelegram(credentials) {
    const data = await authApi.loginWithTelegram(credentials)
    setUser(data.user)
  }

  async function updateProfile(profile) {
    const updatedUser = await authApi.updateProfile(profile)
    setUser(updatedUser)
    return updatedUser
  }

  async function refreshUser() {
    const profile = await authApi.currentUser()
    setUser(profile)
    return profile
  }

  function logout() {
    authApi.logout()
    setUser(null)
  }

  return <AuthContext.Provider value={{ user, loading, login, register, loginWithTelegram, updateProfile, refreshUser, logout }}>{children}</AuthContext.Provider>
}