import {
  ActionIcon,
  Badge,
  Group,
  Loader,
  Menu,
  Select,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { adminUsersApi } from '../api/adminApi'
import { formatDate, formatDateTime } from '../../utils/dates'
import { adminPath } from '../adminBase'
import {
  ConfirmDialog,
  EmptyState,
  ErrorAlert,
  PaginationBar,
  PLAN_COLORS,
  PLAN_LABELS,
  SectionHeading,
  SuccessAlert,
} from '../components/adminShared'
import { copyText, formatError } from '../utils/formUtils'

const PLAN_OPTIONS = Object.entries(PLAN_LABELS).map(([value, label]) => ({ value, label }))

export default function UsersPage() {
  const [search, setSearch] = useState('')
  const [plan, setPlan] = useState('')
  const [blocked, setBlocked] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ results: [], count: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [planTarget, setPlanTarget] = useState(null)
  const [blockTarget, setBlockTarget] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = { page, page_size: 20 }
      if (search) params.search = search
      if (plan) params.plan = plan
      if (blocked) params.blocked = blocked === 'blocked' ? '1' : '0'
      const result = await adminUsersApi.list(params)
      setData(result)
    } catch (err) {
      setError(formatError(err, 'Foydalanuvchilarni yuklashda xatolik.'))
    } finally {
      setLoading(false)
    }
  }, [page, search, plan, blocked])

  useEffect(() => {
    load()
  }, [load])

  async function changePlan(nextPlan) {
    if (!planTarget) return
    setBusy(true)
    setError(null)
    try {
      await adminUsersApi.setPlan(planTarget.id, nextPlan)
      setSuccess(`Tarif ${PLAN_LABELS[nextPlan] || nextPlan} ga o'zgartirildi.`)
      setPlanTarget(null)
      await load()
    } catch (err) {
      setError(formatError(err, "Tarifni o'zgartirishda xatolik."))
      setPlanTarget(null)
    } finally {
      setBusy(false)
    }
  }

  async function toggleBlock() {
    if (!blockTarget) return
    setBusy(true)
    setError(null)
    try {
      await adminUsersApi.setBlock(blockTarget.id, !blockTarget.is_blocked)
      setSuccess(blockTarget.is_blocked ? 'Foydalanuvchi ochildi.' : 'Foydalanuvchi bloklandi.')
      setBlockTarget(null)
      await load()
    } catch (err) {
      setError(formatError(err, 'Amalni bajarishda xatolik.'))
      setBlockTarget(null)
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
        title="Foydalanuvchilar"
        description="Telegram profillar, tariflar va bloklash."
      />
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>
      <Group align="flex-end">
        <TextInput
          label="Qidiruv"
          placeholder="Username, ism yoki telegram_id"
          value={search}
          onChange={(event) => {
            setSearch(event.currentTarget.value)
            setPage(1)
          }}
          w={{ base: '100%', sm: 280 }}
        />
        <Select
          label="Tarif"
          data={[{ value: '', label: 'Barchasi' }, ...PLAN_OPTIONS]}
          value={plan}
          onChange={(value) => {
            setPlan(value || '')
            setPage(1)
          }}
          clearable
          w={140}
        />
        <Select
          label="Holat"
          data={[
            { value: '', label: 'Barchasi' },
            { value: 'active', label: 'Faol' },
            { value: 'blocked', label: 'Bloklangan' },
          ]}
          value={blocked}
          onChange={(value) => {
            setBlocked(value || '')
            setPage(1)
          }}
          clearable
          w={150}
        />
      </Group>

      {loading ? (
        <div className="admin-loading"><Loader /></div>
      ) : results.length === 0 ? (
        <EmptyState icon="bi-people" title="Foydalanuvchi topilmadi" />
      ) : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Foydalanuvchi</th>
                <th>Telegram</th>
                <th>Tarif</th>
                <th>Holat</th>
                <th>Oxirgi faollik</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {results.map((user) => (
                <tr key={user.id}>
                  <td>
                    <Text fw={600} size="sm">
                      {user.username || user.full_name || '—'}
                    </Text>
                    <Text size="xs" c="dimmed">{user.email || ''}</Text>
                  </td>
                  <td>
                    <Group gap={4}>
                      <Text size="sm" style={{ fontFamily: 'monospace' }}>{user.telegram_id}</Text>
                      <ActionIcon
                        variant="subtle"
                        size="xs"
                        onClick={() => copyText(String(user.telegram_id))}
                        title="Nusxalash"
                      >
                        <i className="bi bi-clipboard" />
                      </ActionIcon>
                      {user.is_staff ? <Badge size="xs" color="red">Staff</Badge> : null}
                    </Group>
                  </td>
                  <td>
                    <Badge color={PLAN_COLORS[user.plan] || 'gray'} variant="light">
                      {PLAN_LABELS[user.plan] || user.plan}
                    </Badge>
                    {user.plan !== 'free' && (
                      <Text size="xs" c="dimmed" mt={2}>
                        {user.plan_active
                          ? `amal qiladi${user.plan_expires ? ` · ${formatDate(user.plan_expires)}` : ''}`
                          : 'muddati o\'tgan'}
                      </Text>
                    )}
                  </td>
                  <td>
                    <Badge color={user.is_blocked ? 'red' : 'green'} variant="light">
                      {user.is_blocked ? 'Bloklangan' : 'Faol'}
                    </Badge>
                  </td>
                  <td>
                    <Text size="xs" c="dimmed">
                      {user.last_seen_at
                        ? formatDateTime(user.last_seen_at)
                        : user.created_at
                          ? formatDateTime(user.created_at)
                          : '—'}
                    </Text>
                  </td>
                  <td>
                    <Group gap={4} wrap="nowrap">
                      <ActionIcon
                        variant="subtle"
                        color="blue"
                        component={Link}
                        to={adminPath(`/users/${user.id}`)}
                        title="Batafsil"
                      >
                        <i className="bi bi-eye" />
                      </ActionIcon>
                      <Menu position="bottom-end" withinPortal>
                        <Menu.Target>
                          <ActionIcon variant="subtle" title="Amallar">
                            <i className="bi bi-three-dots-vertical" />
                          </ActionIcon>
                        </Menu.Target>
                        <Menu.Dropdown>
                          <Menu.Label>Tarif</Menu.Label>
                          {Object.keys(PLAN_LABELS).map((planKey) => (
                            <Menu.Item
                              key={planKey}
                              disabled={user.plan === planKey}
                              onClick={() => setPlanTarget({ ...user, nextPlan: planKey })}
                            >
                              {PLAN_LABELS[planKey]}
                            </Menu.Item>
                          ))}
                          <Menu.Divider />
                          <Menu.Item
                            color={user.is_blocked ? 'green' : 'red'}
                            onClick={() => setBlockTarget(user)}
                          >
                            {user.is_blocked ? 'Blokdan olish' : 'Bloklash'}
                          </Menu.Item>
                        </Menu.Dropdown>
                      </Menu>
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
        open={Boolean(planTarget)}
        title="Tarifni o'zgartirish"
        message={`${planTarget?.username || planTarget?.telegram_id} uchun tarif "${PLAN_LABELS[planTarget?.nextPlan] || planTarget?.nextPlan}" bo'lsinmi?`}
        confirmLabel="Ha, o'zgartirish"
        loading={busy}
        onCancel={() => setPlanTarget(null)}
        onConfirm={() => changePlan(planTarget.nextPlan)}
      />

      <ConfirmDialog
        open={Boolean(blockTarget)}
        title={blockTarget?.is_blocked ? 'Blokdan olish' : 'Bloklash'}
        message={
          blockTarget?.is_blocked
            ? 'Foydalanuvchi botdan yana foydalana oladi.'
            : 'Foydalanuvchi botdan foydalana olmaydi.'
        }
        confirmLabel="Tasdiqlash"
        danger={!blockTarget?.is_blocked}
        loading={busy}
        onCancel={() => setBlockTarget(null)}
        onConfirm={toggleBlock}
      />
    </Stack>
  )
}

export function UserDetailPage() {
  const { userId } = useParams()
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    adminUsersApi
      .detail(userId)
      .then((data) => {
        if (active) setUser(data)
      })
      .catch((err) => {
        if (active) setError(formatError(err, 'Foydalanuvchi topilmadi.'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [userId])

  if (loading) return <div className="admin-loading"><Loader size="lg" /></div>
  if (!user) return <ErrorAlert>{error || 'Topilmadi.'}</ErrorAlert>

  return (
    <Stack gap="lg">
      <SectionHeading
        title={user.username || user.full_name || String(user.telegram_id)}
        description="Foydalanuvchi profili va to'lov tarixi."
        actions={
          <Link className="admin-btn admin-btn-secondary" to={adminPath('/users')}>
            Ro'yxat
          </Link>
        }
      />
      <div className="admin-panel">
        <Title order={5} mb="sm">Asosiy ma'lumotlar</Title>
        <Stack gap="xs">
          <DetailRow label="Telegram ID" value={user.telegram_id} />
          <DetailRow label="Ism" value={user.full_name || '—'} />
          <DetailRow label="Username" value={user.username || '—'} />
          <DetailRow label="Email" value={user.email || '—'} />
          <DetailRow label="Til" value={user.language_code || '—'} />
          <DetailRow label="Tarif" value={PLAN_LABELS[user.plan] || user.plan} />
          {user.plan !== 'free' && (
            <DetailRow
              label="Obuna muddati"
              value={
                user.plan_active
                  ? `faol${user.plan_expires ? ` · ${formatDate(user.plan_expires)}` : ''}`
                  : "muddati o'tgan"
              }
            />
          )}
          <DetailRow label="Holat" value={user.is_blocked ? 'Bloklangan' : 'Faol'} />
          <DetailRow
            label="Ro'yxatdan o'tgan"
            value={formatDateTime(user.created_at)}
          />
          <DetailRow
            label="Oxirgi faollik"
            value={formatDateTime(user.last_seen_at)}
          />
          <DetailRow label="Sevimlilar" value={user.favorites_count} />
        </Stack>
      </div>

      {user.requests?.length ? (
        <div className="admin-panel">
          <Title order={5} mb="sm">So'nggi arizalar</Title>
          <Stack gap="xs">
            {user.requests.map((request) => (
              <Group key={request.id} justify="space-between">
                <Text size="sm">
                  {request.plan_label} · {Number(request.amount).toLocaleString()} so'm
                </Text>
                <Badge variant="light">{request.status_label}</Badge>
              </Group>
            ))}
          </Stack>
        </div>
      ) : null}
    </Stack>
  )
}

function DetailRow({ label, value }) {
  return (
    <Group justify="space-between">
      <Text size="sm" c="dimmed">{label}</Text>
      <Text size="sm" fw={500}>{value}</Text>
    </Group>
  )
}
