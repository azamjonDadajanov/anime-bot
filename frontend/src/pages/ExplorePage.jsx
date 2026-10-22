import { useMemo } from 'react'
import { Select, TextInput } from '@mantine/core'
import { useSearchParams } from 'react-router-dom'
import useCatalogIndex from '../hooks/useCatalogIndex'
import PageHeading from '../components/PageHeading'
import MediaGrid from '../components/MediaGrid'
import { MEDIA_TYPE_ICONS, MEDIA_TYPE_LABELS, genreNames } from '../mediaMeta'

const FORMATS = [
  { value: 'anime', label: 'Animelar', icon: MEDIA_TYPE_ICONS.anime },
  { value: 'movie', label: 'Filmlar', icon: MEDIA_TYPE_ICONS.movie },
  { value: 'series', label: 'Seriallar', icon: MEDIA_TYPE_ICONS.series },
  { value: 'manga', label: 'Mangalar', icon: MEDIA_TYPE_ICONS.manga },
]

const SORTS = [
  { value: 'newest', label: 'Eng yangi' },
  { value: 'rating', label: 'Reyting' },
  { value: 'az', label: "A–Z" },
]

function ExplorePage() {
  const { items, counts, allGenres, loading, error, reload } = useCatalogIndex()
  const [params, setParams] = useSearchParams()

  const query = params.get('q') || ''
  const format = params.get('type') || ''
  const genre = params.get('genre') || ''
  const sort = params.get('sort') || 'newest'

  function setParam(key, value) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  function resetFilters() {
    setParams(new URLSearchParams(), { replace: true })
  }

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const list = items.filter((item) => {
      if (format && item.type !== format) return false
      if (genre && !genreNames(item).some((name) => name.toLowerCase() === genre.toLowerCase())) return false
      if (needle && !String(item.title || '').toLowerCase().includes(needle)) return false
      return true
    })
    if (sort === 'rating') {
      return list.sort((a, b) => (Number(b.rating) || 0) - (Number(a.rating) || 0))
    }
    if (sort === 'az') {
      return list.sort((a, b) => String(a.title || '').localeCompare(String(b.title || ''), 'uz'))
    }
    return list.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
  }, [items, query, format, genre, sort])

  const active = Boolean(query.trim() || format || genre)
  const filterSummary = [
    format ? MEDIA_TYPE_LABELS[format] : '',
    genre,
    query.trim() ? `“${query.trim()}”` : '',
  ].filter(Boolean).join(' · ')

  return (
    <main className="dashboard-page">
      <PageHeading
        eyebrow="Kashf / Katalog 2026"
        title="Katalogni kashf eting"
        description="Format, janr va kayfiyat bo'yicha filtrlang. Har bir tanlov haqiqiy katalogdan olinadi."
        stats={[
          { value: counts.total, label: 'Media' },
          { value: allGenres.length, label: 'Janr' },
        ]}
      />

      {error ? (
        <div className="empty-state">
          <i className="bi bi-broadcast-pin" aria-hidden="true" />
          <h2>Katalog yuklanmadi</h2>
          <p>{error}</p>
          <button className="ac-btn ac-btn-ghost" type="button" onClick={reload}>
            Qayta urinish <i className="bi bi-arrow-clockwise" aria-hidden="true" />
          </button>
        </div>
      ) : (
        <>
          <section className="explore-bar" aria-label="Katalog filtrlari">
            <div className="explore-bar-top">
              <TextInput
                className="explore-search"
                aria-label="Katalogdan qidirish"
                placeholder="Nom bo'yicha qidirish…"
                leftSection={<i className="bi bi-search" aria-hidden="true" />}
                value={query}
                onChange={(event) => setParam('q', event.currentTarget.value)}
                autoComplete="off"
              />
              <Select
                aria-label="Saralash"
                data={SORTS}
                value={sort}
                onChange={(value) => setParam('sort', value === 'newest' ? '' : value)}
                allowDeselect={false}
                leftSection={<i className="bi bi-sort-down" aria-hidden="true" />}
              />
              <Select
                aria-label="Format"
                placeholder="Barcha formatlar"
                data={FORMATS.map(({ value, label }) => ({ value, label }))}
                value={format || null}
                onChange={(value) => setParam('type', value || '')}
                clearable
                leftSection={<i className="bi bi-grid" aria-hidden="true" />}
              />
            </div>

            <div className="filter-block">
              <span className="filter-label">Format</span>
              <div className="filter-chips">
                <button
                  className={`filter-chip${!format ? ' is-active' : ''}`}
                  type="button"
                  onClick={() => setParam('type', '')}
                >
                  Barchasi <span className="count">{counts.total}</span>
                </button>
                {FORMATS.map((item) => (
                  <button
                    className={`filter-chip${format === item.value ? ' is-active' : ''}`}
                    key={item.value}
                    type="button"
                    onClick={() => setParam('type', format === item.value ? '' : item.value)}
                  >
                    <i className={`bi ${item.icon}`} aria-hidden="true" />
                    {item.label}
                    <span className="count">{counts[item.value] || 0}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="filter-block">
              <span className="filter-label">Janr</span>
              <div className="filter-chips">
                {allGenres.slice(0, 14).map((item) => (
                  <button
                    className={`filter-chip${genre.toLowerCase() === item.name.toLowerCase() ? ' is-active' : ''}`}
                    key={item.name}
                    type="button"
                    onClick={() => setParam('genre', genre === item.name ? '' : item.name)}
                  >
                    {item.name}
                    <span className="count">{item.count}</span>
                  </button>
                ))}
              </div>
            </div>
          </section>

          <div className="results-bar">
            <span>
              <b>{results.length}</b> natija {filterSummary ? `· ${filterSummary}` : '· barcha media'}
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 14 }}>
              {active && (
                <button className="results-clear" type="button" onClick={resetFilters}>
                  <i className="bi bi-x-lg" aria-hidden="true" /> Tozalash
                </button>
              )}
              {SORTS.find((item) => item.value === sort)?.label || 'Eng yangi'}
            </span>
          </div>

          <MediaGrid
            items={results}
            loading={loading}
            emptyTitle="Hech narsa topilmadi"
            emptyDescription="Boshqa nom, janr yoki format bilan urinib ko'ring."
            emptyAction={active ? (
              <button className="ac-btn ac-btn-ghost" type="button" onClick={resetFilters}>
                Filtrlarni tozalash
              </button>
            ) : null}
          />
        </>
      )}
    </main>
  )
}

export default ExplorePage
