import { Group, Loader, Select, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { useEffect, useMemo, useState } from 'react'
import { adminDashboardApi, adminIncomeApi } from '../api/adminApi'
import { ErrorAlert, PLAN_LABELS, SectionHeading, StatCard } from '../components/adminShared'
import { formatError } from '../utils/formUtils'

const CURRENT_YEAR = String(new Date().getFullYear())

export default function DashboardPage() {
  const [stats, setStats] = useState(null)
  const [monthly, setMonthly] = useState(null)
  const [year, setYear] = useState(CURRENT_YEAR)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    Promise.all([
      adminDashboardApi.stats(),
      adminIncomeApi.monthly(year),
    ])
      .then(([statsData, monthlyData]) => {
        if (!active) return
        setStats(statsData)
        setMonthly(monthlyData)
        setError(null)
      })
      .catch((err) => {
        if (active) setError(formatError(err, 'Statistika yuklashda xatolik.'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [year])

  const years = useMemo(
    () => Array.from({ length: 5 }, (_, i) => String(Number(CURRENT_YEAR) - i)),
    [],
  )

  if (loading && !stats) {
    return <div className="admin-loading"><Loader size="lg" /></div>
  }

  return (
    <Stack gap="lg">
      <SectionHeading
        title="Boshqaruv paneli"
        description="Platformaning umumiy ko'rsatkichlari va oylik tushumlar."
        actions={
          <Select
            data={years}
            value={year}
            onChange={(value) => value && setYear(value)}
            w={120}
            allowDeselect={false}
          />
        }
      />
      <ErrorAlert>{error}</ErrorAlert>

      {stats ? (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
          <StatCard
            title="Foydalanuvchilar"
            value={stats.users.total}
            icon="bi-people"
            color="blue"
            hint={`Faol: ${stats.users.active_30d} · Bloklangan: ${stats.users.blocked}`}
          />
          <StatCard
            title="Medialar"
            value={stats.media.titles}
            icon="bi-film"
            color="violet"
            hint={`Qismlar: ${stats.media.parts} · Fayllar: ${stats.media.files}`}
          />
          <StatCard
            title="Oylik tushum"
            value={`${Number(stats.income.month_total || 0).toLocaleString()} so'm`}
            icon="bi-cash-coin"
            color="green"
            hint={`Arizalar: ${stats.income.month_count}`}
          />
          <StatCard
            title="Kutilayotgan arizalar"
            value={stats.subscriptions.pending}
            icon="bi-ticket-perforated"
            color="orange"
            hint={`Tasdiqlangan: ${stats.subscriptions.approved}`}
          />
        </SimpleGrid>
      ) : null}

      {stats ? (
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
          <div className="admin-panel">
            <Title order={4} mb="sm">Kontent turlari</Title>
            <Stack gap="xs">
              {Object.entries(stats.media.by_type || {}).map(([type, total]) => (
                <Group key={type} justify="space-between">
                  <Text size="sm">{type}</Text>
                  <Text size="sm" fw={600}>{total}</Text>
                </Group>
              ))}
              {!Object.keys(stats.media.by_type || {}).length ? (
                <Text c="dimmed" size="sm">Hozircha media yo'q.</Text>
              ) : null}
            </Stack>
          </div>
          <div className="admin-panel">
            <Title order={4} mb="sm">Broadcast va kanallar</Title>
            <Stack gap="xs">
              <Group justify="space-between">
                <Text size="sm">Jami broadcast</Text>
                <Text size="sm" fw={600}>{stats.broadcasts.total}</Text>
              </Group>
              <Group justify="space-between">
                <Text size="sm">Faol broadcast</Text>
                <Text size="sm" fw={600}>{stats.broadcasts.running}</Text>
              </Group>
              <Group justify="space-between">
                <Text size="sm">Kanallar</Text>
                <Text size="sm" fw={600}>{stats.channels.total}</Text>
              </Group>
              <Group justify="space-between">
                <Text size="sm">Faol obunalar</Text>
                <Text size="sm" fw={600}>{stats.subscriptions.active}</Text>
              </Group>
              {Object.entries(stats.subscriptions.by_plan || {}).map(([planKey, total]) => (
                <Group key={planKey} justify="space-between">
                  <Text size="sm">{PLAN_LABELS[planKey] || planKey}</Text>
                  <Text size="sm" fw={600}>{total}</Text>
                </Group>
              ))}
            </Stack>
          </div>
        </SimpleGrid>
      ) : null}

      {monthly ? (
        <div className="admin-panel">
          <Title order={4} mb="sm">{monthly.year}-yil tushumlari</Title>
          <Text size="sm" c="dimmed" mb="md">
            Jami: {Number(monthly.total || 0).toLocaleString()} so'm ·
            O'rtacha oylik: {Number(monthly.average_monthly || 0).toLocaleString()} so'm
          </Text>
          <div className="admin-month-bars">
            {monthly.months.map((item) => {
              const max = Math.max(...monthly.months.map((m) => Number(m.total) || 0), 1)
              const width = Math.round(((Number(item.total) || 0) / max) * 100)
              return (
                <div key={item.label} className="admin-month-row">
                  <span className="admin-month-label">{item.label}</span>
                  <div className="admin-month-track">
                    <div className="admin-month-fill" style={{ width: `${width}%` }} />
                  </div>
                  <span className="admin-month-value">
                    {Number(item.total || 0).toLocaleString()}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      ) : null}
    </Stack>
  )
}
