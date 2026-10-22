import { Link } from 'react-router-dom'
import { coverSrc } from '../apis/mediaUrl'
import { genreNames, releaseLabel, typeLabel } from '../mediaMeta'

export function SpotlightCard({ item, kicker = 'Hafta marvaridi', icon = 'bi-fire' }) {
  if (!item) return null
  const cover = coverSrc(item)
  const genres = genreNames(item)

  return (
    <Link
      className="spotlight"
      to={`/media/${item.slug}`}
      aria-label={`${item.title} tafsilotlarini ochish`}
    >
      <span className="spotlight-poster">
        {cover
          ? <img src={cover} alt={`${item.title} muqovasi`} loading="lazy" decoding="async" />
          : <i className="bi bi-play-circle" aria-hidden="true" />}
        <span className="spotlight-shade" aria-hidden="true" />
        <span className="spotlight-kicker">
          <i className={`bi ${icon}`} aria-hidden="true" /> {kicker}
        </span>
        <span className="spotlight-body">
          <span className="spotlight-title" title={item.title}>{item.title}</span>
          <span className="spotlight-meta">
            <span>{typeLabel(item)}</span>
            <span className="dot" aria-hidden="true" />
            <span>{releaseLabel(item)}</span>
            {item.rating ? (
              <>
                <span className="dot" aria-hidden="true" />
                <span><i className="bi bi-star-fill" aria-hidden="true" /> {item.rating}</span>
              </>
            ) : null}
            {genres.length > 0 && (
              <>
                <span className="dot" aria-hidden="true" />
                <span>{genres.slice(0, 2).join(' · ')}</span>
              </>
            )}
          </span>
          <span className="spotlight-cta">
            Batafsil <i className="bi bi-arrow-up-right" aria-hidden="true" />
          </span>
        </span>
      </span>
    </Link>
  )
}

export function SpotlightSkeleton() {
  return (
    <div className="spotlight spotlight-skeleton" aria-hidden="true">
      <span className="spotlight-poster">
        <span className="ac-skeleton" />
      </span>
    </div>
  )
}

export default SpotlightCard
