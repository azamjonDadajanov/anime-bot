import { useState } from 'react'
import { Alert, Button, PasswordInput, TextInput } from '@mantine/core'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../apis/useAuth'

function getErrorMessage(error) {
  const data = error.response?.data
  if (!data) return "Server bilan bog'lanib bo'lmadi. Django server ishlayotganini tekshiring."
  if (typeof data.detail === 'string') return data.detail
  return Object.values(data).flat().map(String).join(' ')
}

function AuthPage({ mode }) {
  const isRegister = mode === 'register'
  const { user, login, register } = useAuth()
  const navigate = useNavigate()
  const [values, setValues] = useState({ username: '', email: '', password: '', passwordConfirm: '' })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  if (user) return <Navigate to="/" replace />

  function update(field) {
    return (event) => {
      const { value } = event.currentTarget
      setValues((current) => ({ ...current, [field]: value }))
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      if (isRegister) {
        await register({
          username: values.username,
          email: values.email,
          password: values.password,
          password_confirm: values.passwordConfirm,
        })
      } else {
        await login({ username: values.username, password: values.password })
      }
      navigate('/', { replace: true })
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-stage">
      <section className="auth-cinema" aria-label="AniChopar">
        <div className="auth-art" aria-hidden="true">
          <span className="auth-art-ring" />
          <span className="auth-art-orb" />
          <span className="auth-art-kanji">アニメ</span>
          <span className="auth-art-word">ANICHOPAR</span>
        </div>

        <div className="auth-cinema-copy">
          <span className="hero-kicker">
            <span className="dot" aria-hidden="true" />
            AniChopar / Shaxsiy kabinet
          </span>
          <h1 className="auth-title">
            Yaxshi hikoyalar <em>shu yerdan</em> boshlanadi.
          </h1>
          <p className="auth-caption">
            Anime, kino, serial va manga — o&apos;zbek tilida, bir orbital
            katalogda. Sevimlilar, tarix va obuna yoningizda.
          </p>
        </div>

        <div className="auth-cinema-foot" aria-hidden="true">
          <span>01</span>
          <span>Kino · Anime · Serial · Manga</span>
          <span>AC / 2026</span>
        </div>
      </section>

      <section className="auth-panel">
        <div className="auth-card">
          <span className="eyebrow">{isRegister ? "Ro'yxatdan o'tish" : 'Kirish'}</span>
          <h2 className="auth-card-title">
            {isRegister ? 'Yangi hisob yarating' : 'Xush kelibsiz'}
          </h2>
          <p className="auth-card-sub">
            {isRegister
              ? "Bir daqiqada profil yarating va katalogning barcha imkoniyatlarini oching."
              : 'Davom etish uchun hisobingizga kiring.'}
          </p>

          {error && <Alert color="red" mb="sm" title="Kirish amalga oshmadi">{error}</Alert>}

          <form className="auth-form" onSubmit={handleSubmit}>
            <TextInput
              label="Foydalanuvchi nomi"
              placeholder="masalan, ali_akbar"
              autoComplete="username"
              value={values.username}
              onChange={update('username')}
              required
            />
            {isRegister && (
              <TextInput
                label="Email"
                placeholder="siz@example.com"
                type="email"
                autoComplete="email"
                value={values.email}
                onChange={update('email')}
                required
              />
            )}
            <PasswordInput
              label="Parol"
              placeholder={isRegister ? 'Kamida 8 ta belgi' : 'Parolingiz'}
              autoComplete={isRegister ? 'new-password' : 'current-password'}
              value={values.password}
              onChange={update('password')}
              required
              minLength={isRegister ? 8 : undefined}
            />
            {isRegister && (
              <PasswordInput
                label="Parolni tasdiqlang"
                placeholder="Parolni qayta kiriting"
                autoComplete="new-password"
                value={values.passwordConfirm}
                onChange={update('passwordConfirm')}
                required
              />
            )}
            <Button
              className="auth-submit"
              type="submit"
              size="md"
              fullWidth
              loading={submitting}
              mt="xs"
            >
              {isRegister ? 'Hisob yaratish' : 'Kirish'}
            </Button>
          </form>

          <Link className="auth-telegram" to="/telegram-auth">
            <i className="bi bi-telegram" aria-hidden="true" />
            Telegram orqali kirish
          </Link>

          <div className="auth-divider">yoki</div>

          <p className="auth-switch">
            {isRegister ? 'Hisobingiz bormi?' : "Hali profilingiz yo'qmi?"}{' '}
            <Link to={isRegister ? '/login' : '/register'}>
              {isRegister ? 'Kirish' : "Ro'yxatdan o'tish"}
            </Link>
          </p>

          <p className="auth-legal">
            Davom etish orqali siz <span>foydalanish shartlari</span> va
            maxfiylik siyosatiga rozilik bildirasiz.
          </p>
        </div>
      </section>
    </main>
  )
}

export default AuthPage
