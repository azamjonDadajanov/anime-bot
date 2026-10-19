import { useState, useEffect } from 'react'
import { Text, Skeleton } from '@mantine/core'
import { Link } from 'react-router-dom'
import { coverSrc } from '../apis/mediaUrl'

const typeLabels = {
  movie: 'Kino',
  anime: 'Anime',
  series: 'Serial',
  manga: 'Manga',
}

const statusLabels = {
  upcoming: 'Kutilmoqda',
  ongoing: 'Davom etmoqda',
  completed: 'Tugallangan',
}

function RailCard({ item }) {
  const cover = coverSrc(item)
  return (
    <Link className="rail-card" to={`/media/${item.slug}`} aria-label={`${item.title} tafsilotlarini ochish`}>
      <div className="rail-card-poster">
        {cover
          ? <img src={cover} alt={`${item.title} muqovasi`} loading="lazy" />
          : <i className="bi bi-film" aria-hidden="true" />}
      </div>
      <div className="rail-card-info">
        <div className="rail-card-top">
          <span className="rail-card-title" title={item.title}>{item.title}</span>
          <span className={`rail-card-status rail-card-status-${item.status}`}>
            {statusLabels[item.status] || item.status || 'Noma\'lum'}
          </span>
        </div>
        <span className="rail-card-parts">
          {item.episode_count ? `${item.episode_count} qism` : 'Qismlar yo\'q'}
        </span>
        <span className="rail-card-type">{typeLabels[item.type] || item.type}</span>
      </div>
    </Link>
  )
}

function RailSkeleton() {
  return (
    <div className="rail-track" aria-hidden="true">
      {Array.from({ length: 6 }).map((_, index) => (
        <div className="rail-card rail-card-skeleton" key={index}>
          <Skeleton height={270} />
          <div className="rail-card-info">
            <Skeleton height={14} radius="sm" />
            <Skeleton height={11} width="55%" radius="sm" />
          </div>
        </div>
      ))}
    </div>
  )
}

function MediaRail({ title, load, href }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    load()
      .then((data) => active && setItems(Array.isArray(data) ? data : data.results || []))
      .catch(() => active && setItems([]))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [load])

  if (loading) return <section className="rail"><RailSkeleton /></section>
  if (!items.length) return null

  return (
    <section className="rail">
      <div className="rail-head">
        <Text component="h2" className="rail-title">{title}</Text>
        {href && (
          <Link className="rail-more" to={href}>
            Barchasini ko'rish <i className="bi bi-arrow-right" aria-hidden="true" />
          </Link>
        )}
      </div>
      <div className="rail-track">
        {items.map((item) => <RailCard key={item.id} item={item} />)}
      </div>
    </section>
  )
}

export default MediaRail
