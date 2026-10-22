import {
  ActionIcon,
  Badge,
  Checkbox,
  Group,
  Loader,
  Select,
  Stack,
  Tabs,
  Text,
  TextInput,
} from '@mantine/core'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { adminCommentsApi, adminRatingsApi } from '../api/adminApi'
import { adminPath } from '../adminBase'
import { CrownIcon } from '../../components/PremiumBadge'
import { formatDateTime } from '../../utils/dates'
import {
  ConfirmDialog,
  EmptyState,
  ErrorAlert,
  PaginationBar,
  SectionHeading,
  SuccessAlert,
} from '../components/adminShared'
import { formatError } from '../utils/formUtils'

const PAGE_SIZE = 20

const SOURCE_OPTIONS = [
  { value: '', label: 'Barchasi' },
  { value: 'site', label: 'Sayt' },
  { value: 'bot', label: 'Bot' },
]

const SCORE_OPTIONS = [
  { value: '', label: 'Barchasi' },
  ...Array.from({ length: 10 }, (_, index) => ({
    value: String(index + 1),
    label: String(index + 1),
  })),
]

function authorLabel(row) {
  return row.author?.display_name || row.author?.username || '—'
}

function AuthorCell({ row }) {
  return (
    <Group gap={6} wrap="nowrap">
      <Text size="sm" fw={500} lineClamp={1}>{authorLabel(row)}</Text>
      {row.author?.is_premium ? (
        <Badge size="xs" color="yellow" variant="light" leftSection={<CrownIcon size={11} />}>
          Obunachi
        </Badge>
      ) : null}
    </Group>
  )
}

function MediaCell({ row }) {
  return (
    <div>
      <Text
        size="sm"
        component={Link}
        to={adminPath(`/media/${row.title_slug}`)}
        style={{ color: 'inherit' }}
      >
        {row.title_name || row.title_slug}
      </Text>
      <Text size="xs" c="dimmed">#{row.title}</Text>
    </div>
  )
}

/** Izohlar tab: the shared site/bot comment table, one delete per row. */
function CommentsTab() {
  const [search, setSearch] = useState('')
  const [title, setTitle] = useState('')
  const [source, setSource] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ results: [], count: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [bulkOpen, setBulkOpen] = useState(false)
  const [selected, setSelected] = useState([])
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = { page, page_size: PAGE_SIZE }
      if (search) params.search = search
      if (title) params.title = title
      if (source) params.source = source
      setData(await adminCommentsApi.list(params))
    } catch (err) {
      setError(formatError(err, 'Izohlarni yuklashda xatolik.'))
    } finally {
      setLoading(false)
    }
  }, [page, search, title, source])

  useEffect(() => {
    load()
  }, [load])

  const results = data.results || []
  const count = data.count || 0
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE))
  const allChecked = results.length > 0 && results.every((row) => selected.includes(row.id))

  function toggle(id) {
    setSelected((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]))
  }

  function toggleAll() {
    setSelected(allChecked ? [] : results.map((row) => row.id))
  }

  async function removeOne() {
    if (!deleteTarget) return
    setBusy(true)
    setError(null)
    try {
      await adminCommentsApi.remove(deleteTarget.id)
      setSuccess('Izoh o\'chirildi.')
      setDeleteTarget(null)
      setSelected((prev) => prev.filter((item) => item !== deleteTarget.id))
      await load()
    } catch (err) {
      setError(formatError(err, 'Izohni o\'chirishda xatolik.'))
      setDeleteTarget(null)
    } finally {
      setBusy(false)
    }
  }

  async function removeBulk() {
    if (!selected.length) return
    setBusy(true)
    setError(null)
    try {
      const result = await adminCommentsApi.bulkDelete(selected)
      setSuccess(`${result.deleted || selected.length} ta izoh o'chirildi.`)
      setSelected([])
      setBulkOpen(false)
      await load()
    } catch (err) {
      setError(formatError(err, 'Izohlarni o\'chirishda xatolik.'))
      setBulkOpen(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Stack gap="md">
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>
      <Group align="flex-end">
        <TextInput
          label="Qidiruv"
          placeholder="Izoh matni yoki muallif"
          value={search}
          onChange={(event) => {
            setSearch(event.currentTarget.value)
            setPage(1)
          }}
          w={{ base: '100%', sm: 260 }}
        />
        <TextInput
          label="Media"
          placeholder="Slug yoki id"
          value={title}
          onChange={(event) => {
            setTitle(event.currentTarget.value)
            setPage(1)
          }}
          w={{ base: '100%', sm: 180 }}
        />
        <Select
          label="Manba"
          data={SOURCE_OPTIONS}
          value={source}
          onChange={(value) => {
            setSource(value || '')
            setPage(1)
          }}
          clearable
          w={140}
        />
        {selected.length > 0 && (
          <button type="button" className="admin-btn admin-btn-danger" onClick={() => setBulkOpen(true)}>
            <i className="bi bi-trash3" /> {selected.length} ta izohni o'chirish
          </button>
        )}
      </Group>

      {loading ? (
        <div className="admin-loading"><Loader /></div>
      ) : results.length === 0 ? (
        <EmptyState icon="bi-chat-left-text" title="Izoh topilmadi" />
      ) : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th style={{ width: 36 }}>
                  <Checkbox checked={allChecked} onChange={toggleAll} aria-label="Barchasini tanlash" />
                </th>
                <th>Izoh</th>
                <th>Media</th>
                <th>Qism</th>
                <th>Manba</th>
                <th>Muallif</th>
                <th>Sana</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {results.map((row) => (
                <tr key={row.id}>
                  <td>
                    <Checkbox
                      checked={selected.includes(row.id)}
                      onChange={() => toggle(row.id)}
                      aria-label={`Izoh #${row.id} ni tanlash`}
                    />
                  </td>
                  <td style={{ maxWidth: 340 }}>
                    <Text size="sm" lineClamp={2}>{row.body}</Text>
                  </td>
                  <td><MediaCell row={row} /></td>
                  <td>{row.part_number ? `${row.part_number}-qism` : '—'}</td>
                  <td>
                    <Badge size="xs" variant="light" color={row.source === 'bot' ? 'blue' : 'green'}>
                      {row.source === 'bot' ? 'Bot' : 'Sayt'}
                    </Badge>
                  </td>
                  <td><AuthorCell row={row} /></td>
                  <td>
                    <Text size="xs" c="dimmed">{formatDateTime(row.created_at)}</Text>
                  </td>
                  <td>
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      title="O'chirish"
                      onClick={() => setDeleteTarget(row)}
                    >
                      <i className="bi bi-trash3" />
                    </ActionIcon>
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
        title="Izohni o'chirish"
        message={`"${deleteTarget?.body || ''}" izohi butunlay o'chirilsinmi?`}
        confirmLabel="Ha, o'chirish"
        danger
        loading={busy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={removeOne}
      />

      <ConfirmDialog
        open={bulkOpen}
        title="Izohlarni o'chirish"
        message={`${selected.length} ta izoh butunlay o'chirilsinmi?`}
        confirmLabel="Ha, o'chirish"
        danger
        loading={busy}
        onCancel={() => setBulkOpen(false)}
        onConfirm={removeBulk}
      />
    </Stack>
  )
}

/** Baholar tab: every 1-10 score; removing one recomputes the average. */
function RatingsTab() {
  const [search, setSearch] = useState('')
  const [title, setTitle] = useState('')
  const [minScore, setMinScore] = useState('')
  const [maxScore, setMaxScore] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ results: [], count: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [selected, setSelected] = useState([])
  const [bulkOpen, setBulkOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = { page, page_size: PAGE_SIZE }
      if (search) params.search = search
      if (title) params.title = title
      if (minScore) params.min_score = minScore
      if (maxScore) params.max_score = maxScore
      setData(await adminRatingsApi.list(params))
    } catch (err) {
      setError(formatError(err, 'Baholarni yuklashda xatolik.'))
    } finally {
      setLoading(false)
    }
  }, [page, search, title, minScore, maxScore])

  useEffect(() => {
    load()
  }, [load])

  const results = data.results || []
  const count = data.count || 0
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE))
  const allChecked = results.length > 0 && results.every((row) => selected.includes(row.id))

  function toggle(id) {
    setSelected((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]))
  }

  function toggleAll() {
    setSelected(allChecked ? [] : results.map((row) => row.id))
  }

  async function removeOne() {
    if (!deleteTarget) return
    setBusy(true)
    setError(null)
    try {
      await adminRatingsApi.remove(deleteTarget.id)
      setSuccess("Baho o'chirildi, o'rtacha qayta hisoblandi.")
      setDeleteTarget(null)
      setSelected((prev) => prev.filter((item) => item !== deleteTarget.id))
      await load()
    } catch (err) {
      setError(formatError(err, "Baho o'chirishda xatolik."))
      setDeleteTarget(null)
    } finally {
      setBusy(false)
    }
  }

  async function removeBulk() {
    if (!selected.length) return
    setBusy(true)
    setError(null)
    try {
      const result = await adminRatingsApi.bulkDelete(selected)
      setSuccess(`${result.deleted || selected.length} ta baho o'chirildi.`)
      setSelected([])
      setBulkOpen(false)
      await load()
    } catch (err) {
      setError(formatError(err, 'Baholarni o\'chirishda xatolik.'))
      setBulkOpen(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Stack gap="md">
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>
      <Group align="flex-end">
        <TextInput
          label="Qidiruv"
          placeholder="Muallif yoki media"
          value={search}
          onChange={(event) => {
            setSearch(event.currentTarget.value)
            setPage(1)
          }}
          w={{ base: '100%', sm: 240 }}
        />
        <TextInput
          label="Media"
          placeholder="Slug yoki id"
          value={title}
          onChange={(event) => {
            setTitle(event.currentTarget.value)
            setPage(1)
          }}
          w={{ base: '100%', sm: 170 }}
        />
        <Select
          label="Min baho"
          data={SCORE_OPTIONS}
          value={minScore}
          onChange={(value) => {
            setMinScore(value || '')
            setPage(1)
          }}
          clearable
          w={110}
        />
        <Select
          label="Max baho"
          data={SCORE_OPTIONS}
          value={maxScore}
          onChange={(value) => {
            setMaxScore(value || '')
            setPage(1)
          }}
          clearable
          w={110}
        />
        {selected.length > 0 && (
          <button type="button" className="admin-btn admin-btn-danger" onClick={() => setBulkOpen(true)}>
            <i className="bi bi-trash3" /> {selected.length} ta bahoni o'chirish
          </button>
        )}
      </Group>

      {loading ? (
        <div className="admin-loading"><Loader /></div>
      ) : results.length === 0 ? (
        <EmptyState icon="bi-star" title="Baho topilmadi" />
      ) : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th style={{ width: 36 }}>
                  <Checkbox checked={allChecked} onChange={toggleAll} aria-label="Barchasini tanlash" />
                </th>
                <th>Baho</th>
                <th>Media</th>
                <th>Muallif</th>
                <th>Yaratilgan</th>
                <th>O'zgartirilgan</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {results.map((row) => (
                <tr key={row.id}>
                  <td>
                    <Checkbox
                      checked={selected.includes(row.id)}
                      onChange={() => toggle(row.id)}
                      aria-label={`Baho #${row.id} ni tanlash`}
                    />
                  </td>
                  <td>
                    <Badge color="yellow" variant="light" style={{ fontFamily: 'monospace' }}>
                      <i className="bi bi-star-fill" /> {row.score}/10
                    </Badge>
                  </td>
                  <td><MediaCell row={row} /></td>
                  <td><AuthorCell row={row} /></td>
                  <td>
                    <Text size="xs" c="dimmed">{formatDateTime(row.created_at)}</Text>
                  </td>
                  <td>
                    <Text size="xs" c="dimmed">{formatDateTime(row.updated_at)}</Text>
                  </td>
                  <td>
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      title="O'chirish"
                      onClick={() => setDeleteTarget(row)}
                    >
                      <i className="bi bi-trash3" />
                    </ActionIcon>
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
        title="Bahoni o'chirish"
        message={`${authorLabel(deleteTarget || {})} ning ${deleteTarget?.score ?? ''}/10 bahosi o'chirilsinmi? O'rtacha qayta hisoblanadi.`}
        confirmLabel="Ha, o'chirish"
        danger
        loading={busy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={removeOne}
      />

      <ConfirmDialog
        open={bulkOpen}
        title="Baholarni o'chirish"
        message={`${selected.length} ta baho o'chirilsinmi? O'rtachalar qayta hisoblanadi.`}
        confirmLabel="Ha, o'chirish"
        danger
        loading={busy}
        onCancel={() => setBulkOpen(false)}
        onConfirm={removeBulk}
      />
    </Stack>
  )
}

/**
 * Community moderation: the one table behind the site comments, the bot's
 * 💬 flow and the 1-10 scores — one screen, two tabs.
 */
export default function CommentsPage() {
  return (
    <Stack gap="lg">
      <SectionHeading
        title="Izohlar va baholar"
        description="Sayt va botdagi bitta jadval: qidiruv, manba bo'yicha filtr, o'chirish."
      />
      <Tabs defaultValue="comments" radius="md">
        <Tabs.List>
          <Tabs.Tab value="comments" leftSection={<i className="bi bi-chat-left-text" />}>
            Izohlar
          </Tabs.Tab>
          <Tabs.Tab value="ratings" leftSection={<i className="bi bi-star" />}>
            Baholar (1-10)
          </Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="comments" pt="lg">
          <CommentsTab />
        </Tabs.Panel>
        <Tabs.Panel value="ratings" pt="lg">
          <RatingsTab />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  )
}
