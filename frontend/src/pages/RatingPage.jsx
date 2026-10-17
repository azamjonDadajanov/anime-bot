import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Stack,
  Text,
  Title,
} from '@mantine/core'
import { Link } from 'react-router-dom'
import { gameApi } from '../apis/api'

function errorText(error) {
  const data = error.response?.data
  if (!data) return 'Server bilan bog\'lanishda xatolik yuz berdi.'
  if (typeof data.detail === 'string') return data.detail
  return Object.values(data).flat().map(String).join(' ')
}

export function RatingPage() {
  const [board, setBoard] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const ownRef = useRef(null)

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    gameApi.leaderboard(100)
      .then(setBoard)
      .catch((requestError) => setError(errorText(requestError)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  function scrollToOwn() {
    ownRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  if (loading) {
    return (
      <main className="dashboard-page">
        <div className="page-loader"><Loader /></div>
      </main>
    )
  }

  const own = board?.own
  const results = board?.results || []

  return (
    <main className="dashboard-page">
      <section className="home-hero">
        <div className="home-hero-copy">
          <Text className="eyebrow">ANIME REYTING</Text>
          <Title order={1} className="home-hero-title">Reyting jadvali</Title>
          <Text c="dimmed" className="home-hero-text">
            O'yinda ball to'plang, reytingda yuqoriga chiqing. Oyning eng faol
            o'yinchisi 1 oylik obuna yutadi.
          </Text>
          <ul className="home-hero-pills">
            <li><i className="bi bi-trophy" aria-hidden="true" /> Sizning balingiz: {own?.points ?? 0}</li>
            <li><i className="bi bi-star" aria-hidden="true" /> Lv.{own?.level ?? 1} · {own?.name || '—'}</li>
            <li><i className="bi bi-bar-chart" aria-hidden="true" /> {own ? `${own.rank}-o'rin` : '—'}</li>
          </ul>
          <Group mt="md">
            <Button
              component={Link}
              to="/game"
              size="md"
              leftSection={<i className="bi bi-controller" aria-hidden="true" />}
            >
              O'yin o'ynash
            </Button>
            <Button
              variant="light"
              size="md"
              leftSection={<i className="bi bi-person-badge" aria-hidden="true" />}
              onClick={scrollToOwn}
              disabled={!own}
            >
              O'z reytingimni ko'rish
            </Button>
          </Group>
        </div>
      </section>

      {error && <Alert color="red" mb="lg">{error}</Alert>}

      {own && (
        <Card withBorder padding="lg" radius="md" mb="lg">
          <Group justify="space-between">
            <Group gap="sm">
              <Badge size="lg" color="yellow" variant="filled">#{own.rank}</Badge>
              <div>
                <Text fw={700}>Sizning reytingingiz</Text>
                <Text size="sm" c="dimmed">Lv.{own.level} · {own.name || 'o\'yinchi'}</Text>
              </div>
            </Group>
            <Text fw={700} size="xl">{own.points} ball</Text>
          </Group>
        </Card>
      )}

      {results.length === 0 ? (
        <div className="empty-state">
          <i className="bi bi-trophy" aria-hidden="true" />
          <Text fw={600}>Hali reyting yo'q</Text>
          <Text size="sm" c="dimmed">Birinchi bo'lib o'yinda ball to'plang.</Text>
        </div>
      ) : (
        <Card withBorder padding="md" radius="md">
          <Stack gap="xs">
            {results.map((row) => (
              <div
                key={row.user_id}
                ref={own && row.rank === own.rank ? ownRef : undefined}
              >
                <Group justify="space-between">
                  <Group gap="xs">
                    <Badge size="sm" variant="light" color={row.rank <= 3 ? 'yellow' : 'gray'}>
                      #{row.rank}
                    </Badge>
                    <Text size="sm">{row.name}</Text>
                    {own && row.rank === own.rank && (
                      <Badge size="xs" variant="outline" color="blue">siz</Badge>
                    )}
                  </Group>
                  <Group gap="xs">
                    <Text size="sm" c="dimmed">{row.verified} tasdiq</Text>
                    <Text size="sm" fw={600}>{row.points} ball</Text>
                  </Group>
                </Group>
              </div>
            ))}
          </Stack>
        </Card>
      )}
    </main>
  )
}

export default RatingPage
