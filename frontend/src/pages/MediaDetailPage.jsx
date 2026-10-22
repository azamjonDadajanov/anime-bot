import { useState, useEffect, useMemo } from 'react'
import { Alert, Tabs } from '@mantine/core'
import { Link, useParams } from 'react-router-dom'
import { hasAccessToken, mediaApi } from '../apis/api'
import { coverSrc } from '../apis/mediaUrl'
import { computeResume, loadTitleProgress, orderParts } from '../reading'
import MediaRail from '../components/MediaRail'
import CommentsSection from '../components/CommentsSection'
import {
  genreNames,
  releaseLabel,
  statusLabel,
  typeLabel,
} from '../mediaMeta'

function errorText(error) {
  const data = error.response?.data
  if (!data) return "Server bilan bog'lanishda xatolik yuz berdi."
  if (typeof data.detail === 'string') return data.detail
  return Object.values(data).flat().map(String).join(' ')
}

function DetailSkeleton() {
  return (
    <div aria-busy="true" aria-hidden="true">
      <div className="detail-cinema">
        <div className="ac-skeleton ac-skeleton-poster" />
        <div style={{ display: 'grid', gap: 14 }}>
          <div className="ac-skeleton ac-skeleton-line" style={{ width: '26%' }} />
          <div className="ac-skeleton ac-skeleton-line" style={{ width: '78%', height: 56 }} />
          <div className="ac-skeleton ac-skeleton-line" style={{ width: '92%' }} />
          <div className="ac-skeleton ac-skeleton-line" style={{ width: '88%' }} />
          <div className="ac-skeleton ac-skeleton-line" style={{ width: '64%' }} />
          <div className="ac-skeleton ac-skeleton-line" style={{ width: '40%', height: 44, marginTop: 10, borderRadius: 999 }} />
        </div>
      </div>
      <div className="parts-list">
        {Array.from({ length: 6 }).map((_, index) => (
          <div className="ac-skeleton" key={index} style={{ height: 60, borderRadius: 10 }} />
        ))}
      </div>
    </div>
  )
}

export function MediaDetailPage() {
  const { slug } = useParams()
  const [item, setItem] = useState(null)
  const [loadedSlug, setLoadedSlug] = useState('')
  const [error, setError] = useState('')
  const [errorSlug, setErrorSlug] = useState('')
  const [progress, setProgress] = useState({})
  const [isFavorite, setIsFavorite] = useState(false)
  const [favoriteBusy, setFavoriteBusy] = useState(false)
  const [related, setRelated] = useState([])
  const loading = loadedSlug !== slug

  useEffect(() => {
    let active = true
    setRelated([])
    mediaApi.detail(slug)
      .then((data) => {
        if (!active) return
        setItem(data)
        setIsFavorite(Boolean(data.is_favorite))
        setError('')
        setLoadedSlug(slug)
      })
      .catch((requestError) => {
        if (!active) return
        setError(errorText(requestError))
        setErrorSlug(slug)
      })
      .finally(() => active && setLoadedSlug(slug))
    return () => { active = false }
  }, [slug])

  // Feed the profile's "Oxirgi ko'rgan medialar" / activity tabs.
  useEffect(() => {
    if (!item || !hasAccessToken()) return
    mediaApi.recordView(slug).catch(() => {})
  }, [item, slug])

  useEffect(() => {
    if (!item || item.type !== 'manga') return undefined
    let active = true
    loadTitleProgress(slug)
      .then((data) => active && setProgress(data))
      .catch(() => {})
    return () => { active = false }
  }, [slug, item])

  // "O'xshash animelar": ranked on the server — shared genres first, then the
  // same format, then the same release window (same rail the bot shows).
  useEffect(() => {
    if (!item) return undefined
    let active = true
    mediaApi.similar(slug)
      .then((list) => active && setRelated(list))
      .catch(() => {})
    return () => { active = false }
  }, [item, slug])

  const parts = useMemo(() => {
    if (!item) return []
    return item.type === 'manga' ? orderParts(item.parts || []) : (item.parts || [])
  }, [item])

  const seasons = useMemo(() => {
    if (!parts.length) return []
    const groups = new Map()
    parts.forEach((part) => {
      const seasonNumber = part.season_number != null ? Number(part.season_number) : 1
      const key = String(seasonNumber)
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          seasonNumber,
          label: `${seasonNumber}-fasl`,
          parts: [],
        })
      }
      groups.get(key).parts.push(part)
    })
    return Array.from(groups.values()).sort((a, b) => a.seasonNumber - b.seasonNumber)
  }, [parts])

  const [activeSeason, setActiveSeason] = useState(null)

  useEffect(() => {
    if (seasons.length > 0 && (!activeSeason || !seasons.some((season) => season.key === activeSeason))) {
      setActiveSeason(seasons[0].key)
    }
  }, [seasons, activeSeason])

  if (loading) return <main className="dashboard-page"><DetailSkeleton /></main>

  if (errorSlug === slug && error) {
    return (
      <main className="dashboard-page">
        <div className="empty-state">
          <i className="bi bi-exclamation-diamond" aria-hidden="true" />
          <h2>Media topilmadi</h2>
          <p>{error}</p>
          <Link className="ac-btn ac-btn-ghost" to="/explore">Katalogga qaytish</Link>
        </div>
      </main>
    )
  }

  if (!item) {
    return (
      <main className="dashboard-page">
        <div className="empty-state">
          <i className="bi bi-film" aria-hidden="true" />
          <h2>Media topilmadi</h2>
          <p>Bu media katalogda mavjud emas yoki o&apos;chirilgan.</p>
          <Link className="ac-btn ac-btn-ghost" to="/explore">Katalogga qaytish</Link>
        </div>
      </main>
    )
  }

  const cover = coverSrc(item)
  const isManga = item.type === 'manga'
  const resume = isManga ? computeResume(progress, parts) : null
  const currentSeason = seasons.find((season) => season.key === activeSeason) || seasons[0]
  const currentParts = currentSeason ? currentSeason.parts : []
  const genres = genreNames(item)
  const primaryGenre = genres[0]

  const telegramUrl = (partId) => `https://t.me/anichoparbot?start=part_${partId}`
  const rememberPart = (partId) => {
    if (!hasAccessToken()) return
    mediaApi.recordView(slug, partId).catch(() => {})
  }

  function toggleFavorite() {
    if (!hasAccessToken() || favoriteBusy) return
    setFavoriteBusy(true)
    mediaApi.toggleFavorite(slug)
      .then((data) => setIsFavorite(Boolean(data.is_favorite)))
      .catch(() => {})
      .finally(() => setFavoriteBusy(false))
  }

  return (
    <main className="dashboard-page">
      <Link className="back-link" to="/explore">
        <i className="bi bi-arrow-left" aria-hidden="true" /> Katalogga qaytish
      </Link>

      <section className="detail-cinema">
        {cover && <img className="detail-cinema-bg" src={cover} alt="" aria-hidden="true" />}
        <div className="detail-cover">
          {cover
            ? <img src={cover} alt={`${item.title} muqovasi`} />
            : <i className="bi bi-film" aria-hidden="true" />}
          <span className="detail-cover-tag">
            <span>{typeLabel(item)}</span>
            {item.default_quality ? (
              <span><i className="bi bi-badge-hd" aria-hidden="true" /> {item.default_quality}</span>
            ) : null}
          </span>
        </div>

        <div className="detail-copy">
          <div className="detail-topline">
            <span>{typeLabel(item)}</span>
            <span className="dot" aria-hidden="true" />
            <span>{releaseLabel(item)}</span>
            <span className="dot" aria-hidden="true" />
            <span>{statusLabel(item)}</span>
            {item.code ? (
              <>
                <span className="dot" aria-hidden="true" />
                <span>Kod {item.code}</span>
              </>
            ) : null}
          </div>

          <h1 className="detail-title">{item.title}</h1>

          {genres.length > 0 && (
            <div className="detail-genres">
              {genres.map((genre) => (
                <Link
                  className="detail-genre"
                  key={genre}
                  to={`/explore?genre=${encodeURIComponent(genre)}`}
                >
                  {genre}
                </Link>
              ))}
            </div>
          )}

          <p className="detail-synopsis">
            {item.synopsis || 'Ushbu media uchun tavsif kiritilmagan.'}
          </p>

          <div className="detail-facts">
            {item.rating || item.rating_average || item.rating_count ? (
              <span className="detail-fact">
                Reyting
                <b>
                  <i className="bi bi-star-fill" aria-hidden="true" />{' '}
                  {item.rating_average
                    ? Number(item.rating_average).toFixed(1).replace(/\.0$/, '')
                    : item.rating || '—'}
                  {item.rating_count ? ` · ${item.rating_count} baho` : '/10'}
                </b>
              </span>
            ) : null}
            {item.language ? (
              <span className="detail-fact">
                Til
                <b><i className="bi bi-translate" aria-hidden="true" /> {item.language}</b>
              </span>
            ) : null}
            <span className="detail-fact">
              Qismlar
              <b><i className="bi bi-collection" aria-hidden="true" /> {parts.length || item.episode_count || 0}</b>
            </span>
            {item.required_plan === 'paid' ? (
              <span className="detail-fact">
                Kirish
                <b><i className="bi bi-stars" aria-hidden="true" /> Obuna</b>
              </span>
            ) : null}
          </div>

          <div className="detail-actions">
            {isManga && parts.length > 0 && (
              <Link className="ac-btn ac-btn-primary" to={`/read/${slug}`}>
                <i className="bi bi-book-half" aria-hidden="true" />
                {resume
                  ? `Davom ettirish · ${resume.part.number}-qism`
                  : "O'qishni boshlash"}
              </Link>
            )}

            {hasAccessToken() ? (
              <button
                className={`detail-fav${isFavorite ? ' is-active' : ''}`}
                type="button"
                aria-pressed={isFavorite}
                disabled={favoriteBusy}
                onClick={toggleFavorite}
              >
                <i className={isFavorite ? 'bi bi-heart-fill' : 'bi bi-heart'} aria-hidden="true" />
                {isFavorite ? 'Sevimlilarda' : "Sevimlilarga qo'shish"}
              </button>
            ) : (
              <Link className="ac-btn ac-btn-ghost" to="/login">
                Saqlash uchun kirish <i className="bi bi-box-arrow-in-right" aria-hidden="true" />
              </Link>
            )}

            {!isManga && currentParts.length > 0 && (
              <a
                className="ac-btn ac-btn-ghost"
                href={telegramUrl(currentParts[0].id)}
                target="_blank"
                rel="noreferrer"
                onClick={() => rememberPart(currentParts[0].id)}
              >
                <i className="bi bi-telegram" aria-hidden="true" /> Birinchi qism
              </a>
            )}
          </div>
        </div>
      </section>

      <section className="parts-section">
        <div className="parts-heading">
          <div className="parts-heading-main">
            <span className="section-kicker">{isManga ? "O'QISH" : 'TOMOSHA QILISH'}</span>
            <h2>Qismlar</h2>
          </div>
          <span className="parts-heading-count">
            {currentSeason ? `${currentSeason.label} · ${currentParts.length} ta qism` : `${parts.length} ta qism`}
          </span>
        </div>

        {!parts.length ? (
          <div className="empty-state compact-empty">
            <i className="bi bi-hourglass-split" aria-hidden="true" />
            <h3>Qismlar hali qo&apos;shilmagan</h3>
            <p>Media tayyor bo&apos;lgach, qismlar shu yerda paydo bo&apos;ladi.</p>
          </div>
        ) : (
          <>
            {seasons.length > 1 && (
              <Tabs
                value={activeSeason}
                onChange={setActiveSeason}
                variant="pills"
                className="season-tabs"
              >
                <Tabs.List>
                  {seasons.map((season) => (
                    <Tabs.Tab
                      key={season.key}
                      value={season.key}
                      leftSection={<i className="bi bi-collection-play" aria-hidden="true" />}
                    >
                      {season.label} ({season.parts.length})
                    </Tabs.Tab>
                  ))}
                </Tabs.List>
              </Tabs>
            )}

            <div className="parts-list">
              {currentParts.map((part) => {
                if (isManga) {
                  const isRead = Boolean(progress[part.id]?.isRead)
                  return (
                    <Link
                      className="part-link"
                      to={`/read/${slug}/${part.number}`}
                      key={part.id}
                      onClick={() => rememberPart(part.id)}
                    >
                      <span className="part-play"><i className="bi bi-book" aria-hidden="true" /></span>
                      <span className="part-copy">
                        <b>{part.number}-qism</b>
                        <span>{part.title || item.title}</span>
                      </span>
                      {isRead
                        ? <i className="bi bi-check-circle-fill part-read" aria-label="O'qilgan" />
                        : <i className="bi bi-chevron-right part-open" aria-hidden="true" />}
                    </Link>
                  )
                }
                return (
                  <a
                    className="part-link"
                    href={telegramUrl(part.id)}
                    target="_blank"
                    rel="noreferrer"
                    key={part.id}
                    onClick={() => rememberPart(part.id)}
                  >
                    <span className="part-play"><i className="bi bi-play-fill" aria-hidden="true" /></span>
                    <span className="part-copy">
                      <b>{part.number}-qism</b>
                      <span>{part.title || item.title}</span>
                    </span>
                    <i className="bi bi-telegram part-telegram" aria-label="Telegramda ochish" />
                  </a>
                )
              })}
            </div>
          </>
        )}
      </section>

      <CommentsSection slug={item.slug} />

      {related.length > 0 && (
        <div className="related-block">
          <MediaRail
            title="O'xshash animelar"
            jp="類似"
            index="08"
            description={primaryGenre ? `${primaryGenre} janridan yana shu xil hikoyalar.` : undefined}
            href={primaryGenre ? `/explore?genre=${encodeURIComponent(primaryGenre)}` : '/explore'}
            linkLabel="Katalogda ko'rish"
            items={related}
          />
        </div>
      )}
    </main>
  )
}

export default MediaDetailPage
