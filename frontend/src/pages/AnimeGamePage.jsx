import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Progress,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from '@mantine/core'
import { gameApi } from '../apis/api'

const typeLabels = {
  anime: 'Anime',
  series: 'Serial',
  movie: 'Kino',
  manga: 'Manga',
}

function errorText(error) {
  const data = error.response?.data
  if (!data) return 'Server bilan bog\'lanishda xatolik yuz berdi.'
  if (typeof data.detail === 'string') return data.detail
  return Object.values(data).flat().map(String).join(' ')
}

export function AnimeGamePage() {
  const [status, setStatus] = useState(null)
  const [titles, setTitles] = useState(null)
  const [leaderboard, setLeaderboard] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [quiz, setQuiz] = useState(null)
  const [answers, setAnswers] = useState([])
  const [current, setCurrent] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(null)
  const startedAtRef = useRef(0)

  const loadAll = useCallback(() => {
    setLoading(true)
    setError('')
    Promise.all([gameApi.status(), gameApi.titles(), gameApi.leaderboard()])
      .then(([statusData, titlesData, board]) => {
        setStatus(statusData)
        setTitles(titlesData)
        setLeaderboard(board)
      })
      .catch((requestError) => setError(errorText(requestError)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  function startQuiz(titleId) {
    setError('')
    setNotice('')
    gameApi
      .startQuiz(titleId)
      .then((data) => {
        setQuiz(data)
        setAnswers(new Array(data.questions.length).fill(null))
        setCurrent(0)
        setResult(null)
        startedAtRef.current = Date.now()
      })
      .catch((requestError) => {
        const message = errorText(requestError)
        setError(message)
        loadAll()
      })
  }

  function selectAnswer(index) {
    setAnswers((prev) => {
      const next = [...prev]
      next[current] = index
      return next
    })
  }

  function goNext() {
    setCurrent((prev) => Math.min(prev + 1, quiz.questions.length - 1))
  }

  function goPrev() {
    setCurrent((prev) => Math.max(prev - 1, 0))
  }

  function submitQuiz() {
    if (answers.some((value) => value === null)) {
      setError('Barcha savollarga javob bering.')
      return
    }
    setSubmitting(true)
    setError('')
    const elapsedMs = Date.now() - startedAtRef.current
    gameApi
      .submitQuiz({ attemptId: quiz.attempt_id, answers, elapsedMs })
      .then((data) => {
        setResult(data)
        setQuiz(null)
        setNotice(
          data.verified
            ? 'Tabriklaymiz! Bu anime tasdiqlandi.'
            : "Afsus, o'tib bo'lmadi. Bu anime uchun qayta urinish yo'q.",
        )
        loadAll()
      })
      .catch((requestError) => setError(errorText(requestError)))
      .finally(() => setSubmitting(false))
  }

  if (loading) {
    return (
      <main className="dashboard-page">
        <div className="page-loader"><Loader /></div>
      </main>
    )
  }

  if (quiz) {
    const question = quiz.questions[current]
    const answered = answers.filter((value) => value !== null).length
    const total = quiz.questions.length

    return (
      <main className="dashboard-page">
        <Stack gap="lg" maw={720} mx="auto">
          <div>
            <Text className="eyebrow">O'YIN · {quiz.title.title}</Text>
            <Title order={1} className="home-hero-title">
              Savol {current + 1} / {total}
            </Title>
          </div>

          <Progress value={((current + 1) / total) * 100} size="lg" radius="xl" />

          <Card withBorder padding="xl" radius="md">
            <Text fw={600} size="lg" mb="md">{question.text}</Text>
            <Stack gap="sm">
              {question.choices.map((choice, index) => (
                <Button
                  key={choice + String(index)}
                  variant={answers[current] === index ? 'filled' : 'outline'}
                  justify="flex-start"
                  onClick={() => selectAnswer(index)}
                  fullWidth
                >
                  {choice}
                </Button>
              ))}
            </Stack>
          </Card>

          <Group justify="space-between">
            <Button variant="default" disabled={current === 0} onClick={goPrev}>
              Orqaga
            </Button>
            <Text size="sm" c="dimmed">{answered} / {total} javob berildi</Text>
            {current < total - 1 ? (
              <Button disabled={answers[current] === null} onClick={goNext}>
                Keyingi
              </Button>
            ) : (
              <Button
                color="green"
                loading={submitting}
                disabled={answers.some((value) => value === null)}
                onClick={submitQuiz}
              >
                Yakunlash
              </Button>
            )}
          </Group>

          <Text size="xs" c="dimmed">
            Javoblar keyin ko'rsatilmaydi — bu yagona urinish.
          </Text>
        </Stack>
      </main>
    )
  }

  return (
    <main className="dashboard-page">
      <section className="home-hero">
        <div className="home-hero-copy">
          <Text className="eyebrow">ANIME REYTING O'YINI</Text>
          <Title order={1} className="home-hero-title">O'yin</Title>
          <Text c="dimmed" className="home-hero-text">
            Botda ko'rgan animearingiz bo'yicha savollarga javob bering, ball to'plang va
            reytingda yuqoriga chiqing. O'tgan animelar uchun rozilik nishoni olasiz.
          </Text>
          <ul className="home-hero-pills">
            <li><i className="bi bi-trophy" aria-hidden="true" /> {status?.points ?? 0} ball</li>
            <li><i className="bi bi-star" aria-hidden="true" /> {status?.name ?? '—'} (Lv.{status?.level ?? 1})</li>
            <li><i className="bi bi-patch-check" aria-hidden="true" /> {status?.verified_count ?? 0} tasdiqlangan</li>
            <li><i className="bi bi-ui-checks" aria-hidden="true" /> {status?.attempts ?? 0} urinish</li>
          </ul>
        </div>
      </section>

      {error && <Alert color="red" mb="lg">{error}</Alert>}
      {notice && <Alert color="green" mb="lg" onClose={() => setNotice('')} withCloseButton>{notice}</Alert>}

      {result && (
        <Alert color={result.verified ? 'green' : 'orange'} mb="lg">
          <Text fw={700}>
            {result.correct} / {result.total} to'g'ri javob
            {result.verified ? ' — tasdiqlandi!' : " — o'tib bo'lmadi."}
          </Text>
          <Text size="sm">
            +{result.points_awarded} ball. Javoblar ko'rsatilmaydi.
          </Text>
        </Alert>
      )}

      <section style={{ marginTop: '2rem' }}>
        <Text component="h2" className="rail-title" mb="md">Mavjud animelar</Text>
        {!titles?.unlocked?.length ? (
          <div className="empty-state">
            <i className="bi bi-lock" aria-hidden="true" />
            <Text fw={600}>Hozircha o'yin uchun anime yo'q</Text>
            <Text size="sm" c="dimmed">
              Botda kamida {titles?.min_parts ?? 3} ta qism ochilgan animelar shu yerda paydo bo'ladi.
            </Text>
          </div>
        ) : (
          <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="md">
            {titles.unlocked.map((item) => (
              <Card key={item.id} withBorder padding="lg" radius="md">
                <Group justify="space-between" mb="xs">
                  <Text fw={600} lineClamp={1}>{item.title}</Text>
                  <Badge size="sm" variant="light">{typeLabels[item.type] || item.type}</Badge>
                </Group>
                <Text size="sm" c="dimmed" mb="md">
                  {item.points} ball · {item.bot_views} marta ochilgan
                </Text>
                <Button
                  fullWidth
                  disabled={!item.ready}
                  onClick={() => startQuiz(item.id)}
                >
                  {item.ready ? "Boshlash" : `Savollar tayyor emas (${item.questions}/5)`}
                </Button>
              </Card>
            ))}
          </SimpleGrid>
        )}
      </section>

      {titles?.verified?.length > 0 && (
        <section style={{ marginTop: '2.5rem' }}>
          <Text component="h2" className="rail-title" mb="md">Tasdiqlangan animelar</Text>
          <SimpleGrid cols={{ base: 2, sm: 3, md: 5 }} spacing="sm">
            {titles.verified.map((item) => (
              <Card key={item.id} withBorder padding="sm" radius="md">
                <Text size="sm" fw={600} lineClamp={1}>{item.title}</Text>
                <Badge size="xs" color="green" mt={4} variant="light">
                  +{item.points} ball
                </Badge>
              </Card>
            ))}
          </SimpleGrid>
        </section>
      )}

      {leaderboard?.results?.length > 0 && (
        <section style={{ marginTop: '2.5rem' }}>
          <Group justify="space-between" mb="md">
            <Text component="h2" className="rail-title">Reyting jadvali</Text>
            {leaderboard.own && (
              <Text size="sm" c="dimmed">
                Siz: {leaderboard.own.rank}-o'rin · {leaderboard.own.points} ball
              </Text>
            )}
          </Group>
          <Card withBorder padding="md" radius="md">
            <Stack gap="xs">
              {leaderboard.results.map((row) => (
                <Group key={row.user_id} justify="space-between">
                  <Group gap="xs">
                    <Badge size="sm" variant="light" color={row.rank <= 3 ? 'yellow' : 'gray'}>
                      #{row.rank}
                    </Badge>
                    <Text size="sm">{row.name}</Text>
                  </Group>
                  <Group gap="xs">
                    <Text size="sm" c="dimmed">{row.verified} tasdiq</Text>
                    <Text size="sm" fw={600}>{row.points} ball</Text>
                  </Group>
                </Group>
              ))}
            </Stack>
          </Card>
        </section>
      )}
    </main>
  )
}

export default AnimeGamePage
