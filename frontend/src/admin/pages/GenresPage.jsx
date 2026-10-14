import { ActionIcon, Group, Loader, Stack, Text, TextInput } from '@mantine/core'
import { useCallback, useEffect, useState } from 'react'
import { adminGenreApi } from '../api/adminApi'
import {
  ConfirmDialog,
  EmptyState,
  ErrorAlert,
  SectionHeading,
  SuccessAlert,
} from '../components/adminShared'
import { formatError } from '../utils/formUtils'

export default function GenresPage() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState(null)
  const [editName, setEditName] = useState('')
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await adminGenreApi.list({ page_size: 200 })
      setItems(data)
    } catch (err) {
      setError(formatError(err, 'Janrlarni yuklashda xatolik.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function handleCreate(event) {
    event.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    setError(null)
    try {
      await adminGenreApi.create(name.trim())
      setName('')
      setSuccess("Janr qo'shildi.")
      await load()
    } catch (err) {
      setError(formatError(err, "Qo'shishda xatolik."))
    } finally {
      setSaving(false)
    }
  }

  async function handleUpdate(event) {
    event.preventDefault()
    if (!editing || !editName.trim()) return
    setBusy(true)
    setError(null)
    try {
      await adminGenreApi.update(editing.id, { name: editName.trim() })
      setEditing(null)
      setSuccess('Janr yangilandi.')
      await load()
    } catch (err) {
      setError(formatError(err, "Yangilashda xatolik."))
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    setBusy(true)
    try {
      await adminGenreApi.remove(deleteTarget.id)
      setDeleteTarget(null)
      setSuccess("Janr o'chirildi.")
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
      <SectionHeading title="Janrlar" description="Katalog janrlarini boshqarish." />
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>

      <form className="admin-panel" onSubmit={handleCreate}>
        <Group align="flex-end" wrap="wrap">
          <TextInput
            label="Yangi janr"
            placeholder="Fantastika"
            value={name}
            onChange={(event) => setName(event.currentTarget.value)}
            w={{ base: '100%', sm: 280 }}
          />
          <button type="submit" className="admin-btn admin-btn-primary" disabled={saving || !name.trim()}>
            {saving ? "Qo'shilmoqda…" : "Qo'shish"}
          </button>
        </Group>
      </form>

      {editing ? (
        <form className="admin-panel" onSubmit={handleUpdate}>
          <Group align="flex-end" wrap="wrap">
            <TextInput
              label={`Tahrirlash: ${editing.name}`}
              value={editName}
              onChange={(event) => setEditName(event.currentTarget.value)}
              w={{ base: '100%', sm: 280 }}
              autoFocus
            />
            <button type="submit" className="admin-btn admin-btn-primary" disabled={busy || !editName.trim()}>
              Saqlash
            </button>
            <button type="button" className="admin-btn admin-btn-secondary" onClick={() => setEditing(null)}>
              Bekor
            </button>
          </Group>
        </form>
      ) : null}

      {loading ? (
        <div className="admin-loading"><Loader /></div>
      ) : items.length === 0 ? (
        <EmptyState icon="bi-tags" title="Janr yo'q" />
      ) : (
        <div className="admin-genre-grid">
          {items.map((genre) => (
            <div key={genre.id} className="admin-genre-chip">
              <Text size="sm" fw={500}>{genre.name}</Text>
              <Text size="xs" c="dimmed">{genre.media_count}</Text>
              <ActionIcon
                variant="subtle"
                color="blue"
                size="sm"
                onClick={() => {
                  setEditing(genre)
                  setEditName(genre.name)
                }}
                title="Tahrirlash"
              >
                <i className="bi bi-pencil" />
              </ActionIcon>
              <ActionIcon
                variant="subtle"
                color="red"
                size="sm"
                onClick={() => setDeleteTarget(genre)}
                title="O'chirish"
              >
                <i className="bi bi-x" />
              </ActionIcon>
            </div>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Janrni o'chirish"
        message={`"${deleteTarget?.name}" janri o'chiriladi.`}
        confirmLabel="O'chirish"
        danger
        loading={busy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      />
    </Stack>
  )
}
