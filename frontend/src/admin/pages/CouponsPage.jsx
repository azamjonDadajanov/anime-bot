import {
  ActionIcon,
  Badge,
  Group,
  Loader,
  NumberInput,
  Select,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { useCallback, useEffect, useState } from 'react'
import { adminChannelApi, adminCouponApi } from '../api/adminApi'
import { formatDate, formatDateTime } from '../../utils/dates'
import {
  COUPON_STATUS_COLORS,
  COUPON_STATUS_LABELS,
  CHANNEL_PURPOSE_LABELS,
  ConfirmDialog,
  EmptyState,
  ErrorAlert,
  PaginationBar,
  SectionHeading,
  SuccessAlert,
} from '../components/adminShared'
import { copyText, formatError, inputHandler, numberHandler, selectHandler } from '../utils/formUtils'

const STATUS_OPTIONS = [
  { value: '', label: 'Barchasi' },
  ...Object.entries(COUPON_STATUS_LABELS).map(([value, label]) => ({ value, label })),
]

const EMPTY_FORM = { code: '', days: 7, max_uses: 10, posted_channel: '', is_active: true }
const PAGE_SIZE = 20

export default function CouponsPage() {
  const [data, setData] = useState({ results: [], count: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [channels, setChannels] = useState([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [editing, setEditing] = useState(null)
  const [saving, setSaving] = useState(false)
  const [busyId, setBusyId] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [busy, setBusy] = useState(false)
  const [redemptions, setRedemptions] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = { page, page_size: PAGE_SIZE }
      if (query) params.search = query
      if (status) params.status = status
      setData(await adminCouponApi.list(params))
    } catch (err) {
      setError(formatError(err, 'Kuponlarni yuklashda xatolik.'))
    } finally {
      setLoading(false)
    }
  }, [page, query, status])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    adminChannelApi
      .list({ page_size: 200 })
      .then((rows) => setChannels(rows))
      .catch(() => setChannels([]))
  }, [])

  const channelOptions = channels.map((channel) => ({
    value: String(channel.id),
    label: `${channel.title} Â· ${CHANNEL_PURPOSE_LABELS[channel.purpose] || channel.purpose}`,
  }))

  function cancelEdit() {
    setEditing(null)
    setForm(EMPTY_FORM)
  }

  function startEdit(coupon) {
    setEditing(coupon)
    setForm({
      code: coupon.code,
      days: coupon.days,
      max_uses: coupon.max_uses,
      posted_channel: coupon.posted_channel ? String(coupon.posted_channel) : '',
      is_active: coupon.is_active,
    })
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const payload = {
        code: (form.code || '').trim(),
        days: Number(form.days) || 0,
        max_uses: Number(form.max_uses) || 0,
        posted_channel: form.posted_channel ? Number(form.posted_channel) : null,
        is_active: form.is_active,
      }
      if (editing) {
        const updated = await adminCouponApi.update(editing.id, payload)
        setSuccess(`"${updated.code}" kupon yangilandi.`)
        cancelEdit()
      } else {
        const created = await adminCouponApi.create(payload)
        setSuccess(`"${created.code}" kupon yaratildi.`)
        setForm(EMPTY_FORM)
      }
      await load()
    } catch (err) {
      setError(formatError(err, "Saqlashda xatolik."))
    } finally {
      setSaving(false)
    }
  }

  async function handleToggle(coupon) {
    setBusyId(coupon.id)
    setError(null)
    try {
      const updated = await adminCouponApi.toggle(coupon.id)
      setSuccess(`"${updated.code}" endi ${updated.status_label.toLowerCase()}.`)
      await load()
    } catch (err) {
      setError(formatError(err, "Holatni o'zgartirishda xatolik."))
    } finally {
      setBusyId(null)
    }
  }

  async function handlePublish(coupon) {
    setBusyId(coupon.id)
    setError(null)
    setSuccess(null)
    try {
      const result = await adminCouponApi.publish(coupon.id)
      setSuccess(result.detail)
      await load()
    } catch (err) {
      setError(formatError(err, "Kanalga joylashda xatolik."))
    } finally {
      setBusyId(null)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    setBusy(true)
    try {
      await adminCouponApi.remove(deleteTarget.id)
      setSuccess(`"${deleteTarget.code}" kupon o'chirildi.`)
      setDeleteTarget(null)
      await load()
    } catch (err) {
      setError(formatError(err, "O'chirishda xatolik."))
      setDeleteTarget(null)
    } finally {
      setBusy(false)
    }
  }

  async function showRedemptions(coupon) {
    setRedemptions({ coupon, rows: [], loading: true })
    try {
      const rows = await adminCouponApi.redemptions(coupon.id)
      setRedemptions({ coupon, rows, loading: false })
    } catch (err) {
      setError(formatError(err, "Ishlatganlarni yuklashda xatolik."))
      setRedemptions(null)
    }
  }

  async function copyCode(code) {
    const ok = await copyText(code)
    setSuccess(ok ? `"${code}" nusxalandi.` : null)
  }

  const results = data.results || []
  const count = data.count || 0
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE))

  return (
    <Stack gap="lg">
      <SectionHeading
        title="Kuponlar"
        description="Promo kodlar: kimga, necha kun va necha kishiga â€” hamda kanalga joylash."
      />
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>

      <div className="admin-panel">
        <Title order={5} mb="sm">{editing ? `Tahrirlash: ${editing.code}` : 'Yangi kupon'}</Title>
        <form onSubmit={handleSubmit}>
          <Group align="flex-end" grow>
            <TextInput
              label="Kod"
              placeholder="Bo'sh qoldirsangiz avtomatik yaratiladi"
              value={form.code}
              onChange={inputHandler(setForm, 'code')}
              maxLength={24}
            />
            <NumberInput
              label="Necha kun"
              min={1}
              max={3650}
              value={form.days}
              onChange={numberHandler(setForm, 'days')}
              required
            />
            <NumberInput
              label="Necha kishiga"
              min={1}
              value={form.max_uses}
              onChange={numberHandler(setForm, 'max_uses')}
              required
            />
          </Group>
          <Group align="flex-end" mt="md">
            <Select
              label="E'lon kanali"
              placeholder="Sozlamalardagi kanal"
              data={channelOptions}
              value={form.posted_channel}
              onChange={selectHandler(setForm, 'posted_channel')}
              clearable
              searchable
              w={{ base: '100%', sm: 320 }}
            />
            {editing ? (
              <button type="button" className="admin-btn admin-btn-secondary" onClick={cancelEdit}>
                Bekor
              </button>
            ) : null}
            <button type="submit" className="admin-btn admin-btn-primary" disabled={saving}>
              {saving ? 'Saqlanmoqdaâ€¦' : editing ? 'Saqlash' : "Qo'shish"}
            </button>
          </Group>
        </form>
      </div>

      <Group align="flex-end" justify="space-between" wrap="wrap">
        <Group align="flex-end" wrap="wrap">
          <TextInput
            label="Qidiruv"
            placeholder="Kod bo'yicha"
            value={search}
            onChange={(event) => setSearch(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                setPage(1)
                setQuery(search.trim())
              }
            }}
            w={{ base: '100%', sm: 240 }}
          />
          <Select
            label="Holat"
            data={STATUS_OPTIONS}
            value={status}
            onChange={(value) => {
              setStatus(value || '')
              setPage(1)
            }}
            allowDeselect={false}
            w={180}
          />
          <button
            type="button"
            className="admin-btn admin-btn-secondary"
            onClick={() => {
              setPage(1)
              setQuery(search.trim())
            }}
          >
            <i className="bi bi-search" /> Filtrlash
          </button>
        </Group>
        <button
          type="button"
          className="admin-btn admin-btn-secondary"
          onClick={() => {
            setSearch('')
            setQuery('')
            setStatus('')
            setPage(1)
          }}
        >
          Tozalash
        </button>
      </Group>

      {loading ? (
        <div className="admin-loading"><Loader /></div>
      ) : results.length === 0 ? (
        <EmptyState
          icon="bi-percent"
          title="Kupon yo'q"
          description="Yuqoridagi shakldan yangi promo kod yarating."
        />
      ) : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Kod</th>
                <th>Kun</th>
                <th>Ishlatilgan</th>
                <th>Holat</th>
                <th>Kanal</th>
                <th>Yaratilgan</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {results.map((coupon) => (
                <tr key={coupon.id}>
                  <td>
                    <Group gap={6} wrap="nowrap">
                      <Text fw={600} size="sm">{coupon.code}</Text>
                      <ActionIcon
                        variant="subtle"
                        size="sm"
                        onClick={() => copyCode(coupon.code)}
                        title="Nusxalash"
                      >
                        <i className="bi bi-clipboard" />
                      </ActionIcon>
                    </Group>
                  </td>
                  <td>{coupon.days}</td>
                  <td>
                    {coupon.used_count} / {coupon.max_uses}
                    <Text size="xs" c="dimmed">Qoldi: {coupon.remaining}</Text>
                  </td>
                  <td>
                    <Badge variant="light" color={COUPON_STATUS_COLORS[coupon.status] || undefined}>
                      {coupon.status_label || COUPON_STATUS_LABELS[coupon.status] || coupon.status}
                    </Badge>
                  </td>
                  <td>
                    {coupon.posted_channel_title ? (
                      <>
                        <Text size="sm">{coupon.posted_channel_title}</Text>
                        {coupon.posted_message_id ? (
                          <Text size="xs" c="dimmed">Xabar: {coupon.posted_message_id}</Text>
                        ) : null}
                      </>
                    ) : (
                      <Text size="sm" c="dimmed">â€”</Text>
                    )}
                  </td>
                  <td>{formatDate(coupon.created_at)}</td>
                  <td>
                    <Group gap={4} wrap="nowrap">
                      <ActionIcon
                        variant="subtle"
                        color="green"
                        onClick={() => handlePublish(coupon)}
                        loading={busyId === coupon.id}
                        title="Kanalga joylash"
                      >
                        <i className="bi bi-send" />
                      </ActionIcon>
                      <ActionIcon
                        variant="subtle"
                        color="indigo"
                        onClick={() => showRedemptions(coupon)}
                        title="Ishlatganlar"
                      >
                        <i className="bi bi-people" />
                      </ActionIcon>
                      <ActionIcon
                        variant="subtle"
                        color="orange"
                        onClick={() => handleToggle(coupon)}
                        loading={busyId === coupon.id}
                        title={coupon.is_active ? "To'xtatish" : 'Faollashtirish'}
                      >
                        <i className={`bi ${coupon.is_active ? 'bi-pause' : 'bi-play'}`} />
                      </ActionIcon>
                      <ActionIcon
                        variant="subtle"
                        color="blue"
                        onClick={() => startEdit(coupon)}
                        title="Tahrirlash"
                      >
                        <i className="bi bi-pencil" />
                      </ActionIcon>
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        onClick={() => setDeleteTarget(coupon)}
                        title="O'chirish"
                      >
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

      <PaginationBar
        page={page}
        totalPages={totalPages}
        count={count}
        onChange={setPage}
        loading={loading}
      />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Kuponni o'chirish"
        message={`"${deleteTarget?.code}" kupon va uning ishlatilish tarixi o'chiriladi.`}
        confirmLabel="O'chirish"
        danger
        loading={busy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      />

      {redemptions ? (
        <div
          className="admin-modal-backdrop"
          role="presentation"
          onClick={() => setRedemptions(null)}
        >
          <div
            className="admin-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Kuponni ishlatganlar"
            onClick={(event) => event.stopPropagation()}
          >
            <Title order={4} mb="xs">{redemptions.coupon.code} â€” ishlatganlar</Title>
            {redemptions.loading ? (
              <div className="admin-loading"><Loader /></div>
            ) : redemptions.rows.length === 0 ? (
              <Text c="dimmed" size="sm">Hozircha hech kim ishlatmagan.</Text>
            ) : (
              <div className="admin-table-wrap">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>Foydalanuvchi</th>
                      <th>Telegram ID</th>
                      <th>Kun</th>
                      <th>Sana</th>
                    </tr>
                  </thead>
                  <tbody>
                    {redemptions.rows.map((row) => (
                      <tr key={row.id}>
                        <td>{row.username || `#${row.user}`}</td>
                        <td>{row.telegram_id ?? 'â€”'}</td>
                        <td>{row.days}</td>
                        <td>{formatDateTime(row.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <Group justify="flex-end" mt="md">
              <button
                type="button"
                className="admin-btn admin-btn-secondary"
                onClick={() => setRedemptions(null)}
              >
                Yopish
              </button>
            </Group>
          </div>
        </div>
      ) : null}
    </Stack>
  )
}
