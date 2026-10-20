import { useState } from 'react'
import { Button, PasswordInput, TextInput } from '@mantine/core'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAdminAuth } from '../auth/useAdminAuth'
import { adminPath } from '../adminBase'
import { ErrorAlert } from '../components/adminShared'

export default function AdminLoginPage() {
  const { login, user } = useAdminAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  if (user) {
    return <Navigate to={adminPath('/')} replace />
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await login({ username, password })
      const from = location.state?.from || adminPath('/')
      navigate(from, { replace: true })
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Kirishda xatolik.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="admin-login">
      <form className="admin-login-card" onSubmit={handleSubmit}>
        <div className="admin-brand admin-login-brand">
          <i className="bi bi-shield-lock" aria-hidden="true" />
          <span>AniChopar Admin</span>
        </div>
        <p className="admin-login-hint">Admin panelga kirish uchun hisobingizni taqdim eting.</p>
        <ErrorAlert>{error}</ErrorAlert>
        <TextInput
          label="Login"
          placeholder="username"
          value={username}
          onChange={(event) => setUsername(event.currentTarget.value)}
          required
          autoFocus
        />
        <PasswordInput
          label="Parol"
          placeholder="••••••••"
          value={password}
          onChange={(event) => setPassword(event.currentTarget.value)}
          required
          mt="md"
        />
        <Button type="submit" fullWidth mt="lg" loading={loading}>
          Kirish
        </Button>
      </form>
    </div>
  )
}
