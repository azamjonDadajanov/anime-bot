import { useState, useEffect } from 'react'
import { Alert, Badge, Button, Group, Loader, Text, Title } from '@mantine/core'
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
  const loading = loadedSlug !== slug

  useEffect(() => {
    let active = true
    mediaApi.detail(slug)
      .then((data) => {
        if (!active) return
        setItem(data)
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
  const parts = isManga ? orderParts(item.parts || []) : (item.parts || [])
  const resume = isManga ? computeResume(progress, parts) : null
  const telegramUrl = (partId) => `https://t.me/adgfdsfbot?start=part_${partId}`
  const rememberPart = (partId) => {
    if (!hasAccessToken()) return
    mediaApi.recordView(slug, partId).catch(() => {})
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
            <Title order={2}>Barcha qismlar</Title>
          </div>
          <Text c="dimmed" size="sm">{parts.length} ta qism</Text>
        </div>
        {!parts.length ? (
          <div className="empty-state compact-empty">
            <i className="bi bi-hourglass-split" aria-hidden="true" />
            <Text>Qismlar hali qo'shilmagan.</Text>
          </div>
        ) : isManga ? (
          <div className="parts-list">
            {parts.map((part) => {
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
                    <b>{part.season_number ? `${part.season_number}-fasl · ` : ''}{part.number}-qism</b>
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
            {parts.map((part) => (
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
                  <b>{part.season_number ? `${part.season_number}-fasl · ` : ''}{part.number}-qism</b>
                  <span>{part.title || item.title}</span>
                </span>
                <i className="bi bi-telegram part-telegram" aria-hidden="true" />
              </a>
            ))}
          </div>
        )}
      </section>
    </main>
  )
}

export default MediaDetailPage
