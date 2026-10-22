import { useState, useEffect } from 'react'
import { Alert, Pagination, Select, TextInput } from '@mantine/core'
import { Link } from 'react-router-dom'
import { mediaApi } from '../apis/api'
import MediaGrid from '../components/MediaGrid'
import SectionHead from '../components/SectionHead'
import { SpotlightCard, SpotlightSkeleton } from '../components/SpotlightCard'
import { MEDIA_TYPE_LABELS } from '../mediaMeta'

const PER_PAGE = 10

const mediaTypes = [
  { value: 'movie', label: 'Kino' },
  { value: 'anime', label: 'Anime' },
  { value: 'series', label: 'Serial' },
  { value: 'manga', label: 'Manga' },
]

function errorText(error) {
  const data = error.response?.data
  if (!data) return "Server bilan bog'lanishda xatolik yuz berdi."
  if (typeof data.detail === 'string') return data.detail
  return Object.values(data).flat().map(String).join(' ')
}

export function FavoritesPage() {
  const [items, setItems] = useState([])
  const [query, setQuery] = useState('')
  const [type, setType] = useState(null)
  const [page, setPage] = useState(1)
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    const timer = window.setTimeout(() => {
      setError('')
      mediaApi.favorites({ page, search: query.trim(), type: type || undefined })
        .then((data) => {
          if (!active) return
          setItems(data.results)
          setCount(data.count)
        })
        .catch((requestError) => active && setError(errorText(requestError)))
        .finally(() => active && setLoading(false))
    }, query ? 250 : 0)
    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [page, query, type])

  function updateQuery(event) {
    setLoading(true)
    setQuery(event.currentTarget.value)
    setPage(1)
  }

  function updateType(value) {
    setLoading(true)
    setType(value)
    setPage(1)
  }

  function updatePage(nextPage) {
    setLoading(true)
    setPage(nextPage)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const filtering = Boolean(query.trim() || type)
  // The newest favourite headlines the page (first result, newest-first order).
  const featured = !filtering && page === 1 && items.length > 0 ? items[0] : null
  const rest = featured ? items.slice(1) : items
  const formats = new Set(items.map((item) => MEDIA_TYPE_LABELS[item.type] || item.type)).size
  const totalPages = Math.ceil(count / PER_PAGE)

  return (
    <main className="dashboard-page">
      <section className="library-hero">
        <div className="library-copy">
          <span className="eyebrow">Sizning kutubxonangiz</span>
          <h1 className="library-title">
            Sevimlilar, <em>bir joyda.</em>
          </h1>
          <p className="library-text">
            Telegram botda saqlagan va saytda belgilagan barcha media — kino,
            anime, serial va manga. Qaytganingizda davom etish uchun tayyor.
          </p>

          <div className="library-toolbar">
            <TextInput
              aria-label="Sevimlilardan qidirish"
              placeholder="Kutubxonadan qidirish…"
              leftSection={<i className="bi bi-search" aria-hidden="true" />}
              value={query}
              onChange={updateQuery}
            />
            <Select
              aria-label="Media turini tanlang"
              placeholder="Barcha turlar"
              clearable
              data={mediaTypes}
              value={type}
              onChange={updateType}
            />
          </div>

          <div className="library-stats">
            <span><b>{count}</b> media</span>
            <span><b>{formats}</b> format</span>
            <span><b>{PER_PAGE}</b> har sahifa</span>
          </div>
        </div>

        <div className="library-visual">
          {loading
            ? <SpotlightSkeleton />
            : <SpotlightCard item={featured} kicker="Oxirgi saralangan" icon="bi-star-fill" />}
        </div>
      </section>

      {error && <Alert color="red" mb="lg">{error}</Alert>}

      <section className="favorites-list">
        <SectionHead
          index="02"
          title={filtering ? 'Natijalar' : 'Barcha sevimlilar'}
          jp={filtering ? '検索' : '本棚'}
          description={filtering ? undefined : "Saralangan sana bo'yicha, eng yangisi birinchi."}
          linkLabel="Katalog"
          href="/explore"
        />
        <MediaGrid
            items={rest}
            loading={loading}
            emptyTitle={filtering ? 'Hech narsa topilmadi' : "Sevimlilar hozircha bo'sh"}
            emptyDescription={filtering
              ? 'Boshqa nom yoki tur bilan urinib ko‘ring.'
              : "Telegram botda yoki media sahifasida yoqtirgan filmingizni sevimlilarga qo'shing."}
            emptyAction={!filtering ? (
              <Link className="ac-btn ac-btn-ghost" to="/explore">
                Katalogni kashf etish <i className="bi bi-compass" aria-hidden="true" />
              </Link>
            ) : null}
        />
      </section>

      {!loading && count > PER_PAGE && (
        <div className="catalog-foot">
          <span>Jami {count} ta media · har sahifada {PER_PAGE} ta</span>
          <Pagination total={totalPages} value={page} onChange={updatePage} size="sm" withEdges />
        </div>
      )}
    </main>
  )
}

export default FavoritesPage
