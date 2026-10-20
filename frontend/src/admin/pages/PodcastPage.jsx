import { Group, Stack, Text, TextInput, Title } from '@mantine/core'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { adminBroadcastApi } from '../api/adminApi'
import { adminPath } from '../adminBase'
import {
  ErrorAlert,
  SectionHeading,
  SuccessAlert,
} from '../components/adminShared'
import { checkboxHandler, formatError, inputHandler } from '../utils/formUtils'

const EMPTY_FORM = {
  file_id: '',
  text: '',
  caption: '',
  send_now: true,
  protect_content: true,
}

export default function PodcastPage() {
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const result = await adminBroadcastApi.sendPodcast({
        file_id: form.file_id,
        text: form.text || '',
        caption: form.caption || '',
        send_now: form.send_now,
        protect_content: form.protect_content,
      })
      setSuccess(
        form.send_now
          ? `Podcast yuborishga tayyordi (broadcast #${result?.id}).`
          : `Podcast broadcast #${result?.id} sifatida yaratildi.`,
      )
      setForm((prev) => ({ ...prev, file_id: '', text: '', caption: '' }))
    } catch (err) {
      setError(formatError(err, 'Podcast yuborishda xatolik.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Stack gap="lg" maw={640}>
      <SectionHeading
        title="Podcast yuborish"
        description="Audio fayl (Telegram file_id) orqali barcha foydalanuvchilarga podcast yuborish."
        actions={
          <Link className="admin-btn admin-btn-secondary" to={adminPath('/media/new')}>
            Katalogga qo'shish
          </Link>
        }
      />
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>

      <form className="admin-panel" onSubmit={handleSubmit}>
        <Stack gap="md">
          <Title order={5}>Audio yuborish</Title>
          <Text size="sm" c="dimmed">
            Avval audio faylni bot orqali kanalga yuboring, so'ng uning file_id'ini bu yerga
            kiriting. file_id doimiy saqlanadi va bir necha marta ishlatilishi mumkin.
          </Text>
          <TextInput
            label="Telegram audio file_id"
            placeholder="BAACAgUAAxkBAAIB..."
            value={form.file_id}
            onChange={inputHandler(setForm, 'file_id')}
            required
          />
          <TextInput
            label="Qo'shimcha matn (ixtiyoriy)"
            placeholder="Podcast haqida qisqa izoh…"
            value={form.text}
            onChange={inputHandler(setForm, 'text')}
          />
          <TextInput
            label="Audio izohi (caption)"
            value={form.caption}
            onChange={inputHandler(setForm, 'caption')}
          />
          <Group>
            <label className="admin-checkbox">
              <input
                type="checkbox"
                checked={form.send_now}
                onChange={checkboxHandler(setForm, 'send_now')}
              />
              Darhol yuborish
            </label>
            <label className="admin-checkbox">
              <input
                type="checkbox"
                checked={form.protect_content}
                onChange={checkboxHandler(setForm, 'protect_content')}
              />
              Himoyalangan
            </label>
          </Group>
          <Group justify="flex-end">
            <button type="submit" className="admin-btn admin-btn-primary" disabled={saving}>
              {saving ? 'Yuborilmoqda…' : form.send_now ? 'Yuborish' : 'Saqlash'}
            </button>
          </Group>
        </Stack>
      </form>

      <div className="admin-panel">
        <Title order={5} mb="xs">Maslahat</Title>
        <Stack gap="xs">
          <Text size="sm">
            1. Podcastni katalogga qo'shmoqchi bo'lsangiz, "Katalogga qo'shish" orqali yangi
            media (turi: Podcast) yarating.
          </Text>
          <Text size="sm">
            2. Katta hajmli audio uchun file_id saqlang — Telegram 20MB dan katta fayllarni
            bot orqali yubormaydi.
          </Text>
          <Text size="sm">
            3. Yuborishdan oldin Boshqaruv panelidan foydalanuvchilar sonini tekshiring.
          </Text>
        </Stack>
      </div>
    </Stack>
  )
}
