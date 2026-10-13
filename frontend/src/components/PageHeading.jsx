import { Text, Title } from '@mantine/core'

function PageHeading({ eyebrow, title, description }) {
  return (
    <div className="page-heading">
      <Text className="eyebrow">{eyebrow}</Text>
      <Title order={1}>{title}</Title>
      {description && <Text c="dimmed">{description}</Text>}
    </div>
  )
}

export default PageHeading