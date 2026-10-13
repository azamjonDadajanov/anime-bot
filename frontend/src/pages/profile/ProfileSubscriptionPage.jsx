import { Alert, Badge, Button, Group, Loader, Text, Title } from '@mantine/core'
import { Link } from 'react-router-dom'
import { profileApi } from '../../apis/api'
import { useAuth } from '../../apis/useAuth'
import { useApi } from './useApi'
import { formatDate, formatDateTime, formatPrice, PLAN_STATUS_COLORS, PLAN_STATUS_LABELS } from './profileUtils'

export function ProfileSubscriptionPage() {
  const { user } = useAuth()
  const { data, loading, error } = useApi(() => profileApi.subscription(), user?.id)

  if (loading) return <div className="page-loader"><Loader /></div>
  if (error) return <Alert color="red">{error}</Alert>

  const { summary, requests } = data

  return (
    <div className="profile-sections">
      <section className="profile-info-panel">
        <Group justify="space-between" align="center">
          <Text className="section-kicker">OBUNA HOLATI</Text>
          <Badge color={summary.is_active ? 'blue' : 'gray'} variant="light">
            {summary.is_active ? 'Faol' : summary.is_paid ? "Muddati o'tgan" : 'Bepul tarif'}
          </Badge>
        </Group>
        <Title order={2}>{summary.plan_label} tarifi</Title>

        {summary.expires_soon && (
          <Alert color="yellow" mt="lg" icon={<i className="bi bi-exclamation-triangle" aria-hidden="true" />}>
            Obuna {summary.days_left} kundan keyin tugaydi. Uzaytirish uchun yangi to'lov yuboring.
          </Alert>
        )}

        <div className="profile-row"><Text c="dimmed">Tarif narxi</Text><Text fw={600}>{formatPrice(summary.last_amount)}</Text></div>
        <div className="profile-row">
          <Text c="dimmed">Amal qilish muddati</Text>
          <Text fw={600}>
            {summary.started_at ? `${formatDate(summary.started_at)} — ${formatDate(summary.expires_at)}` : 'Muddat belgilanmagan'}
          </Text>
        </div>
        <div className="profile-row">
          <Text c="dimmed">Tugashiga qolgan kun</Text>
          <Text fw={600}>{summary.days_left === null ? '—' : `${summary.days_left} kun`}</Text>
        </div>
        <div className="profile-row"><Text c="dimmed">Jami to'langan</Text><Text fw={600}>{formatPrice(summary.total_paid)}</Text></div>
        <div className="profile-row"><Text c="dimmed">Tasdiqlangan to'lovlar</Text><Text fw={600}>{summary.payments_count} ta</Text></div>
        <div className="profile-row"><Text c="dimmed">To'lov davri</Text><Text fw={600}>{summary.period_days} kun</Text></div>

        <Button
          component={Link}
          to="/subscription"
          mt="xl"
          leftSection={<i className="bi bi-arrow-up-circle" aria-hidden="true" />}
        >
          Tarifni o'zgartirish yoki uzaytirish
        </Button>
      </section>

      <section className="profile-edit-panel">
        <Text className="section-kicker">TO'LOVLAR TARIXI</Text>
        <Title order={2}>Arizalar va to'lovlar</Title>
        {requests.length === 0 ? (
          <div className="empty-state compact-empty">
            <i className="bi bi-receipt" aria-hidden="true" />
            <Text fw={600}>Hozircha to'lov yo'q</Text>
            <Text c="dimmed" size="sm">Obuna tarifini tanlab, to'lov arizasini yuboring.</Text>
          </div>
        ) : (
          <ul className="payment-list">
            {requests.map((request) => (
              <li className="payment-row" key={request.id}>
                <span className="payment-row-icon">
                  <i className="bi bi-credit-card-2-front" aria-hidden="true" />
                </span>
                <div className="payment-row-body">
                  <Text fw={700}>{request.plan?.toUpperCase()} tarifi</Text>
                  <Text c="dimmed" size="xs">
                    Ariza: {formatDateTime(request.created_at)}
                    {request.updated_at !== request.created_at ? ` · Yangilangan: ${formatDateTime(request.updated_at)}` : ''}
                  </Text>
                  {request.notes && <Text size="xs" c="dimmed">Izoh: {request.notes}</Text>}
                </div>
                <div className="payment-row-side">
                  <Text fw={700}>{formatPrice(request.amount)}</Text>
                  <Badge color={PLAN_STATUS_COLORS[request.status] || 'gray'} variant="light">
                    {PLAN_STATUS_LABELS[request.status] || request.status}
                  </Badge>
                  {request.screenshot && (
                    <a className="text-link" href={request.screenshot} target="_blank" rel="noreferrer">
                      Chekni ko'rish
                    </a>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

export default ProfileSubscriptionPage
