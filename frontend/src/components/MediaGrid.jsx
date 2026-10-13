import { SimpleGrid, Loader, Title, Text } from '@mantine/core'
import MediaCard from './MediaCard'

function MediaGrid({ items, loading, emptyTitle, emptyDescription }) {
  if (loading) return <div className="page-loader"><Loader /></div>
  if (!items.length) {
    return (
      <div className="empty-state">
        <i className="bi bi-collection-play" aria-hidden="true" />
        <Title order={3}>{emptyTitle}</Title>
        <Text c="dimmed">{emptyDescription}</Text>
      </div>
    )
  }
  return (
    <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
      {items.map((item) => <MediaCard key={item.id} item={item} />)}
    </SimpleGrid>
  )
}

export default MediaGrid