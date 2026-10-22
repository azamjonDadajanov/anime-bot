import { Badge, Group, Loader, Select, Stack, Text } from '@mantine/core'
import { useCallback, useEffect, useState } from 'react'
import { adminLogApi } from '../api/adminApi'
import { formatDateTime } from '../../utils/dates'
import { EmptyState, ErrorAlert, PaginationBar, SectionHeading } from '../components/adminShared'
import { formatError } from '../utils/formUtils'

const LEVEL_OPTIONS = [
  { value: '', label: 'Barcha darajalar' },
  { value: 'DEBUG', label: 'Debug' },
  { value: 'INFO', label: 'Info' },
  { value: 'WARNING', label: 'Ogohlantirish' },
  { value: 'ERROR', label: 'Xato' },
  { value: 'CRITICAL', label: 'Kritik' },
]

const LEVEL_COLORS = {
  DEBUG: 'gray',
  INFO: 'blue',
  WARNING: 'yellow',
  ERROR: 'red',
  CRITICAL: 'red',
}

export default function LogsPage() {
  const [level, setLevel] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ results: [], count: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = { page, page_size: 30 }
      if (level) params.level = level
      const result = await adminLogApi.list(params)
      setData(result)
    } catch (err) {
      setError(formatError(err, 'Jurnallarni yuklashda xatolik.'))
    } finally {
      setLoading(false)
    }
  }, [page, level])

  useEffect(() => {
    load()
  }, [load])

  const results = data.results || []
  const count = data.count || 0
  const totalPages = Math.max(1, Math.ceil(count / 30))

  return (
    <Stack gap="lg">
      <SectionHeading
        title="Jurnallar"
        description="Bot va API xatolari, ogohlantirishlar."
        actions={
          <Select
            data={LEVEL_OPTIONS}
            value={level}
            onChange={(value) => {
              setLevel(value || '')
              setPage(1)
            }}
            clearable
            w={200}
            placeholder="Daraja"
          />
        }
      />
      <ErrorAlert>{error}</ErrorAlert>

      {loading ? (
        <div className="admin-loading"><Loader /></div>
      ) : results.length === 0 ? (
        <EmptyState icon="bi-journal-text" title="Jurnal yo'q" />
      ) : (
        <Stack gap="xs">
          {results.map((entry) => (
            <div key={entry.id} className="admin-log-row">
              <Group justify="space-between" align="flex-start">
                <Group gap="xs">
                  <Badge size="sm" color={LEVEL_COLORS[entry.level] || 'gray'} variant="light">
                    {entry.level}
                  </Badge>
                  <Text size="xs" c="dimmed" style={{ fontFamily: 'monospace' }}>
                    {entry.logger}
                  </Text>
                </Group>
                <Text size="xs" c="dimmed">
                  {formatDateTime(entry.created_at)}
                </Text>
              </Group>
              <Text size="sm" mt={4}>{entry.message}</Text>
              {entry.telegram_id ? (
                <Text size="xs" c="dimmed">tg: {entry.telegram_id}</Text>
              ) : null}
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
    </Stack>
  )
}
