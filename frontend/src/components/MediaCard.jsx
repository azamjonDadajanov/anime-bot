import { Link } from 'react-router-dom'
import { coverSrc } from '../apis/mediaUrl'
import { episodeLabel, genreNames, releaseLabel, typeIcon, typeLabel } from '../mediaMeta'

function MediaCard({ item }) {
  const cover = coverSrc(item)
  const genres = genreNames(item)

  return (
    <Link className="poster-card" to={`/media/${item.slug}`} aria-label={`${item.title} tafsilotlarini ochish`}>
      <span className="poster-frame">
        {cover
          ? <img src={cover} alt={`${item.title} muqovasi`} loading="lazy" decoding="async" />
          : <span className="poster-fallback"><i className={`bi ${typeIcon(item)}`} aria-hidden="true" /></span>}
        <span className="poster-sheen" aria-hidden="true" />
        <span className="poster-badge">{typeLabel(item)}</span>
        {item.rating ? (
          <span className="poster-rating">
            <i className="bi bi-star-fill" aria-hidden="true" /> {item.rating}
          </span>
        ) : null}
        {item.status === 'upcoming'
          ? <span className="poster-progress">Kutilmoqda</span>
          : (
            <span className="poster-action" aria-hidden="true">
              <i className="bi bi-play-fill" />
            </span>
          )}
      </span>
      <span className="poster-body">
        <span className="poster-title" title={item.title}>{item.title}</span>
        <span className="poster-meta">
          <span>{releaseLabel(item)}</span>
          <span className="dot" aria-hidden="true" />
          <span>{episodeLabel(item)}</span>
        </span>
        {genres.length > 0 && (
          <span className="poster-genres">{genres.slice(0, 2).join(' · ')}</span>
        )}
      </span>
    </Link>
  )
}

export default MediaCard
