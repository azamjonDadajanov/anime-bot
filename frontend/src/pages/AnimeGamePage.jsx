import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Loader } from '@mantine/core'
import { Link } from 'react-router-dom'
import { gameApi } from '../apis/api'
import SectionHead from '../components/SectionHead'
import { typeLabel } from '../mediaMeta'

function errorText(error) {
  const data = error.response?.data
  if (!data) return "Server bilan bog'lanishda xatolik yuz berdi."
  if (typeof data.detail === 'string') return data.detail
  return Object.values(data).flat().map(String).join(' ')
}

const CHOICE_KEYS = ['A', 'B', 'C', 'D', 'E']

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
        setError(errorText(requestError))
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
        <div className="page-loader"><Loader size="sm" /></div>
      </main>
    )
  }

  if (quiz) {
    const question = quiz.questions[current]
    const answered = answers.filter((value) => value !== null).length
    const total = quiz.questions.length

    return (
      <main className="dashboard-page">
        <div className="quiz-shell">
          <div className="quiz-head">
            <span className="eyebrow">O&apos;yin · {quiz.title.title}</span>
            <h1>
              Savol {current + 1} <span style={{ opacity: 0.4 }}>/ {total}</span>
            </h1>
            <div className="quiz-progress">
              <span className="count">{answered} / {total} javob</span>
              <div className="bar">
                <span style={{ width: `${((current + 1) / total) * 100}%` }} />
              </div>
            </div>
          </div>

          <div className="quiz-card">
            <p className="quiz-question">{question.text}</p>
            <div className="quiz-choices">
              {question.choices.map((choice, index) => (
                <button
                  key={choice + String(index)}
                  className={`quiz-choice${answers[current] === index ? ' is-selected' : ''}`}
                  type="button"
                  aria-pressed={answers[current] === index}
                  onClick={() => selectAnswer(index)}
                >
                  <span className="key" aria-hidden="true">{CHOICE_KEYS[index] || index + 1}</span>
                  {choice}
                </button>
              ))}
            </div>
          </div>

          <div className="quiz-nav">
            <Button variant="default" disabled={current === 0} onClick={goPrev}>
              Orqaga
            </Button>
            <span className="quiz-note">Javoblar keyin ko&apos;rsatilmaydi — bu yagona urinish.</span>
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
          </div>
        </div>
      </main>
    )
  }

  return (
    <main className="dashboard-page">
      <section className="game-hero">
        <div className="game-copy">
          <span className="eyebrow">Anime reyting o&apos;yini</span>
          <h1 className="game-title">
            Bilimingizni <em>sinang.</em>
          </h1>
          <p className="game-text">
            Botda ko&apos;rgan animelaringiz bo&apos;yicha savollarga javob
            bering, ball to&apos;plang va reytingda yuqoriga chiqing. O&apos;tgan
            animelar uchun tasdiq nishoni olasiz.
          </p>
        </div>
        <div className="game-stats">
          <div className="game-stat">
            <b>{status?.points ?? 0}</b>
            <span>Ball</span>
          </div>
          <div className="game-stat">
            <b>Lv.{status?.level ?? 1}</b>
            <span>{status?.name ?? "O'yinchi"}</span>
          </div>
          <div className="game-stat">
            <b>{status?.verified_count ?? 0}</b>
            <span>Tasdiqlangan</span>
          </div>
          <div className="game-stat">
            <b>{status?.attempts ?? 0}</b>
            <span>Urinish</span>
          </div>
        </div>
      </section>

      {error && <Alert color="red" mb="md">{error}</Alert>}
      {notice && <Alert color="green" mb="md" onClose={() => setNotice('')} withCloseButton>{notice}</Alert>}

      {result && (
        <Alert color={result.verified ? 'green' : 'orange'} mb="md">
          <b>
            {result.correct} / {result.total} to&apos;g&apos;ri javob
            {result.verified ? ' — tasdiqlandi!' : " — o'tib bo'lmadi."}
          </b>
          <div>+{result.points_awarded} ball. Javoblar ko&apos;rsatilmaydi.</div>
        </Alert>
      )}

      <section className="game-section">
        <SectionHead
          index="01"
          title="Mavjud animelar"
          jp="挑戦"
          description="Botda kamida bir necha qismi ochilgan animelar o'yin uchun tayyor."
        />
        {!titles?.unlocked?.length ? (
          <div className="empty-state">
            <i className="bi bi-lock" aria-hidden="true" />
            <h2>Hozircha o&apos;yin uchun anime yo&apos;q</h2>
            <p>
              Botda kamida {titles?.min_parts ?? 3} marta ochilgan animelar shu
              yerda paydo bo&apos;ladi — qismlari shu sondan kam bo&apos;lganlar
              uchun barcha qismlar ochilganda kifoya.
            </p>
          </div>
        ) : (
          <div className="game-grid">
            {titles.unlocked.map((item) => (
              <article className="game-card" key={item.id}>
                <div className="game-card-top">
                  <h3>{item.title}</h3>
                  <span className="pill">{typeLabel(item)}</span>
                </div>
                <span className="game-card-meta">
                  {item.points} ball · {item.bot_views} marta ochilgan
                  {item.quiz_size ? ` · ${item.quiz_size} savol` : ''}
                </span>
                <Button
                  fullWidth
                  variant={item.ready ? 'filled' : 'default'}
                  disabled={!item.ready}
                  onClick={() => startQuiz(item.id)}
                >
                  {item.ready
                    ? 'Boshlash'
                    : `Savollar tayyor emas (${item.questions}/${item.quiz_size || 5})`}
                </Button>
              </article>
            ))}
          </div>
        )}
      </section>

      {titles?.verified?.length > 0 && (
        <section className="game-section">
          <SectionHead
            index="02"
            title="Tasdiqlangan animelar"
            jp="認定"
            description="Siz yutgan va tasdiqlangan hikoyalar."
          />
          <div className="verified-grid">
            {titles.verified.map((item) => (
              <div className="verified-card" key={item.id}>
                <b>{item.title}</b>
                <span>+{item.points} ball</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {leaderboard?.results?.length > 0 && (
        <section className="game-section">
          <SectionHead
            index="03"
            title="Reyting jadvali"
            jp="順位"
            href="/rating"
            linkLabel="To'liq jadval"
            description={leaderboard.own
              ? `Siz: ${leaderboard.own.rank}-o'rin · ${leaderboard.own.points} ball`
              : undefined}
          />
          <div className="leaderboard">
            <div className="leaderboard-head" aria-hidden="true">
              <span>#</span>
              <span>O&apos;yinchi</span>
              <span style={{ textAlign: 'right' }}>Tasdiq</span>
              <span style={{ textAlign: 'right' }}>Ball</span>
            </div>
            {leaderboard.results.slice(0, 8).map((row) => (
              <div className="leaderboard-row" key={row.user_id}>
                <span className={`lb-rank${row.rank === 1 ? ' is-top' : ''}${row.rank > 1 && row.rank <= 3 ? ' is-second' : ''}`}>
                  {row.rank}
                </span>
                <span className="lb-name">{row.name}</span>
                <span className="lb-cell">{row.verified}</span>
                <span className="lb-cell lb-points">{row.points}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="game-section">
        <Link className="section-link" to="/explore">
          Katalogga qaytish <i className="bi bi-arrow-right" aria-hidden="true" />
        </Link>
      </div>
    </main>
  )
}

export default AnimeGamePage
