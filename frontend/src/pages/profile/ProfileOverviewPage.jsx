import { useState } from 'react'
import { Alert, Badge, Button, Group, Loader, Stack, Text, TextInput, Title } from '@mantine/core'
import { Link, useNavigate } from 'react-router-dom'
import { profileApi } from '../../apis/api'
import { useAuth } from '../../apis/useAuth'
import { ActivityList, StatTile } from './profileWidgets'
import { useApi } from './useApi'
import { errorText, formatDate, formatDateTime, formatPrice } from './profileUtils'

export function ProfileOverviewPage() {
  const { user, updateProfile, logout } = useAuth()
  const navigate = useNavigate()
  const { data, loading, error } = useApi(() => profileApi.overview(), user?.id)

  const [username, setUsername] = useState(user.username)
  const [email, setEmail] = useState(user.email || '')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [formError, setFormError] = useState('')

  async function saveProfile(event) {
    event.preventDefault()
    setSaving(true)
    setMessage('')
    setFormError('')
    try {
      await updateProfile({ username: username.trim(), email: email.trim() })
      setMessage("Profil ma'lumotlari saqlandi.")
    } catch (requestError) {
      setFormError(errorText(requestError))
    } finally {
      setSaving(false)
    }
  }

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  if (loading) return <div className="page-loader"><Loader /></div>
  if (error) return <Alert color="red">{error}</Alert>

  const { account, telegram, stats, subscription, recent_activity: recentActivity } = data

  return (
    <div className="profile-sections">
      <section className="profile-stats" aria-label="Hisob statistikasi">
        <StatTile icon="bi-heart-fill" label="Sevimlilar" value={stats.favorites} href="/favorites" />
        <StatTile icon="bi-play-circle-fill" label="Ko'rilgan media" value={stats.views} href="/profile/history" />
        <StatTile icon="bi-book-half" label="O'qilgan qismlar" value={stats.reading} href="/profile/history" />
        <StatTile icon="bi-receipt" label="To'lov arizalari" value={stats.requests} href="/profile/subscription" />
      </section>

      <div className="profile-page-grid">
        <section className="profile-edit-panel">
          <Text className="section-kicker">PROFILNI TAHRIRLASH</Text>
          <Title order={2}>Shaxsiy ma'lumotlar</Title>
          {message && <Alert color="green" mt="lg">{message}</Alert>}
          {formError && <Alert color="red" mt="lg">{formError}</Alert>}
          <form onSubmit={saveProfile}>
            <Stack gap="md" mt="lg">
              <TextInput
                label="Foydalanuvchi nomi"
                value={username}
                onChange={(event) => setUsername(event.currentTarget.value)}
                required
              />
              <TextInput
                label="Email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.currentTarget.value)}
              />
              <Button type="submit" loading={saving}>O'zgarishlarni saqlash</Button>
            </Stack>
          </form>
        </section>

        <section className="profile-info-panel">
          <Text className="section-kicker">HISOB MA'LUMOTLARI</Text>
          <Title order={2}>AniChopar hisobi</Title>
          <div className="profile-row"><Text c="dimmed">Hisob ID</Text><Text fw={600}>#{account.id}</Text></div>
          <div className="profile-row"><Text c="dimmed">Foydalanuvchi nomi</Text><Text fw={600}>{account.username}</Text></div>
          <div className="profile-row"><Text c="dimmed">Email</Text><Text fw={600}>{account.email || 'Kiritilmagan'}</Text></div>
          <div className="profile-row"><Text c="dimmed">Rol</Text><Text fw={600}>{account.is_staff ? 'Administrator' : 'Foydalanuvchi'}</Text></div>
          <div className="profile-row"><Text c="dimmed">Ro'yxatdan o'tgan</Text><Text fw={600}>{formatDate(account.joined_at)}</Text></div>
          <div className="profile-row"><Text c="dimmed">Oxirgi kirish</Text><Text fw={600}>{formatDateTime(account.last_login)}</Text></div>
          <Button
            color="red"
            variant="light"
            leftSection={<i className="bi bi-box-arrow-right" aria-hidden="true" />}
            mt="xl"
            onClick={handleLogout}
          >
            Hisobdan chiqish
          </Button>
        </section>
      </div>

      <div className="profile-page-grid">
        <section className="profile-info-panel">
          <Group justify="space-between" align="center">
            <Text className="section-kicker">TELEGRAM</Text>
            <Badge color={telegram.linked ? 'green' : 'gray'} variant="light">
              {telegram.linked ? 'Ulangan' : 'Ulanmagan'}
            </Badge>
          </Group>
          <Title order={2}>Botga ulangan akkaunt</Title>
          {telegram.linked ? (
            <>
              <div className="profile-row"><Text c="dimmed">Telegram ID</Text><Text fw={600}>{telegram.telegram_id}</Text></div>
              <div className="profile-row"><Text c="dimmed">Foydalanuvchi nomi</Text><Text fw={600}>{telegram.username ? `@${telegram.username}` : '—'}</Text></div>
              <div className="profile-row"><Text c="dimmed">Ism</Text><Text fw={600}>{telegram.full_name || '—'}</Text></div>
              <div className="profile-row"><Text c="dimmed">Til kodi</Text><Text fw={600}>{telegram.language_code || '—'}</Text></div>
              <div className="profile-row"><Text c="dimmed">Oxirgi faollik</Text><Text fw={600}>{formatDateTime(telegram.last_seen_at)}</Text></div>
            </>
          ) : (
            <Text c="dimmed" mt="md">
              Bu hisob Telegram botga ulanmagan. Botda /start buyrug'ini yuborib akkauntni ulang.
            </Text>
          )}
          <Button
            component={Link}
            to="/profile/telegram"
            variant="light"
            mt="xl"
            leftSection={<i className="bi bi-telegram" aria-hidden="true" />}
          >
            Batafsil ko'rish
          </Button>
        </section>

        <section className="profile-info-panel">
          <Group justify="space-between" align="center">
            <Text className="section-kicker">OBUNA HOLATI</Text>
            <Badge color={subscription.is_active ? 'blue' : 'gray'} variant="light">
              {subscription.is_active ? 'Faol' : subscription.is_paid ? "Muddati o'tgan" : 'Bepul'}
            </Badge>
          </Group>
          <Title order={2}>{subscription.plan_label} tarifi</Title>
          <div className="profile-row"><Text c="dimmed">Tarif narxi</Text><Text fw={600}>{formatPrice(subscription.last_amount)}</Text></div>
          <div className="profile-row">
            <Text c="dimmed">Tugash sanasi</Text>
            <Text fw={600}>{subscription.expires_at ? formatDate(subscription.expires_at) : 'Muddat belgilanmagan'}</Text>
          </div>
          <div className="profile-row">
            <Text c="dimmed">Qolgan kun</Text>
            <Text fw={600}>{subscription.days_left ?? '—'}</Text>
          </div>
          <Button
            component={Link}
            to="/profile/subscription"
            variant="light"
            mt="xl"
            leftSection={<i className="bi bi-ticket-perforated" aria-hidden="true" />}
          >
            To'lovlar tarixi
          </Button>
        </section>
      </div>

      <section className="profile-edit-panel">
        <Group justify="space-between" align="center" mb="md">
          <div>
            <Text className="section-kicker">OXIRGI FAOLLIKLAR</Text>
            <Title order={2} mt={8}>Nima bo'ldi?</Title>
          </div>
          <Button component={Link} to="/profile/activity" variant="subtle" size="compact-sm">
            Barchasi <i className="bi bi-arrow-right" aria-hidden="true" />
          </Button>
        </Group>
        <ActivityList
          items={recentActivity}
          emptyTitle="Hozircha faollik yo'q"
          emptyDescription="Botda media ochganingizda yoki sevimlilarga qo'shganingizda shu yerda ko'rinadi."
        />
      </section>
    </div>
  )
}

export default ProfileOverviewPage
