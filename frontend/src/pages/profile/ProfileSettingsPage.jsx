import { useEffect, useState } from 'react'
import { Alert, Badge, Button, Group, Loader, SegmentedControl, Switch, Text, Title, useMantineColorScheme } from '@mantine/core'
import { useNavigate } from 'react-router-dom'
import { profileApi } from '../../apis/api'
import { useAuth } from '../../apis/useAuth'
import { useApi } from './useApi'
import { errorText, formatDate, formatDateTime } from './profileUtils'

const THEME_OPTIONS = [
  { value: 'system', label: 'Tizim' },
  { value: 'light', label: 'Kunduzgi' },
  { value: 'dark', label: 'Tungi' },
]

const LANGUAGE_OPTIONS = [
  { value: 'uz', label: "O'zbekcha" },
  { value: 'ru', label: 'Русский' },
  { value: 'en', label: 'English' },
]

const DEFAULTS = { theme: 'system', language: 'uz', reduce_motion: false }

function toMantineTheme(theme) {
  return theme === 'system' ? 'auto' : theme
}

export function ProfileSettingsPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { setColorScheme } = useMantineColorScheme()
  const { data, loading, error } = useApi(() => profileApi.settings(), user?.id)

  const [settings, setSettings] = useState(null)
  const [saving, setSaving] = useState('')
  const [message, setMessage] = useState('')
  const [saveError, setSaveError] = useState('')

  useEffect(() => {
    if (data) setSettings(data)
  }, [data])

  function applyLocally(values) {
    setColorScheme(toMantineTheme(values.theme))
    document.documentElement.dataset.reduceMotion = values.reduce_motion ? 'true' : 'false'
  }

  async function apply(patch) {
    const previous = settings
    const optimistic = { ...settings, ...patch }
    setSettings(optimistic)
    applyLocally(optimistic)
    setSaving(Object.keys(patch)[0] || '')
    setMessage('')
    setSaveError('')
    try {
      const saved = await profileApi.updateSettings(patch)
      setSettings(saved)
      applyLocally(saved)
      setMessage('Sozlamalar saqlandi.')
    } catch (requestError) {
      setSettings(previous)
      applyLocally(previous)
      setSaveError(errorText(requestError))
    } finally {
      setSaving('')
    }
  }

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  if (loading && !settings) return <div className="page-loader"><Loader /></div>
  if (error) return <Alert color="red">{error}</Alert>
  if (!settings) return null

  const contrast = settings.theme === 'system' ? 'Tizim sozlamasiga mos' : (settings.theme === 'dark' ? 'Tungi' : 'Kunduzgi')

  return (
    <div className="profile-sections">
      {message && <Alert color="green">{message}</Alert>}
      {saveError && <Alert color="red">{saveError}</Alert>}

      <section className="profile-edit-panel">
        <Text className="section-kicker">KO'RINISH</Text>
        <Title order={2}>Mavzu va ko'rinish</Title>
        <Text c="dimmed" size="sm" mt={4}>
          Tanlangan mavzu hisobingizga saqlanadi va keyingi kirishlarda avtomatik qo'llanadi.
        </Text>
        <div className="settings-field">
          <Text fw={600} size="sm">Sayt mavzusi</Text>
          <SegmentedControl
            data={THEME_OPTIONS}
            value={settings.theme}
            onChange={(value) => apply({ theme: value })}
            disabled={Boolean(saving)}
          />
          <Text c="dimmed" size="xs">Hozir: {contrast}</Text>
        </div>
      </section>

      <section className="profile-edit-panel">
        <Text className="section-kicker">MOSLASHTIRISH</Text>
        <Title order={2}>Til va qulaylik</Title>
        <div className="settings-field">
          <Text fw={600} size="sm">Interfeys tili</Text>
          <SegmentedControl
            data={LANGUAGE_OPTIONS}
            value={settings.language}
            onChange={(value) => apply({ language: value })}
            disabled={Boolean(saving)}
          />
          <Text c="dimmed" size="xs">
            Sayt matnlari hozircha o'zbek tilida; tanlov hisobingizda saqlanadi.
          </Text>
        </div>
        <div className="settings-switch">
          <div>
            <Text fw={600} size="sm">Harakatlarni kamaytirish</Text>
            <Text c="dimmed" size="xs">
              Animatsiya va o'tishlarni o'chirib, sahifalarni tinchroq qiladi.
            </Text>
          </div>
          <Switch
            checked={settings.reduce_motion}
            onChange={(event) => apply({ reduce_motion: event.currentTarget.checked })}
            disabled={Boolean(saving)}
            aria-label="Harakatlarni kamaytirish"
          />
        </div>
        <Group mt="xl">
          <Button
            variant="light"
            onClick={() => apply(DEFAULTS)}
            loading={saving === 'theme'}
            disabled={Boolean(saving)}
          >
            Standart holatga qaytarish
          </Button>
          {saving && <Text c="dimmed" size="xs">Saqlanmoqda...</Text>}
        </Group>
      </section>

      <section className="profile-info-panel">
        <Text className="section-kicker">HISOB</Text>
        <Title order={2}>Kirish va xavfsizlik</Title>
        <div className="profile-row"><Text c="dimmed">Foydalanuvchi nomi</Text><Text fw={600}>{user.username}</Text></div>
        <div className="profile-row"><Text c="dimmed">Email</Text><Text fw={600}>{user.email || 'Kiritilmagan'}</Text></div>
        <div className="profile-row"><Text c="dimmed">Ro'yxatdan o'tgan</Text><Text fw={600}>{formatDate(user.date_joined)}</Text></div>
        <div className="profile-row"><Text c="dimmed">Oxirgi kirish</Text><Text fw={600}>{formatDateTime(user.last_login)}</Text></div>
        <div className="profile-row">
          <Text c="dimmed">Telegram</Text>
          <Text fw={600}>{user.telegram_id || 'Ulanmagan'}</Text>
        </div>
        <div className="profile-row">
          <Text c="dimmed">Sozlamalar yangilangan</Text>
          <Text fw={600}>{formatDateTime(settings.updated_at)}</Text>
        </div>
        <Group mt="xl">
          <Button
            color="red"
            variant="light"
            leftSection={<i className="bi bi-box-arrow-right" aria-hidden="true" />}
            onClick={handleLogout}
          >
            Hisobdan chiqish
          </Button>
          <Badge variant="light" color="blue">Til: {settings.language.toUpperCase()}</Badge>
        </Group>
      </section>
    </div>
  )
}

export default ProfileSettingsPage
