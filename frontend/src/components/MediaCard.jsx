import { Text, Badge, Title } from '@mantine/core'
import { Link } from 'react-router-dom'

const mediaTypeLabels = {
  movie: 'Kino',
  anime: 'Anime',
  series: 'Serial',
  manga: 'Manga',
  podcast: 'Podcast',
}

function MediaCard({ item }) {
  const cover = item.cover
    ? `data:${item.cover_content_type || 'image/jpeg'};base64,${item.cover}`
    : ''

  return (
    <Link className="media-card" to={`/media/${item.slug}`} aria-label={`${item.title} tafsilotlarini ochish`}>
      <div className="media-poster">
        {cover
          ? <img src={cover} alt={`${item.title} muqovasi`} loading="lazy" />
          : <i className="bi bi-film" aria-hidden="true" />}
        <Badge className="media-type" variant="light">{mediaTypeLabels[item.type] || item.type}</Badge>
      </div>
      <div className="media-card-copy">
        <Text className="media-year">{item.release_year || 'Yil ko\'rsatilmagan'}</Text>
        <Title order={3}>{item.title}</Title>
        <Text className="media-description" c="dimmed" lineClamp={2}>
          {item.synopsis || 'Ushbu media uchun tavsif kiritilmagan.'}
        </Text>
        {item.genres?.length > 0 && (
          <Text className="media-genres" lineClamp={1}>{item.genres.join(' · ')}</Text>
        )}
      </div>
    </Link>
  )
}

export default MediaCard