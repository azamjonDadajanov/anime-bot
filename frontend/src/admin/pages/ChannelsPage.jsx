import { ActionIcon, Badge, Group, Loader, Select, Stack, Switch, Text, TextInput, Title } from '@mantine/core'
import { useCallback, useEffect, useState } from 'react'
import { adminChannelApi } from '../api/adminApi'
import {
  CHANNEL_PURPOSE_LABELS,
  ConfirmDialog,
  EmptyState,
  ErrorAlert,
  SectionHeading,
  SuccessAlert,
} from '../components/adminShared'
import { formatError, inputHandler, selectHandler } from '../utils/formUtils'

const PURPOSE_OPTIONS = Object.entries(CHANNEL_PURPOSE_LABELS).map(([value, label]) => ({ value, label }))

const EMPTY_FORM = { chat_id: '', title: '', username: '', purpose: 'storage', is_active: true }

export default function ChannelsPage() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await adminChannelApi.list()
      setItems(data)
    } catch (err) {
      setError(formatError(err, 'Kanallarni yuklashda xatolik.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function handleSubmit(event) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const payload = {
        chat_id: Number(form.chat_id),
        title: form.title,
        username: (form.username || '').replace(/^@/, ''),
        purpose: form.purpose,
        is_active: form.is_active,
      }
      if (editing) {
        await adminChannelApi.update(editing.id, payload)
        setSuccess('Kanal yangilandi.')
        setEditing(null)
      } else {
        await adminChannelApi.create(payload)
        setSuccess("Kanal qo'shildi.")
      }
      setForm(EMPTY_FORM)
      await load()
    } catch (err) {
      setError(formatError(err, "Saqlashda xatolik."))
    } finally {
      setSaving(false)
    }
  }

  function startEdit(channel) {
    setEditing(channel)
    setForm({
      chat_id: String(channel.chat_id),
      title: channel.title || '',
      username: channel.username || '',
      purpose: channel.purpose || 'storage',
      is_active: channel.is_active,
    })
  }

  function cancelEdit() {
    setEditing(null)
    setForm(EMPTY_FORM)
  }

  async function toggleActive(channel) {
    setError(null)
    try {
      await adminChannelApi.update(channel.id, { is_active: !channel.is_active })
      await load()
    } catch (err) {
      setError(formatError(err, 'Yangilashda xatolik.'))
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    setBusy(true)
    try {
      await adminChannelApi.remove(deleteTarget.id)
      setDeleteTarget(null)
      setSuccess("Kanal o'chirildi.")
      await load()
    } catch (err) {
      setError(formatError(err, "O'chirishda xatolik."))
      setDeleteTarget(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Stack gap="lg">
      <SectionHeading
        title="Telegram kanallar"
        description="Majburiy obuna, cloud saqlash va ommaviy kanallar."
      />
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>

      <form className="admin-panel" onSubmit={handleSubmit}>
        <Title order={5} mb="sm">{editing ? 'Kanalni tahrirlash' : 'Yangi kanal'}</Title>
        <Group align="flex-end" grow>
          <TextInput
            label="Chat ID"
            placeholder="-1001234567890"
            value={form.chat_id}
            onChange={inputHandler(setForm, 'chat_id')}
            required
          />
          <TextInput
            label="Nomi"
            value={form.title}
            onChange={inputHandler(setForm, 'title')}
            required
          />
          <TextInput
            label="Username"
            placeholder="@kanal"
            value={form.username}
            onChange={inputHandler(setForm, 'username')}
          />
        </Group>
        <Group align="flex-end" mt="md">
          <Select
            label="Maqsad"
            data={PURPOSE_OPTIONS}
            value={form.purpose}
            onChange={selectHandler(setForm, 'purpose')}
            allowDeselect={false}
            w={220}
          />
          <Switch
            label="Faol"
            checked={form.is_active}
            onChange={(event) => setForm((prev) => ({ ...prev, is_active: event.currentTarget.checked }))}
          />
          {editing ? (
            <button type="button" className="admin-btn admin-btn-secondary" onClick={cancelEdit}>
              Bekor
            </button>
          ) : null}
          <button type="submit" className="admin-btn admin-btn-primary" disabled={saving}>
            {saving ? 'Saqlanmoqda…' : editing ? 'Saqlash' : "Qo'shish"}
          </button>
        </Group>
      </form>

      {loading ? (
        <div className="admin-loading"><Loader /></div>
      ) : items.length === 0 ? (
        <EmptyState icon="bi-megaphone" title="Kanal yo'q" />
      ) : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Kanal</th>
                <th>Chat ID</th>
                <th>Maqsad</th>
                <th>Faol</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((channel) => (
                <tr key={channel.id}>
                  <td>
                    <Text fw={600} size="sm">{channel.title}</Text>
                    <Text size="xs" c="dimmed">{channel.username || channel.invite_link || ''}</Text>
                  </td>
                  <td><code>{channel.chat_id}</code></td>
                  <td>
                    <Badge variant="light">
                      {CHANNEL_PURPOSE_LABELS[channel.purpose] || channel.purpose}
                    </Badge>
                  </td>
                  <td>
                    <Switch
                      checked={channel.is_active}
                      onChange={() => toggleActive(channel)}
                      size="sm"
                    />
                  </td>
                  <td>
                    <Group gap={4} wrap="nowrap">
                      <ActionIcon variant="subtle" color="blue" onClick={() => startEdit(channel)} title="Tahrirlash">
                        <i className="bi bi-pencil" />
                      </ActionIcon>
                      <ActionIcon variant="subtle" color="red" onClick={() => setDeleteTarget(channel)} title="O'chirish">
                        <i className="bi bi-trash" />
                      </ActionIcon>
                    </Group>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Kanalni o'chirish"
        message={`"${deleteTarget?.title}" o'chiriladi.`}
        confirmLabel="O'chirish"
        danger
        loading={busy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      />
    </Stack>
  )
}
