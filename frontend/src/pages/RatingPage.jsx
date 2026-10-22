import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Loader } from '@mantine/core'
import { Link } from 'react-router-dom'
import { gameApi } from '../apis/api'
import PremiumBadge from '../components/PremiumBadge'

function errorText(error) {
  const data = error.response?.data
  if (!data) return "Server bilan bog'lanishda xatolik yuz berdi."
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
        <div className="page-loader"><Loader size="sm" /></div>
      </main>
    )
  }

  const own = board?.own
  const results = board?.results || []

  return (
    <main className="dashboard-page">
      <section className="rating-hero">
        <div className="rating-copy">
          <span className="eyebrow">Anime reyting o&apos;yini</span>
          <h1 className="rating-title">
            Reyting <em>jadvali</em>
          </h1>
          <p className="rating-text">
            O&apos;yinda ball to&apos;plang, reytingda yuqoriga chiqing. Oyning
            eng faol o&apos;yinchisi 1 oylik obunani yutadi.
          </p>
          <div className="rating-actions">
            <Button
              component={Link}
              to="/game"
              size="md"
              leftSection={<i className="bi bi-controller" aria-hidden="true" />}
            >
              O&apos;yin o&apos;ynash
            </Button>
            <Button
              variant="default"
              size="md"
              leftSection={<i className="bi bi-person-badge" aria-hidden="true" />}
              onClick={scrollToOwn}
              disabled={!own}
            >
              O&apos;z reytingim
            </Button>
          </div>
        </div>

        <div className="rating-stats">
          <div className="rating-stat">
            <b>{own?.points ?? 0}</b>
            <span>Ball</span>
          </div>
          <div className="rating-stat">
            <b>{own?.rank ? `#${own.rank}` : '—'}</b>
            <span>O&apos;rin</span>
          </div>
          <div className="rating-stat">
            <b>Lv.{own?.level ?? 1}</b>
            <span>{own?.name || "O'yinchi"}</span>
          </div>
        </div>
      </section>

      {error && <Alert color="red" mb="lg">{error}</Alert>}

      {own && (
        <div className="rating-own">
          <span>
            <b>#{own.rank}</b> · {own.points} ball {own.is_premium && <PremiumBadge compact />}
          </span>
          <span>Lv.{own.level} · {own.name || "o'yinchi"}</span>
          <span>Sizning natijangiz</span>
        </div>
      )}

      {results.length === 0 ? (
        <div className="empty-state">
          <i className="bi bi-trophy" aria-hidden="true" />
          <h2>Hali reyting yo&apos;q</h2>
          <p>Birinchi bo&apos;lib o&apos;yinda ball to&apos;plang va jadvalni boshlang.</p>
          <Link className="ac-btn ac-btn-ghost" to="/game">O&apos;yinni boshlash</Link>
        </div>
      ) : (
        <section className="leaderboard" aria-label="Reyting jadvali">
          <div className="leaderboard-head" aria-hidden="true">
            <span>#</span>
            <span>O&apos;yinchi</span>
            <span style={{ textAlign: 'right' }}>Tasdiq</span>
            <span style={{ textAlign: 'right' }}>Ball</span>
          </div>
          {results.map((row) => (
            <div
              className={`leaderboard-row${own && row.rank === own.rank ? ' is-own' : ''}`}
              key={row.user_id}
              ref={own && row.rank === own.rank ? ownRef : undefined}
            >
              <span className={`lb-rank${row.rank === 1 ? ' is-top' : ''}${row.rank > 1 && row.rank <= 3 ? ' is-second' : ''}`}>
                {row.rank}
              </span>
              <span className="lb-name">
                {row.name}
                {row.is_premium && <PremiumBadge compact />}
                {own && row.rank === own.rank && <span className="you">siz</span>}
              </span>
              <span className="lb-cell">{row.verified} tasdiq</span>
              <span className="lb-cell lb-points">{row.points} ball</span>
            </div>
          ))}
        </section>
      )}
    </main>
  )
}

export default RatingPage
