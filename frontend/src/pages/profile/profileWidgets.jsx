import { Link } from 'react-router-dom'
import { Text } from '@mantine/core'
import { formatDateTime, formatPrice, MEDIA_TYPE_LABELS } from './profileUtils'

export function StatTile({ icon, label, value, href }) {
  const body = (
    <>
      <span className="profile-stat-icon"><i className={`bi ${icon}`} aria-hidden="true" /></span>
      <span className="profile-stat-value">{value}</span>
      <span className="profile-stat-label">{label}</span>
    </>
  )
  if (href) {
    return <Link className="profile-stat" to={href}>{body}</Link>
  }
  return <div className="profile-stat">{body}</div>
}

export function ActivityList({ items, emptyTitle = "Faollik hozircha yo'q", emptyDescription }) {
  if (!items || items.length === 0) {
    return (
      <div className="empty-state compact-empty">
        <i className="bi bi-activity" aria-hidden="true" />
        <Text fw={600}>{emptyTitle}</Text>
        {emptyDescription && <Text c="dimmed" size="sm">{emptyDescription}</Text>}
      </div>
    )
  }

  return (
    <ul className="activity-list">
      {items.map((item) => (
        <li
          className="activity-item"
          key={`${item.kind}-${item.slug || item.title}-${item.at}`}
        >
          <span className={`activity-icon activity-icon-${item.kind}`}>
            <i className={`bi ${item.icon}`} aria-hidden="true" />
          </span>
          <div className="activity-body">
            <span className="activity-title">
              {item.slug
                ? <Link to={`/media/${item.slug}`}>{item.title}</Link>
                : item.title}
            </span>
            <span className="activity-meta">
              {item.label}
              {item.detail ? ` · ${item.detail}` : ''}
              {item.amount ? ` · ${formatPrice(item.amount)}` : ''}
            </span>
          </div>
          {MEDIA_TYPE_LABELS[item.type] && (
            <span className="activity-type">{MEDIA_TYPE_LABELS[item.type]}</span>
          )}
          <time className="activity-time" dateTime={item.at}>{formatDateTime(item.at)}</time>
        </li>
      ))}
    </ul>
  )
}
