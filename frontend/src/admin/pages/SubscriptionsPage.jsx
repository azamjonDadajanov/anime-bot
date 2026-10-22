import {
  Badge,
  Group,
  Image,
  Loader,
  Modal,
  Stack,
  Text,
  Textarea,
  Title,
} from '@mantine/core'
import { useCallback, useEffect, useState } from 'react'
import { adminSubscriptionApi } from '../api/adminApi'
import { formatDateTime } from '../../utils/dates'
import {
  ConfirmDialog,
  EmptyState,
  ErrorAlert,
  PaginationBar,
  REQUEST_STATUS_LABELS,
  SectionHeading,
  SuccessAlert,
} from '../components/adminShared'
import { formatError } from '../utils/formUtils'

const STATUS_FILTERS = [
  { value: 'pending', label: 'Kutilmoqda' },
  { value: 'approved', label: 'Tasdiqlangan' },
  { value: 'rejected', label: 'Rad etilgan' },
]

export default function SubscriptionsPage() {
  const [status, setStatus] = useState('pending')
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ results: [], count: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [actionTarget, setActionTarget] = useState(null)
  const [actionType, setActionType] = useState('approve')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = { page, page_size: 20 }
      if (status) params.status = status
      const result = await adminSubscriptionApi.list(params)
      setData(result)
    } catch (err) {
      setError(formatError(err, 'Arizalarni yuklashda xatolik.'))
    } finally {
      setLoading(false)
    }
  }, [page, status])

  useEffect(() => {
    load()
  }, [load])

  async function processRequest() {
    if (!actionTarget) return
    setBusy(true)
    setError(null)
    try {
      if (actionType === 'approve') {
        await adminSubscriptionApi.approve(actionTarget.id, notes)
        setSuccess("Ariza tasdiqlandi va tarif yangilandi.")
      } else {
        await adminSubscriptionApi.reject(actionTarget.id, notes)
        setSuccess('Ariza rad etildi.')
      }
      setActionTarget(null)
      setNotes('')
      await load()
    } catch (err) {
      setError(formatError(err, "Arizani ko'rib chiqishda xatolik."))
      setActionTarget(null)
    } finally {
      setBusy(false)
    }
  }

  const results = data.results || []
  const count = data.count || 0
  const totalPages = Math.max(1, Math.ceil(count / 20))

  return (
    <Stack gap="lg">
      <SectionHeading
        title="Obuna arizalari"
        description="To'lov arizalarini tasdiqlash yoki rad etish."
        actions={
          <Group gap="xs">
            {STATUS_FILTERS.map((item) => (
              <button
                key={item.value}
                type="button"
                className={`admin-btn ${status === item.value ? 'admin-btn-primary' : 'admin-btn-secondary'}`}
                onClick={() => {
                  setStatus(item.value)
                  setPage(1)
                }}
              >
                {item.label}
              </button>
            ))}
          </Group>
        }
      />
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>

      {loading ? (
        <div className="admin-loading"><Loader /></div>
      ) : results.length === 0 ? (
        <EmptyState icon="bi-ticket-perforated" title="Ariza topilmadi" />
      ) : (
        <Stack gap="md">
          {results.map((request) => (
            <div key={request.id} className="admin-panel">
              <Group justify="space-between" align="flex-start" wrap="wrap">
                <Stack gap={4}>
                  <Title order={5}>
                    {request.user || '—'} · {request.plan_label}
                  </Title>
                  <Text size="sm" c="dimmed">
                    Telegram: {request.telegram_id || '—'} · {Number(request.amount).toLocaleString()} so'm
                  </Text>
                  <Text size="xs" c="dimmed">
                    {formatDateTime(request.created_at)}
                  </Text>
                  <Badge
                    variant="light"
                    color={
                      request.status === 'approved'
                        ? 'green'
                        : request.status === 'rejected'
                          ? 'red'
                          : 'yellow'
                    }
                  >
                    {REQUEST_STATUS_LABELS[request.status] || request.status}
                  </Badge>
                </Stack>
                <Group gap="xs" align="flex-start">
                  {request.screenshot_url ? (
                    <button
                      type="button"
                      className="admin-btn admin-btn-secondary"
                      onClick={() => setPreview(request.screenshot_url)}
                    >
                      Chek
                    </button>
                  ) : null}
                  {request.status === 'pending' ? (
                    <>
                      <button
                        type="button"
                        className="admin-btn admin-btn-primary"
                        onClick={() => {
                          setActionTarget(request)
                          setActionType('approve')
                          setNotes('')
                        }}
                      >
                        Tasdiqlash
                      </button>
                      <button
                        type="button"
                        className="admin-btn admin-btn-danger"
                        onClick={() => {
                          setActionTarget(request)
                          setActionType('reject')
                          setNotes('')
                        }}
                      >
                        Rad etish
                      </button>
                    </>
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

      <Modal
        opened={Boolean(preview)}
        onClose={() => setPreview(null)}
        title="To'lov cheki"
        centered
        size="lg"
      >
        {preview ? <Image src={preview} radius="sm" alt="To'lov cheki" /> : null}
      </Modal>

      <ConfirmDialog
        open={Boolean(actionTarget)}
        title={actionType === 'approve' ? 'Arizani tasdiqlash' : 'Arizani rad etish'}
        message={
          actionType === 'approve'
            ? `${actionTarget?.user} uchun "${actionTarget?.plan_label || actionTarget?.plan}" tarifi faollashadi.`
            : 'Ariza rad etiladi.'
        }
        confirmLabel={actionType === 'approve' ? 'Tasdiqlash' : 'Rad etish'}
        danger={actionType === 'reject'}
        loading={busy}
        onCancel={() => setActionTarget(null)}
        onConfirm={processRequest}
      >
        <Textarea
          label="Izoh"
          value={notes}
          onChange={(event) => setNotes(event.currentTarget.value)}
        />
      </ConfirmDialog>
    </Stack>
  )
}
