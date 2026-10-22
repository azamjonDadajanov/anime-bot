import MediaCard from './MediaCard'

function GridSkeleton() {
  return (
    <div className="poster-grid" aria-hidden="true">
      {Array.from({ length: 10 }).map((_, index) => (
        <div className="poster-card poster-card-skeleton" key={index}>
          <span className="poster-frame" />
          <span className="poster-body">
            <span className="ac-skeleton ac-skeleton-line" style={{ width: '78%' }} />
            <span className="ac-skeleton ac-skeleton-line" style={{ width: '46%', height: 8 }} />
          </span>
        </div>
      ))}
    </div>
  )
}

function MediaGrid({ items, loading, emptyTitle, emptyDescription, emptyAction }) {
  if (loading) return <GridSkeleton />

  if (!items.length) {
    return (
      <div className="empty-state">
        <i className="bi bi-collection-play" aria-hidden="true" />
        <h2>{emptyTitle || "Bu yerda hozircha bo'sh"}</h2>
        {emptyDescription && <p>{emptyDescription}</p>}
        {emptyAction}
      </div>
    )
  }

  return (
    <div className="poster-grid">
      {items.map((item) => <MediaCard key={item.id} item={item} />)}
    </div>
  )
}

export default MediaGrid
