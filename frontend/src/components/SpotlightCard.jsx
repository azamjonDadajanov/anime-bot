import { Badge, Skeleton, Text } from '@mantine/core'
import { Link } from 'react-router-dom'
import { coverSrc } from '../apis/mediaUrl'

const typeLabels = {
  movie: 'Kino',
  anime: 'Anime',
  series: 'Serial',
  manga: 'Manga',
}

export function SpotlightCard({ item, kicker = 'Hafta marvaridi', icon = 'bi-fire' }) {
  if (!item) return null
  const cover = coverSrc(item)

  return (
    <Link
      className="home-spotlight"
      to={`/media/${item.slug}`}
      aria-label={`${item.title} tafsilotlarini ochish`}
    >
      <div className="home-spotlight-poster">
        {cover
          ? <img src={cover} alt={`${item.title} muqovasi`} />
          : <i className="bi bi-play-circle" aria-hidden="true" />}
        <span className="home-spotlight-glow" aria-hidden="true" />
      </div>
      <div className="home-spotlight-body">
        <span className="home-spotlight-kicker">
          <i className={`bi ${icon}`} aria-hidden="true" /> {kicker}
        </span>
        <Text className="home-spotlight-title">{item.title}</Text>
        <div className="home-spotlight-meta">
          <Badge variant="light">{typeLabels[item.type] || item.type}</Badge>
          <Text size="xs" c="dimmed">{item.release_year || 'Yil noma\'lum'}</Text>
          <Text size="xs" className="home-spotlight-rating">
            <i className="bi bi-star-fill" aria-hidden="true" /> {item.rating ?? '—'}/10
          </Text>
        </div>
        <span className="home-spotlight-cta">
          Batafsil <i className="bi bi-arrow-right" aria-hidden="true" />
        </span>
      </div>
    </Link>
  )
}

export function SpotlightSkeleton() {
  return (
    <div className="home-spotlight home-spotlight-skeleton" aria-hidden="true">
      <Skeleton className="home-spotlight-poster-skeleton" radius="lg" />
      <div className="home-spotlight-body">
        <Skeleton height={12} width="45%" radius="sm" />
        <Skeleton height={20} width="85%" radius="sm" />
        <Skeleton height={12} width="60%" radius="sm" />
      </div>
    </div>
  )
}

export default SpotlightCard
