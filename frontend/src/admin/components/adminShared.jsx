import { Badge, Group, Stack, Text, Title } from '@mantine/core'

export { MEDIA_TYPE_LABELS, PLAN_LABELS, PLAN_COLORS, ACCESS_PLAN_LABELS, INCOME_SOURCE_LABELS, INCOME_METHOD_LABELS, BROADCAST_STATUS_LABELS, BROADCAST_KIND_LABELS, REQUEST_STATUS_LABELS, CHANNEL_PURPOSE_LABELS, COUPON_STATUS_LABELS, COUPON_STATUS_COLORS } from './adminLabels'

export function StatCard({ title, value, icon, color = 'blue', hint }) {
  return (
    <div className="admin-stat-card">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Stack gap={4}>
          <Text size="sm" c="dimmed">{title}</Text>
          <Title order={2}>{value}</Title>
          {hint ? <Text size="xs" c="dimmed">{hint}</Text> : null}
        </Stack>
        {icon ? (
          <div className={`admin-stat-icon admin-stat-icon-${color}`}>
            <i className={`bi ${icon}`} aria-hidden="true" />
          </div>
        ) : null}
      </Group>
    </div>
  )
}

export function EmptyState({ icon = 'bi-inbox', title, description, action }) {
  return (
    <div className="admin-empty">
      <i className={`bi ${icon}`} aria-hidden="true" />
      <Title order={4}>{title}</Title>
      {description ? <Text c="dimmed" size="sm">{description}</Text> : null}
      {action}
    </div>
  )
}

export function StatusBadge({ status, labels = {}, color }) {
  const label = labels[status] || status
  return (
    <Badge variant="light" color={color || undefined}>
      {label}
    </Badge>
  )
}

export function SectionHeading({ title, description, actions }) {
  return (
    <Group justify="space-between" align="flex-start" mb="md" wrap="wrap">
      <Stack gap={2}>
        <Title order={2}>{title}</Title>
        {description ? <Text c="dimmed" size="sm">{description}</Text> : null}
      </Stack>
      {actions ? <Group gap="xs">{actions}</Group> : null}
    </Group>
  )
}

export function PaginationBar({ page, totalPages, count, onChange, loading }) {
  if (totalPages <= 1 && !count) return null
  return (
    <Group justify="space-between" mt="md" className="admin-pagination">
      <Text size="sm" c="dimmed">
        {count} ta yozuv · {page}/{totalPages}
      </Text>
      <Group gap="xs">
        <button
          type="button"
          className="admin-btn admin-btn-secondary"
          disabled={page <= 1 || loading}
          onClick={() => onChange(page - 1)}
        >
          ← Oldingi
        </button>
        <button
          type="button"
          className="admin-btn admin-btn-secondary"
          disabled={page >= totalPages || loading}
          onClick={() => onChange(page + 1)}
        >
          Keyingi →
        </button>
      </Group>
    </Group>
  )
}

export function ErrorAlert({ children }) {
  if (!children) return null
  return (
    <div className="admin-alert admin-alert-error" role="alert">
      <i className="bi bi-exclamation-triangle" aria-hidden="true" />
      <span>{children}</span>
    </div>
  )
}

export function SuccessAlert({ children }) {
  if (!children) return null
  return (
    <div className="admin-alert admin-alert-success" role="status">
      <i className="bi bi-check-circle" aria-hidden="true" />
      <span>{children}</span>
    </div>
  )
}

export function ConfirmDialog({ open, title, message, confirmLabel = 'Ha', cancelLabel = 'Bekor', onConfirm, onCancel, loading, danger, children }) {
  if (!open) return null
  return (
    <div className="admin-modal-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="admin-modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <Title order={4} mb="xs">{title}</Title>
        <Text c="dimmed" size="sm" mb="lg">{message}</Text>
        {children}
        <Group justify="flex-end" mt="md">
          <button type="button" className="admin-btn admin-btn-secondary" onClick={onCancel} disabled={loading}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`admin-btn ${danger ? 'admin-btn-danger' : 'admin-btn-primary'}`}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? 'Kuting…' : confirmLabel}
          </button>
        </Group>
      </div>
    </div>
  )
}

