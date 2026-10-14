import { useState } from 'react'
import { Alert, Group, Loader, Pagination, Text, Title } from '@mantine/core'
import { Link } from 'react-router-dom'
import { profileApi } from '../../apis/api'
import { useApi } from './useApi'
import { coverUrl, formatDateTime, MEDIA_TYPE_LABELS } from './profileUtils'

const PER_PAGE = 12

function partLabel(item) {
  if (!item.part_number) return ''
  const season = item.season_number ? `${item.season_number}-fasl, ` : ''
  return ` · ${season}${item.part_number}-qism`
}

export function ProfileHistoryPage() {
  const [page, setPage] = useState(1)
  const { data, loading, error } = useApi(() => profileApi.history({ page }), `history-${page}`)

  const items = data?.results || []
  const total = data?.count || 0

  return (
    <section className="profile-edit-panel">
      <Group justify="space-between" align="center" mb="lg">
        <div>
          <Text className="section-kicker">OXIRGI KO'RGAN MEDIALAR</Text>
          <Title order={2} mt={8}>Tomosha va o'qish tarixi</Title>
          <Text c="dimmed" size="sm" mt={4}>
            Botda ochilgan va saytda ko'rilgan medialar, eng yangisidan boshlab.
          </Text>
        </div>
        <Text c="dimmed" size="sm">{total} ta media</Text>
      </Group>

      {loading && <div className="page-loader"><Loader /></div>}
      {error && <Alert color="red">{error}</Alert>}

      {!loading && !error && items.length === 0 && (
        <div className="empty-state">
          <i className="bi bi-clock-history" aria-hidden="true" />
          <Text fw={600}>Tarix hozircha bo'sh</Text>
          <Text c="dimmed" size="sm">
            Botdan yoki saytdan biror media ochsangiz, u shu ro'yxatda paydo bo'ladi.
          </Text>
        </div>
      )}

      {items.length > 0 && (
        <div className="history-grid">
          {items.map((item) => {
            const cover = coverUrl(item)
            const isRead = item.kind === 'read'
            return (
              <article className="history-card" key={item.view_id}>
                <Link className="history-poster" to={`/media/${item.slug}`} aria-label={item.title}>
                  {cover
                    ? <img src={cover} alt={`${item.title} muqovasi`} loading="lazy" />
                    : <i className="bi bi-film" aria-hidden="true" />}
                  <span className={`history-kind history-kind-${item.kind}`}>
                    {isRead ? "O'qildi" : "Ko'rildi"}
                  </span>
                  {item.view_count > 1 && (
                    <span className="history-count">{item.view_count}×</span>
                  )}
                </Link>
                <div className="history-body">
                  <Link className="history-title" to={`/media/${item.slug}`}>{item.title}</Link>
                  <Text className="history-meta" size="xs" c="dimmed">
                    {MEDIA_TYPE_LABELS[item.type] || item.type}
                    {partLabel(item)}
                    {item.source === 'bot' ? ' · Bot' : ' · Sayt'}
                  </Text>
                  <Text className="history-time" size="xs" c="dimmed">
                    <i className="bi bi-clock" aria-hidden="true" /> {formatDateTime(item.viewed_at)}
                  </Text>
                  <Link
                    className="history-continue"
                    to={isRead
                      ? `/read/${item.slug}${item.part_number ? `/${item.part_number}` : ''}`
                      : `/media/${item.slug}`}
                  >
                    {isRead
                      ? <><i className="bi bi-book-half" aria-hidden="true" /> O'qishni davom ettirish</>
                      : <><i className="bi bi-play-fill" aria-hidden="true" /> Qismlarni ko'rish</>}
                  </Link>
                </div>
              </article>
            )
          })}
        </div>
      )}

      {total > PER_PAGE && (
        <Group justify="center" mt="xl">
          <Pagination total={Math.ceil(total / PER_PAGE)} value={page} onChange={setPage} />
        </Group>
      )}
    </section>
  )
}

export default ProfileHistoryPage
