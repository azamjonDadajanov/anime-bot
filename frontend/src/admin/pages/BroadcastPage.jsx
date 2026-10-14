import {
  ActionIcon,
  Badge,
  Group,
  Loader,
  Select,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core'
import { useCallback, useEffect, useState } from 'react'
import { adminBroadcastApi } from '../api/adminApi'
import {
  BROADCAST_KIND_LABELS,
  BROADCAST_STATUS_LABELS,
  ConfirmDialog,
  EmptyState,
  ErrorAlert,
  PaginationBar,
  SectionHeading,
  SuccessAlert,
} from '../components/adminShared'
import { checkboxHandler, copyText, formatError, inputHandler, selectHandler } from '../utils/formUtils'

const KIND_OPTIONS = Object.entries(BROADCAST_KIND_LABELS).map(([value, label]) => ({ value, label }))

const EMPTY_FORM = {
  kind: 'text',
  text: '',
  caption: '',
  file_id: '',
  protect_content: true,
  disable_notification: false,
  include_blocked: false,
}

export default function BroadcastPage() {
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ results: [], count: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [startTarget, setStartTarget] = useState(null)
  const [cancelTarget, setCancelTarget] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await adminBroadcastApi.list({ page, page_size: 10 })
      setData(result)
    } catch (err) {
      setError(formatError(err, 'Broadcastlarni yuklashda xatolik.'))
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => {
    load()
  }, [load])

  async function handleCreate(event) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      await adminBroadcastApi.create({
        kind: form.kind,
        text: form.text || '',
        caption: form.caption || '',
        file_id: form.file_id || '',
        protect_content: form.protect_content,
        disable_notification: form.disable_notification,
        include_blocked: form.include_blocked,
      })
      setSuccess("Broadcast yaratildi. Ro'yxatdan ishga tushiring.")
      setForm({ ...EMPTY_FORM, kind: form.kind })
      await load()
    } catch (err) {
      setError(formatError(err, "Yaratishda xatolik."))
    } finally {
      setSaving(false)
    }
  }

  async function handleStart() {
    if (!startTarget) return
    setBusy(true)
    setError(null)
    try {
      await adminBroadcastApi.start(startTarget.id)
      setSuccess('Broadcast ishga tushirildi.')
      setStartTarget(null)
      await load()
    } catch (err) {
      setError(formatError(err, 'Ishga tushirishda xatolik.'))
      setStartTarget(null)
    } finally {
      setBusy(false)
    }
  }

  async function handleCancel() {
    if (!cancelTarget) return
    setBusy(true)
    setError(null)
    try {
      await adminBroadcastApi.cancel(cancelTarget.id)
      setSuccess("Broadcast so'rov bo'yicha to'xtatiladi.")
      setCancelTarget(null)
      await load()
    } catch (err) {
      setError(formatError(err, "Bekor qilishda xatolik."))
      setCancelTarget(null)
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    setBusy(true)
    setError(null)
    try {
      await adminBroadcastApi.remove(deleteTarget.id)
      setSuccess("Broadcast o'chirildi.")
      setDeleteTarget(null)
      await load()
    } catch (err) {
      setError(formatError(err, "O'chirishda xatolik."))
      setDeleteTarget(null)
    } finally {
      setBusy(false)
    }
  }

  async function copyFileId(fileId) {
    const ok = await copyText(fileId)
    setSuccess(ok ? 'file_id nusxalandi.' : "Nusxalab bo'lmadi.")
  }

  const results = data.results || []
  const count = data.count || 0
  const totalPages = Math.max(1, Math.ceil(count / 10))
  const needFile = ['photo', 'video', 'document', 'audio'].includes(form.kind)

  return (
    <Stack gap="lg">
      <SectionHeading
        title="Broadcast"
        description="Barcha foydalanuvchilarga xabar yuborish."
      />
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>

      <form className="admin-panel" onSubmit={handleCreate}>
        <Title order={5} mb="sm">Yangi broadcast</Title>
        <Stack gap="md">
          <Group align="flex-start" grow>
            <Select
              label="Turi"
              data={KIND_OPTIONS}
              value={form.kind}
              onChange={selectHandler(setForm, 'kind')}
              allowDeselect={false}
            />
            {needFile ? (
              <TextInput
                label="Telegram file_id"
                placeholder="BAACAgUAAxk..."
                value={form.file_id}
                onChange={inputHandler(setForm, 'file_id')}
                required
              />
            ) : null}
          </Group>
          {form.kind === 'text' ? (
            <Textarea
              label="Matn"
              minRows={4}
              value={form.text}
              onChange={inputHandler(setForm, 'text')}
              required
            />
          ) : (
            <Textarea
              label="Izoh (caption)"
              minRows={3}
              value={form.caption}
              onChange={inputHandler(setForm, 'caption')}
            />
          )}
          <Group>
            <label className="admin-checkbox">
              <input
                type="checkbox"
                checked={form.protect_content}
                onChange={checkboxHandler(setForm, 'protect_content')}
              />
              Himoyalangan
            </label>
            <label className="admin-checkbox">
              <input
                type="checkbox"
                checked={form.disable_notification}
                onChange={checkboxHandler(setForm, 'disable_notification')}
              />
              Ovozsiz
            </label>
            <label className="admin-checkbox">
              <input
                type="checkbox"
                checked={form.include_blocked}
                onChange={checkboxHandler(setForm, 'include_blocked')}
              />
              Bloklanganlarni ham
            </label>
          </Group>
          <Group justify="flex-end">
            <button type="submit" className="admin-btn admin-btn-primary" disabled={saving}>
              {saving ? 'Yaratilmoqda…' : 'Yaratish'}
            </button>
          </Group>
        </Stack>
      </form>

      {loading ? (
        <div className="admin-loading"><Loader /></div>
      ) : results.length === 0 ? (
        <EmptyState icon="bi-broadcast" title="Broadcast yo'q" />
      ) : (
        <Stack gap="md">
          {results.map((item) => (
            <div key={item.id} className="admin-panel">
              <Group justify="space-between" align="flex-start" wrap="wrap">
                <Stack gap={4} style={{ minWidth: 0, flex: 1 }}>
                  <Group gap="xs">
                    <Title order={5}>#{item.id}</Title>
                    <Badge variant="light">{BROADCAST_KIND_LABELS[item.kind] || item.kind}</Badge>
                    <Badge
                      variant="light"
                      color={
                        item.status === 'running'
                          ? 'blue'
                          : item.status === 'completed'
                            ? 'green'
                            : item.status === 'failed'
                              ? 'red'
                              : 'gray'
                      }
                    >
                      {BROADCAST_STATUS_LABELS[item.status] || item.status}
                    </Badge>
                  </Group>
                  <Text size="sm" c="dimmed" lineClamp={2}>
                    {item.text || item.caption || '—'}
                  </Text>
                  {item.file_id ? (
                    <Group gap={6}>
                      <Text size="xs" c="dimmed" style={{ fontFamily: 'monospace' }}>
                        {item.file_id.slice(0, 36)}…
                      </Text>
                      <ActionIcon
                        variant="subtle"
                        size="sm"
                        onClick={() => copyFileId(item.file_id)}
                        title="file_id nusxalash"
                      >
                        <i className="bi bi-clipboard" />
                      </ActionIcon>
                    </Group>
                  ) : null}
                  <Text size="xs" c="dimmed">
                    Yuborilgan: {item.sent_count} · Xato: {item.failed_count} · Blok: {item.blocked_count}
                    {item.last_error ? ` · ${item.last_error}` : ''}
                  </Text>
                </Stack>
                <Group gap="xs">
                  {item.status !== 'running' && item.status !== 'completed' ? (
                    <button
                      type="button"
                      className="admin-btn admin-btn-primary"
                      onClick={() => setStartTarget(item)}
                    >
                      Ishga tushirish
                    </button>
                  ) : null}
                  {item.status === 'running' ? (
                    <button
                      type="button"
                      className="admin-btn admin-btn-danger"
                      onClick={() => setCancelTarget(item)}
                    >
                      To'xtatish
                    </button>
                  ) : null}
                  {item.status !== 'running' ? (
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      onClick={() => setDeleteTarget(item)}
                      title="O'chirish"
                    >
                      <i className="bi bi-trash" />
                    </ActionIcon>
                  ) : null}
                </Group>
              </Group>
            </div>
          ))}
        </Stack>
      )}

      <PaginationBar
        page={page}
        totalPages={totalPages}
        count={count}
        onChange={setPage}
        loading={loading}
      />

      <ConfirmDialog
        open={Boolean(startTarget)}
        title="Broadcastni ishga tushirish"
        message={`#${startTarget?.id} broadcast barcha foydalanuvchilarga yuboriladi.`}
        confirmLabel="Ha, yuborish"
        loading={busy}
        onCancel={() => setStartTarget(null)}
        onConfirm={handleStart}
      />

      <ConfirmDialog
        open={Boolean(cancelTarget)}
        title="Broadcastni to'xtatish"
        message={`#${cancelTarget?.id} broadcast to'xtatiladi. Qayta ishga tushirish mumkin.`}
        confirmLabel="To'xtatish"
        danger
        loading={busy}
        onCancel={() => setCancelTarget(null)}
        onConfirm={handleCancel}
      />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Broadcastni o'chirish"
        message={`#${deleteTarget?.id} butunlay o'chiriladi.`}
        confirmLabel="O'chirish"
        danger
        loading={busy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      />
    </Stack>
  )
}
