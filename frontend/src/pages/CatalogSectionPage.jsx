import { useState, useEffect } from 'react'
import { Alert, Group, Pagination } from '@mantine/core'
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
    if (!config) return
    let active = true
    config.load({ page })
      .then((data) => {
        if (!active) return
        setItems(Array.isArray(data) ? data : data.results || [])
        setCount(Array.isArray(data) ? data.length : data.count || 0)
        setError('')
      })
      .catch(() => active && setError('Server bilan bog\'lanishda xatolik yuz berdi.'))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [page, config])

  if (!config) {
    return <main className="dashboard-page"><Alert color="red">Bo'lim topilmadi.</Alert></main>
  }

  function changePage(next) {
    setLoading(true)
    setPage(next)
  }

  return (
    <main className="dashboard-page">
      <PageHeading eyebrow={config.eyebrow} title={config.title} description={config.description} />
      {error && <Alert color="red" mb="lg">{error}</Alert>}
      <MediaGrid
        items={items}
        loading={loading}
        emptyTitle="Bo'sh"
        emptyDescription="Hozircha bu bo'limda media yo'q."
      />
      {!loading && count > PAGE_SIZE && (
        <Group justify="center" mt="xl" className="pagination-row">
          <Pagination total={Math.ceil(count / PAGE_SIZE)} value={page} onChange={changePage} />
        </Group>
      )}
    </main>
  )
}

export default CatalogSectionPage
