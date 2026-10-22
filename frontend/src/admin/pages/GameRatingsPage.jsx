import {
  ActionIcon,
  Badge,
  Button,
  Group,
  Loader,
  NumberInput,
  Pagination,
  Select,
  Stack,
  Tabs,
  Text,
  TextInput,
} from '@mantine/core'
import { useCallback, useEffect, useState } from 'react'
import { adminGameApi } from '../api/adminApi'
import { formatDateTime } from '../../utils/dates'
import {
  ConfirmDialog,
  EmptyState,
  ErrorAlert,
  SectionHeading,
  StatCard,
  SuccessAlert,
} from '../components/adminShared'
import { formatError } from '../utils/formUtils'

const PAGE_SIZE = 20
const CURRENT_YEAR = new Date().getFullYear()
const CURRENT_MONTH = new Date().getMonth() + 1

export default function GameRatingsPage() {
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  const [tab, setTab] = useState('leaderboard')
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)

  const [leaderboard, setLeaderboard] = useState({ results: [], count: 0 })
  const [attempts, setAttempts] = useState({ results: [], count: 0 })
  const [prizes, setPrizes] = useState({ results: [], count: 0 })
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [suspiciousOnly, setSuspiciousOnly] = useState(false)
  const [prizeYear, setPrizeYear] = useState(String(CURRENT_YEAR))

  const [deleteTarget, setDeleteTarget] = useState(null)
  const [busy, setBusy] = useState(false)
  const [busyId, setBusyId] = useState(null)
  const [awarding, setAwarding] = useState(false)

  const [prizeForm, setPrizeForm] = useState({
    year: CURRENT_YEAR,
    month: CURRENT_MONTH,
    user: '',
    points: 0,
    days: 30,
  })
  const [prizeSaving, setPrizeSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      if (tab === 'leaderboard') {
        const data = await adminGameApi.leaderboard({ limit: 100 })
        setLeaderboard(data)
        setTotalPages(1)
      } else if (tab === 'attempts') {
        const params = { page, page_size: PAGE_SIZE }
        if (query) params.search = query
        if (suspiciousOnly) params.suspicious = '1'
        const data = await adminGameApi.attempts(params)
        setAttempts(data)
        setTotalPages(Math.max(1, Math.ceil((data.count || 0) / PAGE_SIZE)))
      } else {
        const data = await adminGameApi.prizes({ year: prizeYear, page, page_size: PAGE_SIZE })
        setPrizes(data)
        setTotalPages(Math.max(1, Math.ceil((data.count || 0) / PAGE_SIZE)))
      }
    } catch (err) {
      setError(formatError(err, "Ma'lumotni yuklashda xatolik."))
    } finally {
      setLoading(false)
    }
  }, [tab, page, query, suspiciousOnly, prizeYear])

  useEffect(() => {
    load()
  }, [load])

  function changeTab(value) {
    setTab(value || 'leaderboard')
    setPage(1)
    setQuery('')
    setSuspiciousOnly(false)
  }

  async function handleToggleSuspicious(attempt) {
    setBusyId(attempt.id)
    setError(null)
    try {
      await adminGameApi.updateAttempt(attempt.id, { is_suspicious: !attempt.is_suspicious })
      setSuccess(attempt.is_suspicious ? 'Belgi olib tashlandi.' : 'Urinish shubhali deb belgilandi.')
      await load()
    } catch (err) {
      setError(formatError(err, "O'zgartirishda xatolik."))
    } finally {
      setBusyId(null)
    }
  }

  async function handleDeleteAttempt() {
    if (!deleteTarget || deleteTarget.kind !== 'attempt') return
    setBusy(true)
    try {
      await adminGameApi.removeAttempt(deleteTarget.item.id)
      setSuccess('Urinish o\'chirildi.')
      setDeleteTarget(null)
      await load()
    } catch (err) {
      setError(formatError(err, "O'chirishda xatolik."))
      setDeleteTarget(null)
    } finally {
      setBusy(false)
    }
  }

  async function handleDeletePrize() {
    if (!deleteTarget || deleteTarget.kind !== 'prize') return
    setBusy(true)
    try {
      await adminGameApi.removePrize(deleteTarget.item.id)
      setSuccess('Sovrin o\'chirildi.')
      setDeleteTarget(null)
      await load()
    } catch (err) {
      setError(formatError(err, "O'chirishda xatolik."))
      setDeleteTarget(null)
    } finally {
      setBusy(false)
    }
  }

  async function handleAward() {
    setAwarding(true)
    setError(null)
    try {
      const prize = await adminGameApi.awardPrize({
        year: new Date().getFullYear(),
        month: new Date().getMonth() + 1,
      })
      setSuccess(`Sovrin berildi: ${prize.username || prize.user} (${prize.points} ball).`)
      await load()
    } catch (err) {
      setError(formatError(err, 'Sovrin berishda xatolik.'))
    } finally {
      setAwarding(false)
    }
  }

  async function handleCreatePrize(event) {
    event.preventDefault()
    if (!prizeForm.user) {
      setError('Foydalanuvchini tanlang.')
      return
    }
    setPrizeSaving(true)
    setError(null)
    try {
      await adminGameApi.createPrize({
        year: Number(prizeForm.year),
        month: Number(prizeForm.month),
        user: Number(prizeForm.user),
        points: Number(prizeForm.points) || 0,
        days: Number(prizeForm.days) || 30,
      })
      setSuccess('Sovrin qo\'shildi.')
      setPrizeForm({ ...prizeForm, user: '', points: 0 })
      await load()
    } catch (err) {
      setError(formatError(err, 'Saqlashda xatolik.'))
    } finally {
      setPrizeSaving(false)
    }
  }

  const lbResults = leaderboard.results || []
  const atResults = attempts.results || []
  const prResults = prizes.results || []
  const totalPlayers = leaderboard.count || lbResults.length
  const topPoints = lbResults[0]?.points || 0
  const suspiciousCount = atResults.filter((a) => a.is_suspicious).length

  const monthNames = [
    'Yanvar', 'Fevral', 'Mart', 'Aprel', 'May', 'Iyun',
    'Iyul', 'Avgust', 'Sentabr', 'Oktabr', 'Noyabr', 'Dekabr',
  ]

  return (
    <Stack gap="lg">
      <SectionHeading
        title="O'yin reytingi"
        description="Reyting jadvali, o'yin urinishlari, tasdiqlangan animelar va oylik sovrinlar."
        actions={
          <Button
            leftSection={<i className="bi bi-trophy" />}
            onClick={handleAward}
            loading={awarding}
            disabled={tab !== 'leaderboard'}
          >
            Oylik sovrinni berish
          </Button>
        }
      />
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>

      <Group grow>
        <StatCard title="Faol o'yinchilar" value={totalPlayers} icon="bi-people" color="blue" />
        <StatCard title="Eng yuqori ball" value={topPoints} icon="bi-trophy" color="green" />
        <StatCard title="Shubhali urinishlar" value={suspiciousCount} icon="bi-exclamation-triangle" color="orange" />
      </Group>

      <Tabs value={tab} onChange={changeTab}>
        <Tabs.List>
          <Tabs.Tab value="leaderboard" leftSection={<i className="bi bi-bar-chart" />}>Reyting</Tabs.Tab>
          <Tabs.Tab value="attempts" leftSection={<i className="bi bi-clock-history" />}>Urinishlar</Tabs.Tab>
          <Tabs.Tab value="prizes" leftSection={<i className="bi bi-gift" />}>Sovrinlar</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="leaderboard" pt="md">
          {loading ? (
            <div className="admin-loading"><Loader /></div>
          ) : lbResults.length === 0 ? (
            <EmptyState
              icon="bi-bar-chart"
              title="Reyting bo'sh"
              description="Hali bironta o'yin urinishi yozilmagan."
            />
          ) : (
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>O'rin</th>
                    <th>Foydalanuvchi</th>
                    <th>Telegram ID</th>
                    <th>Ball</th>
                    <th>Daraja</th>
                    <th>Tasdiqlangan</th>
                    <th>Urinishlar</th>
                  </tr>
                </thead>
                <tbody>
                  {lbResults.map((row) => (
                    <tr key={row.user_id}>
                      <td>
                        <Badge
                          color={row.rank <= 3 ? 'gold' : 'gray'}
                          variant={row.rank <= 3 ? 'filled' : 'light'}
                        >
                          {row.rank}
                        </Badge>
                      </td>
                      <td><Text size="sm" fw={600}>{row.name || '—'}</Text></td>
                      <td><Text size="sm" c="dimmed">{row.telegram_id || '—'}</Text></td>
                      <td><Text size="sm" fw={700}>{row.points}</Text></td>
                      <td>
                        <Text size="sm" fw={500}>{row.level_name}</Text>
                        <Text size="xs" c="dimmed">Daraja {row.level}</Text>
                      </td>
                      <td>
                        {row.verified > 0 ? (
                          <Badge color="green" variant="light">{row.verified}</Badge>
                        ) : (
                          <Text size="sm" c="dimmed">0</Text>
                        )}
                      </td>
                      <td><Text size="sm">{row.attempts}</Text></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Tabs.Panel>

        <Tabs.Panel value="attempts" pt="md">
          <Group align="flex-end" justify="space-between" mb="md" wrap="wrap">
            <Group align="flex-end" wrap="wrap">
              <TextInput
                label="Qidiruv"
                placeholder="Foydalanuvchi yoki anime"
                value={search}
                onChange={(event) => setSearch(event.currentTarget.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    setPage(1)
                    setQuery(search.trim())
                  }
                }}
                w={{ base: '100%', sm: 260 }}
              />
              <Select
                label="Holat"
                data={[
                  { value: '', label: 'Barchasi' },
                  { value: 'suspicious', label: 'Shubhali' },
                ]}
                value={suspiciousOnly ? 'suspicious' : ''}
                onChange={(value) => {
                  setSuspiciousOnly(value === 'suspicious')
                  setPage(1)
                }}
                w={180}
                clearable
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
          </Group>

          {loading ? (
            <div className="admin-loading"><Loader /></div>
          ) : atResults.length === 0 ? (
            <EmptyState
              icon="bi-clock-history"
              title="Urinish topilmadi"
              description="Filtrlarni o'zgartirib ko'ring yoki o'yinchilar o'ynaganidan so'ng ko'ring."
            />
          ) : (
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Foydalanuvchi</th>
                    <th>Anime</th>
                    <th>Ball</th>
                    <th>O'tkazgan</th>
                    <th>Vaqt (ms)</th>
                    <th>Shubhali</th>
                    <th>Sana</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {atResults.map((attempt) => (
                    <tr key={attempt.id}>
                      <td><Text size="sm" fw={500}>{attempt.username || attempt.user}</Text></td>
                      <td><Text size="sm">{attempt.title_title || '—'}</Text></td>
                      <td><Text size="sm" fw={700}>{attempt.points_awarded}</Text></td>
                      <td>
                        {attempt.passed ? (
                          <Badge color="green" variant="light">Ha</Badge>
                        ) : (
                          <Badge color="gray" variant="light">Yo'q</Badge>
                        )}
                      </td>
                      <td><Text size="sm" c="dimmed">{attempt.elapsed_ms || '—'}</Text></td>
                      <td>
                        <ActionIcon
                          variant="subtle"
                          color={attempt.is_suspicious ? 'red' : 'gray'}
                          onClick={() => handleToggleSuspicious(attempt)}
                          loading={busyId === attempt.id}
                          title={attempt.is_suspicious ? 'Belgini olib tashlash' : 'Shubhali deb belgilash'}
                        >
                          <i className={`bi ${attempt.is_suspicious ? 'bi-exclamation-triangle-fill' : 'bi-exclamation-triangle'}`} />
                        </ActionIcon>
                      </td>
                      <td>
                        <Text size="xs" c="dimmed">{formatDateTime(attempt.finished_at || attempt.started_at)}</Text>
                      </td>
                      <td>
                        <ActionIcon
                          variant="subtle"
                          color="red"
                          onClick={() => setDeleteTarget({ kind: 'attempt', item: attempt })}
                          title="O'chirish"
                        >
                          <i className="bi bi-trash" />
                        </ActionIcon>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {totalPages > 1 ? (
            <Group justify="center" mt="md">
              <Pagination
                total={totalPages}
                value={page}
                onChange={setPage}
                size="sm"
              />
            </Group>
          ) : null}
        </Tabs.Panel>

        <Tabs.Panel value="prizes" pt="md">
          <Group align="flex-end" mb="md" wrap="wrap">
            <NumberInput
              label="Yil"
              value={prizeYear}
              onChange={(value) => {
                setPrizeYear(String(value || new Date().getFullYear()))
                setPage(1)
              }}
              min={2024}
              max={2100}
              w={120}
            />
            <form onSubmit={handleCreatePrize} style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-end' }}>
              <NumberInput
                label="Oy"
                value={prizeForm.month}
                onChange={(value) => setPrizeForm({ ...prizeForm, month: value })}
                min={1}
                max={12}
                w={80}
                required
              />
              <TextInput
                label="Foydalanuvchi ID"
                placeholder="1"
                value={prizeForm.user}
                onChange={(event) => setPrizeForm({ ...prizeForm, user: event.currentTarget.value })}
                required
                w={120}
              />
              <NumberInput
                label="Ball"
                value={prizeForm.points}
                onChange={(value) => setPrizeForm({ ...prizeForm, points: value })}
                min={0}
                w={90}
              />
              <NumberInput
                label="Kun"
                value={prizeForm.days}
                onChange={(value) => setPrizeForm({ ...prizeForm, days: value })}
                min={1}
                w={80}
              />
              <button type="submit" className="admin-btn admin-btn-primary" disabled={prizeSaving}>
                {prizeSaving ? 'Qo\'shilmoqda…' : "Qo'shish"}
              </button>
            </form>
          </Group>

          {loading ? (
            <div className="admin-loading"><Loader /></div>
          ) : prResults.length === 0 ? (
            <EmptyState
              icon="bi-gift"
              title="Sovrin yo'q"
              description="Oylik sovrinlar shu yilda hali yozilmagan. Yuqoridan qo'shing yoki 'Oylik sovrinni berish' tugmasini bosing."
            />
          ) : (
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Yil</th>
                    <th>Oy</th>
                    <th>Foydalanuvchi</th>
                    <th>Ball</th>
                    <th>Kun</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {prResults.map((prize) => (
                    <tr key={prize.id}>
                      <td><Text size="sm" fw={500}>{prize.year}</Text></td>
                      <td>
                        <Text size="sm">{monthNames[(prize.month || 1) - 1] || prize.month}</Text>
                      </td>
                      <td><Text size="sm" fw={600}>{prize.username || prize.user}</Text></td>
                      <td><Text size="sm">{prize.points}</Text></td>
                      <td><Text size="sm">{prize.days}</Text></td>
                      <td>
                        <ActionIcon
                          variant="subtle"
                          color="red"
                          onClick={() => setDeleteTarget({ kind: 'prize', item: prize })}
                          title="O'chirish"
                        >
                          <i className="bi bi-trash" />
                        </ActionIcon>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {totalPages > 1 ? (
            <Group justify="center" mt="md">
              <Pagination
                total={totalPages}
                value={page}
                onChange={setPage}
                size="sm"
              />
            </Group>
          ) : null}
        </Tabs.Panel>
      </Tabs>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={deleteTarget?.kind === 'prize' ? 'Sovrinni o\'chirish' : 'Urinishni o\'chirish'}
        message={
          deleteTarget?.kind === 'prize'
            ? `${deleteTarget?.item?.year || ''} yil ${deleteTarget?.item?.month || ''}-oy sovrini o'chiriladi.`
            : 'Bu o\'yin urinishi o\'chiriladi. Ball va statistika qayta hisoblanmaydi.'
        }
        confirmLabel="O'chirish"
        danger
        loading={busy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={deleteTarget?.kind === 'prize' ? handleDeletePrize : handleDeleteAttempt}
      />
    </Stack>
  )
}
