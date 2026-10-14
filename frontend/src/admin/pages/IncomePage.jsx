import {
  ActionIcon,
  Group,
  Loader,
  NumberInput,
  Select,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core'
import { useCallback, useEffect, useState } from 'react'
import { adminIncomeApi } from '../api/adminApi'
import {
  ConfirmDialog,
  EmptyState,
  ErrorAlert,
  INCOME_METHOD_LABELS,
  INCOME_SOURCE_LABELS,
  PaginationBar,
  PLAN_LABELS,
  SectionHeading,
  SuccessAlert,
} from '../components/adminShared'
import { currentYearMonth, formatError, inputHandler, numberHandler, selectHandler, todayISODate } from '../utils/formUtils'

const SOURCE_OPTIONS = Object.entries(INCOME_SOURCE_LABELS).map(([value, label]) => ({ value, label }))
const METHOD_OPTIONS = Object.entries(INCOME_METHOD_LABELS).map(([value, label]) => ({ value, label }))
const PLAN_OPTIONS = [
  { value: '', label: "—" },
  ...Object.entries(PLAN_LABELS).map(([value, label]) => ({ value, label })),
]

const EMPTY_FORM = {
  amount: '',
  source: 'subscription',
  method: 'card',
  plan: '',
  note: '',
  paid_at: todayISODate(),
}

export default function IncomePage() {
  const [month, setMonth] = useState(currentYearMonth)
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ results: [], count: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [editing, setEditing] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = { page, page_size: 20 }
      if (month) params.month = month
      const result = await adminIncomeApi.list(params)
      setData(result)
    } catch (err) {
      setError(formatError(err, 'Tushumlarni yuklashda xatolik.'))
    } finally {
      setLoading(false)
    }
  }, [page, month])

  useEffect(() => {
    load()
  }, [load])

  async function handleSubmit(event) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const payload = {
        amount: Number(form.amount) || 0,
        source: form.source,
        method: form.method,
        plan: form.plan || '',
        note: form.note || '',
        paid_at: form.paid_at
          ? new Date(`${form.paid_at}T12:00:00`).toISOString()
          : new Date().toISOString(),
      }
      if (editing) {
        await adminIncomeApi.update(editing.id, payload)
        setSuccess('Tushum yangilandi.')
        setEditing(null)
      } else {
        await adminIncomeApi.create(payload)
        setSuccess("Tushum qo'shildi.")
      }
      setForm({ ...EMPTY_FORM, paid_at: todayISODate() })
      await load()
    } catch (err) {
      setError(formatError(err, "Saqlashda xatolik."))
    } finally {
      setSaving(false)
    }
  }

  function startEdit(item) {
    setEditing(item)
    setForm({
      amount: item.amount,
      source: item.source,
      method: item.method,
      plan: item.plan || '',
      note: item.note || '',
      paid_at: item.paid_at ? String(item.paid_at).slice(0, 10) : todayISODate(),
    })
  }

  function cancelEdit() {
    setEditing(null)
    setForm({ ...EMPTY_FORM, paid_at: todayISODate() })
  }

  async function handleDelete() {
    if (!deleteTarget) return
    setBusy(true)
    try {
      await adminIncomeApi.remove(deleteTarget.id)
      setDeleteTarget(null)
      setSuccess("Tushum o'chirildi.")
      await load()
    } catch (err) {
      setError(formatError(err, "O'chirishda xatolik."))
      setDeleteTarget(null)
    } finally {
      setBusy(false)
    }
  }

  const results = data.results || []
  const count = data.count || 0
  const totalPages = Math.max(1, Math.ceil(count / 20))
  const shownTotal = results.reduce((sum, item) => sum + Number(item.amount || 0), 0)

  return (
    <Stack gap="lg">
      <SectionHeading
        title="Oylik tushumlar"
        description="Obuna va boshqa tushumlarni qo'shish, tahrirlash va hisobot."
        actions={
          <TextInput
            type="month"
            label="Oy"
            value={month}
            onChange={(event) => {
              setMonth(event.currentTarget.value)
              setPage(1)
            }}
            w={180}
          />
        }
      />
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>

      <div className="admin-panel">
        <Title order={5} mb="sm">{editing ? 'Tushumni tahrirlash' : "Yangi tushum"}</Title>
        <form onSubmit={handleSubmit}>
          <Group align="flex-end" grow>
            <NumberInput
              label="Summa (so'm)"
              min={0}
              precision={2}
              value={form.amount}
              onChange={numberHandler(setForm, 'amount')}
              required
            />
            <Select
              label="Manba"
              data={SOURCE_OPTIONS}
              value={form.source}
              onChange={selectHandler(setForm, 'source')}
              allowDeselect={false}
            />
            <Select
              label="To'lov usuli"
              data={METHOD_OPTIONS}
              value={form.method}
              onChange={selectHandler(setForm, 'method')}
              allowDeselect={false}
            />
            <Select
              label="Tarif"
              data={PLAN_OPTIONS}
              value={form.plan}
              onChange={selectHandler(setForm, 'plan')}
              allowDeselect
              placeholder="—"
            />
            <TextInput
              type="date"
              label="Sana"
              value={form.paid_at}
              onChange={inputHandler(setForm, 'paid_at')}
            />
          </Group>
          <Textarea
            label="Izoh"
            mt="md"
            minRows={2}
            value={form.note}
            onChange={inputHandler(setForm, 'note')}
          />
          <Group justify="flex-end" mt="md">
            {editing ? (
              <button type="button" className="admin-btn admin-btn-secondary" onClick={cancelEdit}>
                Bekor qilish
              </button>
            ) : null}
            <button type="submit" className="admin-btn admin-btn-primary" disabled={saving}>
              {saving ? 'Saqlanmoqda…' : editing ? 'Yangilash' : "Qo'shish"}
            </button>
          </Group>
        </form>
      </div>

      <Text size="sm" c="dimmed">
        Ko'rsatilgan yozuvlar jami: {shownTotal.toLocaleString()} so'm
      </Text>

      {loading ? (
        <div className="admin-loading"><Loader /></div>
      ) : results.length === 0 ? (
        <EmptyState icon="bi-cash-coin" title="Tushum yo'q" description="Yuqoridan tushum qo'shing." />
      ) : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Sana</th>
                <th>Summa</th>
                <th>Manba</th>
                <th>Usul</th>
                <th>Tarif</th>
                <th>Izoh</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {results.map((item) => (
                <tr key={item.id}>
                  <td>{item.paid_at ? new Date(item.paid_at).toLocaleDateString() : '—'}</td>
                  <td style={{ fontWeight: 600 }}>{Number(item.amount).toLocaleString()}</td>
                  <td>{item.source_label || INCOME_SOURCE_LABELS[item.source] || item.source}</td>
                  <td>{item.method_label || INCOME_METHOD_LABELS[item.method] || item.method}</td>
                  <td>{PLAN_LABELS[item.plan] || item.plan || '—'}</td>
                  <td>
                    <Text size="xs" lineClamp={2}>{item.note || '—'}</Text>
                  </td>
                  <td>
                    <Group gap={4} wrap="nowrap">
                      <ActionIcon variant="subtle" color="blue" onClick={() => startEdit(item)} title="Tahrirlash">
                        <i className="bi bi-pencil" />
                      </ActionIcon>
                      <ActionIcon variant="subtle" color="red" onClick={() => setDeleteTarget(item)} title="O'chirish">
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
        title="Tushumni o'chirish"
        message={`${deleteTarget?.amount} so'mlik yozuv o'chiriladi.`}
        confirmLabel="O'chirish"
        danger
        loading={busy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      />
    </Stack>
  )
}
