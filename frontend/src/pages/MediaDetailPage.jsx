import { useState, useEffect, useMemo } from 'react'
import { Alert, Badge, Button, Group, Loader, Tabs, Text, Title } from '@mantine/core'
import { Link, useParams } from 'react-router-dom'
import { hasAccessToken, mediaApi } from '../apis/api'
import { computeResume, loadTitleProgress, orderParts } from '../reading'

const mediaTypeLabels = {
  movie: 'Kino',
  anime: 'Anime',
  series: 'Serial',
  manga: 'Manga',
}

function errorText(error) {
  const data = error.response?.data
  if (!data) return 'Server bilan bog\'lanishda xatolik yuz berdi.'
  if (typeof data.detail === 'string') return data.detail
  return Object.values(data).flat().map(String).join(' ')
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
  const loading = loadedSlug !== slug

  useEffect(() => {
    let active = true
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

  const parts = useMemo(() => {
    if (!item) return []
    return item.type === 'manga' ? orderParts(item.parts || []) : (item.parts || [])
  }, [item])

  // Group parts by season number
  const seasons = useMemo(() => {
    if (!parts.length) return []
    const groups = new Map()
    parts.forEach((part) => {
      const sNum = part.season_number != null ? Number(part.season_number) : 1
      const key = String(sNum)
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          seasonNumber: sNum,
          label: `${sNum}-fasl`,
          parts: [],
        })
      }
      groups.get(key).parts.push(part)
    })
    return Array.from(groups.values()).sort((a, b) => a.seasonNumber - b.seasonNumber)
  }, [parts])

  const [activeSeason, setActiveSeason] = useState(null)

  useEffect(() => {
    if (seasons.length > 0 && (!activeSeason || !seasons.some((s) => s.key === activeSeason))) {
      setActiveSeason(seasons[0].key)
    }
  }, [seasons, activeSeason])

  if (loading) return <main className="dashboard-page"><div className="page-loader"><Loader /></div></main>
  if (errorSlug === slug && error) {
    return <main className="dashboard-page"><Alert color="red" title="Media topilmadi">{error}</Alert></main>
  }
  if (!item) {
    return <main className="dashboard-page"><Alert color="red" title="Media topilmadi">Bu media katalogda mavjud emas.</Alert></main>
  }

  const cover = item.cover
    ? `data:${item.cover_content_type || 'image/jpeg'};base64,${item.cover}`
    : ''
  const isManga = item.type === 'manga'
  const resume = isManga ? computeResume(progress, parts) : null

  const currentSeason = seasons.find((s) => s.key === activeSeason) || seasons[0]
  const currentParts = currentSeason ? currentSeason.parts : []

  const telegramUrl = (partId) => `https://t.me/adgfdsfbot?start=part_${partId}`
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
      <Link className="back-link" to="/">
        <i className="bi bi-arrow-left" aria-hidden="true" /> Katalogga qaytish
      </Link>
      <section className="detail-hero">
        <div className="detail-cover">
          {cover ? <img src={cover} alt={`${item.title} muqovasi`} /> : <i className="bi bi-film" aria-hidden="true" />}
        </div>
        <div className="detail-copy">
          <Badge variant="light">{mediaTypeLabels[item.type] || item.type}</Badge>
          <Text className="media-year">{item.release_year || 'Yil ko\'rsatilmagan'} · {item.status}</Text>
          <Title order={1}>{item.title}</Title>
          <Group gap="xs" className="detail-genres">
            {(item.genres || []).map((genre) => <Badge key={genre} variant="outline">{genre}</Badge>)}
          </Group>
          <Text className="detail-synopsis">{item.synopsis || 'Ushbu media uchun tavsif kiritilmagan.'}</Text>
          <Group gap="xl" className="detail-facts">
            {item.rating && <Text><i className="bi bi-star-fill" aria-hidden="true" /> {item.rating}/10</Text>}
            {item.language && <Text><i className="bi bi-translate" aria-hidden="true" /> {item.language}</Text>}
            <Text><i className="bi bi-collection" aria-hidden="true" /> {parts.length} qism</Text>
          </Group>
          {hasAccessToken() && (
            <Group className="manga-cta">
              <Button
                variant={isFavorite ? 'filled' : 'light'}
                color={isFavorite ? 'red' : 'gray'}
                size="md"
                loading={favoriteBusy}
                onClick={toggleFavorite}
                leftSection={
                  <i className={isFavorite ? 'bi bi-heart-fill' : 'bi bi-heart'} aria-hidden="true" />
                }
              >
                {isFavorite ? "Sevimlilardan olib tashlash" : "Sevimlilarga qo'shish"}
              </Button>
            </Group>
          )}
          {isManga && parts.length > 0 && (
            <Group className="manga-cta">
              <Button
                component={Link}
                to={`/read/${slug}`}
                size="md"
                leftSection={<i className="bi bi-book-half" aria-hidden="true" />}
              >
                {resume
                  ? `Davom ettirish · ${resume.part.number}-qism, ${resume.page}-sahifa`
                  : "O'qishni boshlash"}
              </Button>
            </Group>
          )}
        </div>
      </section>

      <section className="parts-section">
        <div className="parts-heading">
          <div>
            <Text className="section-kicker">{isManga ? "O'QISH" : 'TOMOSHA QILISH'}</Text>
            <Title order={2}>Qismlar</Title>
          </div>
          <Text c="dimmed" size="sm">
            {currentSeason ? `${currentSeason.label} · ${currentParts.length} ta qism` : `${parts.length} ta qism`}
          </Text>
        </div>

        {!parts.length ? (
          <div className="empty-state compact-empty">
            <i className="bi bi-hourglass-split" aria-hidden="true" />
            <Text>Qismlar hali qo'shilmagan.</Text>
          </div>
        ) : (
          <>
            {seasons.length > 0 && (
              <Tabs
                value={activeSeason}
                onChange={setActiveSeason}
                variant="pills"
                radius="md"
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

            {isManga ? (
              <div className="parts-list">
                {currentParts.map((part) => {
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
                })}
              </div>
            ) : (
              <div className="parts-list">
                {currentParts.map((part) => (
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
                    <i className="bi bi-telegram part-telegram" aria-hidden="true" />
                  </a>
                ))}
              </div>
            )}
          </>
        )}
      </section>
    </main>
  )
}

export default MediaDetailPage
