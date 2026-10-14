import { useState } from 'react'
import {
  Alert,
  Button,
  Container,
  Divider,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../apis/useAuth'

function getErrorMessage(error) {
  const data = error.response?.data
  if (!data) return 'Server bilan bog\'lanib bo\'lmadi. Django server ishlayotganini tekshiring.'
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
    <main className="auth-layout">
      <section className="cinema-panel" aria-label="AniChopar">
        <div className="cinema-copy">
          <Text className="eyebrow">SIZNING KINO OLAMINGIZ</Text>
          <Title order={1}>Yaxshi hikoyalar shu yerdan boshlanadi.</Title>
          <Text className="cinema-caption">AniChopar katalogingiz va shaxsiy profilingizga xush kelibsiz.</Text>
        </div>
        <div className="film-note"><span>01</span><span>NOW SHOWING</span><span>AC / 2026</span></div>
      </section>
      <section className="form-panel">
        <Container size={420} className="form-container">
          <Text className="mobile-eyebrow">ANICHOPAR · SHAXSIY KABINET</Text>
          <Title order={2}>{isRegister ? 'Hisob yarating' : 'Xush kelibsiz'}</Title>
          <Text c="dimmed" size="sm" mt={7} mb="xl">
            {isRegister ? 'Yangi profilingizni bir daqiqada sozlang.' : 'Davom etish uchun profilingizga kiring.'}
          </Text>
          {error && <Alert color="red" mb="md" title="Kirish amalga oshmadi">{error}</Alert>}
          <form onSubmit={handleSubmit}>
            <Stack gap="md">
              <TextInput label="Foydalanuvchi nomi" placeholder="masalan, ali_akbar" autoComplete="username"
                value={values.username} onChange={update('username')} required />
              {isRegister && <TextInput label="Email" placeholder="siz@example.com" type="email" autoComplete="email"
                value={values.email} onChange={update('email')} required />}
              <PasswordInput label="Parol" placeholder={isRegister ? 'Kamida 8 ta belgi' : 'Parolingiz'}
                autoComplete={isRegister ? 'new-password' : 'current-password'} value={values.password}
                onChange={update('password')} required minLength={isRegister ? 8 : undefined} />
              {isRegister && <PasswordInput label="Parolni tasdiqlang" placeholder="Parolni qayta kiriting"
                autoComplete="new-password" value={values.passwordConfirm} onChange={update('passwordConfirm')} required />}
              <Button type="submit" size="md" fullWidth loading={submitting} mt="xs">
                {isRegister ? 'Hisob yaratish' : 'Kirish'}
              </Button>
            </Stack>
          </form>
          <Button component={Link} to="/telegram-auth" variant="default" size="md" fullWidth mt="md">
            Telegram orqali kirish
          </Button>
          <Divider label="yoki" labelPosition="center" my="lg" />
          <Text ta="center" size="sm">
            {isRegister ? 'Hisobingiz bormi?' : 'Hali profilingiz yo\'qmi?'}{' '}
            <Link className="text-link" to={isRegister ? '/login' : '/register'}>
              {isRegister ? 'Kirish' : 'Ro\'yxatdan o\'tish'}
            </Link>
          </Text>
        </Container>
      </section>
    </main>
  )
}

export default AuthPage