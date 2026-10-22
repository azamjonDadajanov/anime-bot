import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { coverSrc } from '../apis/mediaUrl'
import { normalizeList, statusLabel, typeLabel } from '../mediaMeta'
import SectionHead from './SectionHead'

function RailCard({ item, index }) {
  const cover = coverSrc(item)
  return (
    <Link className="rail-card" to={`/media/${item.slug}`} aria-label={`${item.title} tafsilotlarini ochish`}>
      <span className="rail-card-poster">
        {cover
          ? <img src={cover} alt={`${item.title} muqovasi`} loading="lazy" decoding="async" />
          : <i className="bi bi-film" aria-hidden="true" />}
        <span className="rail-card-index">{String(index + 1).padStart(2, '0')}</span>
        {item.status && (
          <span className={`rail-card-status rail-card-status-${item.status}`}>{statusLabel(item)}</span>
        )}
      </span>
      <span className="rail-card-info">
        <span className="rail-card-title" title={item.title}>{item.title}</span>
        <span className="rail-card-meta">
          <span>{typeLabel(item)}</span>
          {item.rating ? (
            <>
              <span aria-hidden="true">·</span>
              <i className="bi bi-star-fill" aria-hidden="true" /> {item.rating}
            </>
          ) : null}
        </span>
      </span>
    </Link>
  )
}

function RailSkeleton() {
  return (
    <div className="rail-track" aria-hidden="true">
      {Array.from({ length: 6 }).map((_, index) => (
        <div className="rail-card rail-skeleton" key={index}>
          <div className="ac-skeleton ac-skeleton-poster" />
          <div className="rail-card-info">
            <div className="ac-skeleton ac-skeleton-line" style={{ width: '82%' }} />
            <div className="ac-skeleton ac-skeleton-line" style={{ width: '48%', height: 8 }} />
          </div>
        </div>
      ))}
    </div>
  )
}

/**
 * Horizontal poster rail. `items` renders immediately (homepage, related
 * titles); `load` keeps the original catalogue-sections behaviour.
 */
function MediaRail({ title, jp, index, description, load, href, linkLabel, items: provided, loading: providedLoading }) {
  const [items, setItems] = useState(provided || [])
  const [loading, setLoading] = useState(providedLoading ?? !provided)

  useEffect(() => {
    if (provided || !load) return undefined
    let active = true
    setLoading(true)
    load()
      .then((data) => active && setItems(normalizeList(data)))
      .catch(() => active && setItems([]))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [load, provided])

  useEffect(() => {
    if (provided) setItems(provided)
  }, [provided])

  if (loading) {
    return (
      <section className="rail">
        {title && <SectionHead index={index} title={title} jp={jp} description={description} href={href} linkLabel={linkLabel} />}
        <RailSkeleton />
      </section>
    )
  }

  if (!items.length) return null

  return (
    <section className="rail" aria-label={title}>
      <SectionHead index={index} title={title} jp={jp} description={description} href={href} linkLabel={linkLabel} />
      <div className="rail-track">
        {items.map((item, position) => <RailCard key={item.id} item={item} index={position} />)}
      </div>
    </section>
  )
}

export default MediaRail
