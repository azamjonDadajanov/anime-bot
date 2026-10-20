import { useEffect, useState } from 'react'
import { Alert, Button, Container, PasswordInput, Stack, Text, TextInput, Title } from '@mantine/core'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../apis/useAuth'

function getErrorMessage(error) {
  const data = error.response?.data
  if (!data) return 'Server bilan bog\'lanib bo\'lmadi. Django server ishlayotganini tekshiring.'
  if (typeof data.detail === 'string') return data.detail
  return Object.values(data).flat().map(String).join(' ')
}

function TelegramAuthPage() {
  const { user, loginWithTelegram } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const initData = window.Telegram?.WebApp?.initData || ''

  useEffect(() => {
    window.Telegram?.WebApp?.ready()
    window.Telegram?.WebApp?.expand()
  }, [])

  if (user) return <Navigate to="/" replace />

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await loginWithTelegram({ init_data: initData, email: email.trim(), password })
      navigate('/', { replace: true })
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="telegram-auth-page">
      <Container size={460} className="telegram-auth-container">
        <Text className="eyebrow">ANICHOPAR / TELEGRAM MINI APP</Text>
        <Title order={1}>Telegram bilan davom eting</Title>
        <Text c="dimmed" size="sm" mt="sm" mb="xl">
          Email va parolingizni kiriting. Akkauntingiz bo'lmasa, yangi akkaunt avtomatik yaratiladi: username sifatida Telegram username'ingiz ishlatiladi, u bo'lmasa — email.
        </Text>
        {!initData && <Alert color="yellow" title="Telegram Mini App ichida oching" mb="md">
          Telegram tasdiqlash ma'lumoti topilmadi. Bu sahifani botingizdagi Mini App tugmasi orqali oching.
        </Alert>}
        {error && <Alert color="red" title="Kirish amalga oshmadi" mb="md">{error}</Alert>}
        <form onSubmit={handleSubmit}>
          <Stack gap="md">
            <TextInput label="Email" placeholder="siz@example.com" type="email" autoComplete="email"
              description="Mavjud akkauntni topish uchun. Akkaunt bo'lmasa shu email bilan yangi akkaunt ochiladi."
              value={email} onChange={(event) => setEmail(event.currentTarget.value)} />
            <PasswordInput label="Parol" placeholder="Akkaunt paroli yoki yangi parol"
              autoComplete="current-password" value={password}
              onChange={(event) => setPassword(event.currentTarget.value)} required />
            <Button type="submit" size="md" fullWidth loading={submitting} disabled={!initData}>
              Kirish yoki ro'yxatdan o'tish
            </Button>
          </Stack>
        </form>
        <Text ta="center" size="sm" mt="lg"><Link className="text-link" to="/login">Oddiy login sahifasiga qaytish</Link></Text>
      </Container>
    </main>
  )
}

export default TelegramAuthPage