import { useState, useEffect } from 'react'
import { Alert, Pagination } from '@mantine/core'
import MediaGrid from '../components/MediaGrid'
import PageHeading from '../components/PageHeading'
import { sections } from '../mediaSections'

const PAGE_SIZE = 20

function CatalogSectionPage({ section }) {
  const config = sections[section]
  const [items, setItems] = useState([])
  const [page, setPage] = useState(1)
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!config) return undefined
    let active = true
    config.load({ page })
      .then((data) => {
        if (!active) return
        setItems(Array.isArray(data) ? data : data.results || [])
        setCount(Array.isArray(data) ? data.length : data.count || 0)
        setError('')
      })
      .catch(() => active && setError("Server bilan bog'lanishda xatolik yuz berdi."))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [page, config])

  if (!config) {
    return <main className="dashboard-page"><Alert color="red">Bo'lim topilmadi.</Alert></main>
  }

  function changePage(next) {
    setLoading(true)
    setPage(next)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const totalPages = Math.ceil(count / PAGE_SIZE)

  return (
    <main className="dashboard-page">
      <PageHeading
        eyebrow={config.eyebrow}
        title={config.title}
        description={config.description}
        stats={!loading && count ? [{ value: count, label: 'Media' }] : undefined}
      />

      {error && <Alert color="red" mb="lg" title="Katalog yuklanmadi">{error}</Alert>}

      <MediaGrid
        items={items}
        loading={loading}
        emptyTitle="Bo'lim hozircha bo'sh"
        emptyDescription="Bu bo'limga media qo'shilgach shu yerda paydo bo'ladi."
      />

      {!loading && count > PAGE_SIZE && (
        <div className="catalog-foot">
          <span>
            {page}-sahifa / {totalPages} · jami {count} ta media
          </span>
          <Pagination
            total={totalPages}
            value={page}
            onChange={changePage}
            size="sm"
            withEdges
          />
        </div>
      )}
    </main>
  )
}

export default CatalogSectionPage
