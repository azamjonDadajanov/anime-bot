import { useState, useEffect } from 'react'
import { Alert, Group, Pagination, Select, Text, TextInput, Title } from '@mantine/core'
import { mediaApi } from '../apis/api'
import MediaGrid from '../components/MediaGrid'
import { SpotlightCard, SpotlightSkeleton } from '../components/SpotlightCard'

const PER_PAGE = 10

const mediaTypes = [
  { value: 'movie', label: 'Kino' },
  { value: 'anime', label: 'Anime' },
  { value: 'series', label: 'Serial' },
  { value: 'manga', label: 'Manga' },
]

function errorText(error) {
  const data = error.response?.data
  if (!data) return 'Server bilan bog\'lanishda xatolik yuz berdi.'
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
  }

  const filtering = Boolean(query.trim() || type)
  // The newest favourite headlines the page (first result, newest-first order).
  const featured = !filtering && page === 1 && items.length > 0 ? items[0] : null
  const rest = featured ? items.slice(1) : items
  const showEmpty = !loading && !filtering && items.length === 0
  const showGrid = loading || filtering || rest.length > 0 || showEmpty

  return (
    <main className="dashboard-page">
      <section className="home-hero favorites-hero">
        <div className="home-hero-copy">
          <Text className="eyebrow">SIZNING KUTUBXONANGIZ</Text>
          <Title order={1} className="home-hero-title">Sevimlilar</Title>
          <Text c="dimmed" className="home-hero-text">
            Telegram botda saqlagan barcha turdagi media — kino, anime, serial va manga.
          </Text>
          <div className="favorites-toolbar">
            <TextInput
              className="catalog-search"
              aria-label="Sevimlilardan qidirish"
              placeholder="Sevimlilardan qidirish"
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
          <ul className="home-hero-pills">
            <li><i className="bi bi-collection" aria-hidden="true" /> {count} ta media</li>
            <li><i className="bi bi-clock-history" aria-hidden="true" /> Saralangan sana bo'yicha</li>
          </ul>
        </div>
        {loading ? <SpotlightSkeleton /> : <SpotlightCard item={featured} kicker="Oxirgi saralangan" icon="bi-star-fill" />}
      </section>

      {error && <Alert color="red" mb="lg">{error}</Alert>}

      {(showGrid || rest.length > 0) && (
        <section className="favorites-list">
          <div className="rail-head">
            <Text component="h2" className="rail-title">{filtering ? 'Natijalar' : 'Barcha sevimlilar'}</Text>
            <Text size="sm" c="dimmed">{count} ta media</Text>
          </div>
          <MediaGrid
            items={rest}
            loading={loading}
            emptyTitle="Sevimlilar hozircha bo'sh"
            emptyDescription="Telegram botda yoqtirgan mediangizni sevimlilarga qo'shing."
          />
        </section>
      )}

      {!loading && count > PER_PAGE && (
        <Group justify="space-between" mt="xl" className="pagination-row">
          <Text c="dimmed" size="sm">Jami {count} ta media · har sahifada {PER_PAGE} ta</Text>
          <Pagination total={Math.ceil(count / PER_PAGE)} value={page} onChange={updatePage} />
        </Group>
      )}
    </main>
  )
}

export default FavoritesPage
