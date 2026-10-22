import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { communityApi, hasAccessToken } from '../apis/api'
import { useAuth } from '../apis/useAuth'
import { formatDate } from '../utils/dates'
import PremiumBadge from './PremiumBadge'
import SectionHead from './SectionHead'

function errorText(error) {
  const data = error.response?.data
  if (!data) return "Server bilan bog'lanishda xatolik yuz berdi."
  if (typeof data.detail === 'string') return data.detail
  return Object.values(data).flat().map(String).join(' ')
}

function initialsOf(name) {
  return (name || '?').trim().slice(0, 1).toUpperCase()
}

/**
 * The comment thread of one title — the same table the Telegram bot and the
 * administrator panel read, so anything written here shows up there at once.
 * The 1-10 score lives apart from the text: one row per account, re-posting
 * replaces it instead of adding a second one.
 */
export default function CommentsSection({ slug }) {
  const { user } = useAuth()
  const signedIn = hasAccessToken()
  const [list, setList] = useState({ count: 0, page: 1, pages: 1, results: [] })
  const [summary, setSummary] = useState({ average: 0, count: 0, my_score: null })
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [body, setBody] = useState('')
  const [sending, setSending] = useState(false)
  const [scoreBusy, setScoreBusy] = useState(false)

  const load = useCallback(
    (nextPage = 1) => {
      setLoading(true)
      Promise.all([
        communityApi.comments({ title: slug, page: nextPage }),
        communityApi.rating(slug),
      ])
        .then(([comments, rating]) => {
          setList(comments)
          setSummary(rating)
          setPage(comments.page || nextPage)
          setError('')
        })
        .catch((requestError) => setError(errorText(requestError)))
        .finally(() => setLoading(false))
    },
    [slug],
  )

  useEffect(() => {
    load(1)
  }, [load])

  function submit(event) {
    event.preventDefault()
    const text = body.trim()
    if (!text || sending) return
    setSending(true)
    setNotice('')
    communityApi
      .createComment({ title: slug, body: text })
      .then((data) => {
        setBody('')
        setNotice(data.created ? 'Izohingiz qabul qilindi.' : 'Bu izoh allaqachon yuborilgan.')
        load(1)
      })
      .catch((requestError) => setError(errorText(requestError)))
      .finally(() => setSending(false))
  }

  function rate(score) {
    if (scoreBusy || score === summary.my_score) return
    setScoreBusy(true)
    communityApi
      .setRating(slug, score)
      .then(setSummary)
      .catch((requestError) => setError(errorText(requestError)))
      .finally(() => setScoreBusy(false))
  }

  function remove(id) {
    communityApi
      .deleteComment(id)
      .then(() => load(page))
      .catch((requestError) => setError(errorText(requestError)))
  }

  const average = Number(summary.average || 0)
  const shownAverage = average ? average.toFixed(1).replace(/\.0$/, '') : '—'
  const myScore = summary.my_score

  return (
    <section className="comments-section" id="izohlar">
      <SectionHead
        index="07"
        title="Izohlar"
        jp="感想"
        description={
          summary.count
            ? `O'rtacha baho ${shownAverage}/10 · ${summary.count} ta baholagan`
            : 'Bu media haqida fikrlar — bot va sayt bitta jadvalda.'
        }
      />

      <div className="comments-panel">
        <div className="rating-widget">
          <div className="rating-widget-head">
            <span className="rating-widget-label">
              <i className="bi bi-star-fill" aria-hidden="true" /> Bahoyingiz
            </span>
            <span className="rating-widget-value">
              {myScore ? `${myScore}/10` : 'Baho qo\'yilmagan'}
            </span>
          </div>
          {signedIn ? (
            <div className="rating-scale" role="group" aria-label="1 dan 10 gacha baho">
              {Array.from({ length: 10 }, (_, index) => index + 1).map((score) => (
                <button
                  key={score}
                  type="button"
                  className={`rating-chip${myScore === score ? ' is-active' : ''}`}
                  aria-pressed={myScore === score}
                  disabled={scoreBusy}
                  onClick={() => rate(score)}
                >
                  {score}
                </button>
              ))}
            </div>
          ) : (
            <p className="comments-hint">
              Baholash uchun <Link to="/login">tizimga kiring</Link>.
            </p>
          )}
        </div>

        {signedIn ? (
          <form className="comment-form" onSubmit={submit}>
            <textarea
              className="comment-input"
              rows={3}
              maxLength={1000}
              placeholder="Fikringizni yozing (1000 belgigacha)…"
              value={body}
              onChange={(event) => setBody(event.target.value)}
            />
            <div className="comment-form-foot">
              <span className="comment-counter">{body.length}/1000</span>
              <button
                className="ac-btn ac-btn-primary"
                type="submit"
                disabled={sending || !body.trim()}
              >
                {sending ? 'Yuborilmoqda…' : 'Izoh yuborish'}
              </button>
            </div>
          </form>
        ) : (
          <p className="comments-hint">
            Izoh qoldirish uchun <Link to="/login">tizimga kiring</Link> yoki{' '}
            <Link to="/register">hisob oching</Link>.
          </p>
        )}

        {error && <p className="comments-error">{error}</p>}
        {notice && !error && <p className="comments-notice">{notice}</p>}

        {loading ? (
          <div className="comments-list" aria-busy="true">
            {Array.from({ length: 3 }).map((_, index) => (
              <div className="ac-skeleton" key={index} style={{ height: 72, borderRadius: 12 }} />
            ))}
          </div>
        ) : list.results.length === 0 ? (
          <p className="comments-empty">Hozircha izoh yo'q. Birinchi bo'lib yozing.</p>
        ) : (
          <ul className="comments-list">
            {list.results.map((comment) => {
              const name = comment.author?.display_name || comment.author?.username || 'Foydalanuvchi'
              return (
                <li className="comment-card" key={comment.id}>
                  <span className="comment-avatar" aria-hidden="true">
                    {comment.author_initial || initialsOf(name)}
                  </span>
                  <div className="comment-body">
                    <div className="comment-meta">
                      <b>{name}</b>
                      {comment.author?.is_premium && <PremiumBadge />}
                      {comment.part?.number ? (
                        <span className="comment-part">{comment.part.number}-qism</span>
                      ) : null}
                      <time dateTime={comment.created_at}>{formatDate(comment.created_at)}</time>
                      {comment.author_rating ? (
                        <span className="comment-score">
                          <i className="bi bi-star-fill" aria-hidden="true" /> {comment.author_rating}
                        </span>
                      ) : null}
                    </div>
                    <p className="comment-text">{comment.body}</p>
                  </div>
                  {comment.author?.id && comment.author.id === user?.id ? (
                    <button
                      className="comment-delete"
                      type="button"
                      aria-label="Izohni o'chirish"
                      onClick={() => remove(comment.id)}
                    >
                      <i className="bi bi-trash3" aria-hidden="true" />
                    </button>
                  ) : null}
                </li>
              )
            })}
          </ul>
        )}

        {list.pages > 1 && (
          <div className="comments-pager">
            <button
              className="ac-btn ac-btn-ghost"
              type="button"
              disabled={page <= 1}
              onClick={() => load(page - 1)}
            >
              <i className="bi bi-arrow-left" aria-hidden="true" /> Oldingi
            </button>
            <span>
              {list.page}/{list.pages}
            </span>
            <button
              className="ac-btn ac-btn-ghost"
              type="button"
              disabled={page >= list.pages}
              onClick={() => load(page + 1)}
            >
              Keyingi <i className="bi bi-arrow-right" aria-hidden="true" />
            </button>
          </div>
        )}
      </div>
    </section>
  )
}
