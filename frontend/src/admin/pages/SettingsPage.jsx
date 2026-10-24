import {
  Button,
  Group,
  Loader,
  NumberInput,
  Select,
  Stack,
  Switch,
  Text,
  Textarea,
  Title,
} from '@mantine/core'
import { useEffect, useState } from 'react'
import { adminChannelApi, adminSettingsApi } from '../api/adminApi'
import { ErrorAlert, SectionHeading, SuccessAlert } from '../components/adminShared'
import { formatError, inputHandler, numberHandler } from '../utils/formUtils'

// Channels an announcement may be posted to (see TelegramChannel.Purpose).
const ANNOUNCEMENT_PURPOSES = [
  'anime_ongoing',
  'anime_completed',
  'anime_vip',
  'movie',
  'movie_vip',
  'manga_ongoing',
  'manga_completed',
  'manga_vip',
  'public',
]

const EMPTY = {
  require_subscription: true,
  auto_publish_new_content: false,
  publish_channel: null,
  protect_content: true,
  maintenance_mode: false,
  welcome_text: '',
  access_denied_text: '',
  broadcast_rate_per_second: 25,
  broadcast_concurrency: 5,
  log_channel_id: '',
}

function toForm(data) {
  return {
    require_subscription: Boolean(data.require_subscription),
    auto_publish_new_content: Boolean(data.auto_publish_new_content),
    publish_channel: data.publish_channel ? Number(data.publish_channel) : null,
    protect_content: Boolean(data.protect_content),
    maintenance_mode: Boolean(data.maintenance_mode),
    welcome_text: data.welcome_text || '',
    access_denied_text: data.access_denied_text || '',
    broadcast_rate_per_second: data.broadcast_rate_per_second ?? 25,
    broadcast_concurrency: data.broadcast_concurrency ?? 5,
    log_channel_id: data.log_channel_id ?? '',
  }
}

export default function SettingsPage() {
  const [form, setForm] = useState(EMPTY)
  const [channels, setChannels] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  useEffect(() => {
    let active = true
    adminSettingsApi
      .get()
      .then((data) => {
        if (!active) return
        setForm(toForm(data))
      })
      .catch((err) => {
        if (active) setError(formatError(err, 'Sozlamalarni yuklashda xatolik.'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    // The fallback announcement channel is picked from the announcement
    // channels (catalogue sections) and the general "Ommaviy kanal" ones.
    adminChannelApi
      .list()
      .then((items) => {
        if (active) {
          setChannels(items.filter((item) => ANNOUNCEMENT_PURPOSES.includes(item.purpose)))
        }
      })
      .catch(() => {
        if (active) setChannels([])
      })
    return () => {
      active = false
    }
  }, [])

  const channelOptions = channels.map((channel) => ({
    value: String(channel.id),
    label: channel.title,
  }))

  async function handleSubmit(event) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const payload = {
        require_subscription: form.require_subscription,
        auto_publish_new_content: form.auto_publish_new_content,
        publish_channel: form.publish_channel ?? null,
        protect_content: form.protect_content,
        maintenance_mode: form.maintenance_mode,
        welcome_text: form.welcome_text,
        access_denied_text: form.access_denied_text,
        broadcast_rate_per_second: Number(form.broadcast_rate_per_second) || 25,
        broadcast_concurrency: Number(form.broadcast_concurrency) || 5,
        log_channel_id: form.log_channel_id === '' || form.log_channel_id === null
          ? null
          : Number(form.log_channel_id),
      }
      const updated = await adminSettingsApi.update(payload)
      setForm(toForm(updated))
      setSuccess('Sozlamalar saqlandi.')
    } catch (err) {
      setError(formatError(err, "Saqlashda xatolik."))
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="admin-loading"><Loader size="lg" /></div>

  return (
    <Stack gap="lg" maw={720}>
      <SectionHeading
        title="Bot sozlamalari"
        description="Obuna, himoya, broadcast va matn sozlamalari."
      />
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>

      <form className="admin-panel" onSubmit={handleSubmit}>
        <Stack gap="md">
          <Title order={5}>Asosiy</Title>
          <Switch
            label="Majburiy obuna talab qilinsin"
            checked={form.require_subscription}
            onChange={(event) => setForm((prev) => ({ ...prev, require_subscription: event.currentTarget.checked }))}
          />
          <Switch
            label="Yangi kontentni avtomatik e'lon qilish"
            checked={form.auto_publish_new_content}
            onChange={(event) => setForm((prev) => ({ ...prev, auto_publish_new_content: event.currentTarget.checked }))}
          />
          <Select
            label="Asosiy e'lon kanali (Standart)"
            description="Maxsus kanal belgilanmagan hollarda e'lonlar shu umumiy kanalga chiqadi."
            placeholder="Kanal tanlanmagan"
            data={channelOptions}
            value={form.publish_channel === null ? null : String(form.publish_channel)}
            onChange={(value) =>
              setForm((prev) => ({ ...prev, publish_channel: value ? Number(value) : null }))
            }
            clearable
            searchable
          />
          <Text size="xs" c="dimmed">
            Bo'limlar bo'yicha e'lon kanallari (Animelar / Kinolar / Mangalar · Ongoing,
            Tugagan, VIP) «Kanallar» sahifasida sozlanadi.
          </Text>
          <Switch
            label="Kontentni himoyalash (forward/cheklash)"
            checked={form.protect_content}
            onChange={(event) => setForm((prev) => ({ ...prev, protect_content: event.currentTarget.checked }))}
          />
          <Switch
            label="Texnik rejim (faqat adminlar)"
            color="red"
            checked={form.maintenance_mode}
            onChange={(event) => setForm((prev) => ({ ...prev, maintenance_mode: event.currentTarget.checked }))}
          />

          <Title order={5} mt="md">Broadcast</Title>
          <Group align="flex-start" grow>
            <NumberInput
              label="Sekundiga xabar"
              min={1}
              max={30}
              value={form.broadcast_rate_per_second}
              onChange={numberHandler(setForm, 'broadcast_rate_per_second')}
            />
            <NumberInput
              label="Parallel so'rovlar"
              min={1}
              max={10}
              value={form.broadcast_concurrency}
              onChange={numberHandler(setForm, 'broadcast_concurrency')}
            />
          </Group>

          <Title order={5} mt="md">Matnlar</Title>
          <Textarea
            label="/start yuqori matni"
            minRows={3}
            value={form.welcome_text}
            onChange={inputHandler(setForm, 'welcome_text')}
          />
          <Textarea
            label="Ruxsat rad etilganda qo'shimcha matn"
            minRows={3}
            value={form.access_denied_text}
            onChange={inputHandler(setForm, 'access_denied_text')}
          />

          <Group justify="flex-end">
            <Button type="submit" loading={saving}>
              Saqlash
            </Button>
          </Group>
        </Stack>
      </form>
    </Stack>
  )
}
