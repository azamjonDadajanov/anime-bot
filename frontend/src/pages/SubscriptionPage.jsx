import { useEffect, useMemo, useState } from 'react'
import { Alert, Badge, Button, FileButton, Group, Loader, Text, Title } from '@mantine/core'
import { useAuth } from '../apis/useAuth'
import { subscriptionApi } from '../apis/api'
import PageHeading from '../components/PageHeading'

const STATUS_LABELS = {
  pending: 'Ko\'rib chiqilmoqda',
  approved: 'Obuna tasdiqlandi',
  rejected: 'Ariza rad etildi',
  cancelled: 'Bekor qilindi',
}

const STATUS_COLORS = {
  pending: 'yellow',
  approved: 'green',
  rejected: 'red',
  cancelled: 'gray',
}

function formatPrice(value) {
  const amount = Number(value) || 0
  if (amount <= 0) return 'Bepul'
  return `${amount.toLocaleString('uz-UZ')} so'm`
}

function errorText(error) {
  const data = error.response?.data
  if (!data) return 'Server bilan bog\'lanishda xatolik yuz berdi.'
  if (typeof data.detail === 'string') return data.detail
  return Object.values(data).flat().map(String).join(' ')
}

export function SubscriptionPage() {
  const { user, refreshUser } = useAuth()
  const subscription = user?.subscription
  const currentPlan = subscription?.plan || 'free'
  const currentActive = Boolean(subscription?.is_active)
  const currentExpiresAt = subscription?.expires_at || null

  const [plans, setPlans] = useState([])
  const [cardNumber, setCardNumber] = useState('')
  const [pendingRequest, setPendingRequest] = useState(null)
  const [activePlan, setActivePlan] = useState(currentActive)
  const [expiresAt, setExpiresAt] = useState(currentExpiresAt)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')

  const [selectedPlan, setSelectedPlan] = useState(null)
  const [screenshot, setScreenshot] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState('')
  const [formError, setFormError] = useState('')

  async function loadPlans() {
    setLoading(true)
    setLoadError('')
    try {
      const data = await subscriptionApi.plans()
      setPlans(data.plans || [])
      setCardNumber(data.card_number || '')
      setPendingRequest(data.pending_request || null)
      setActivePlan(Boolean(data.current_active))
      setExpiresAt(data.expires_at || null)
    } catch (error) {
      setLoadError(errorText(error))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadPlans()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPlan, currentActive])

  const selected = useMemo(
    () => plans.find((item) => item.id === selectedPlan) || null,
    [plans, selectedPlan],
  )

  const currentLabel = subscription?.plan_label
    || plans.find((item) => item.id === currentPlan)?.label
    || 'Bepul'

  function startPurchase(planId) {
    if (planId === currentPlan && activePlan) return
    setSelectedPlan(planId)
    setScreenshot(null)
    setMessage('')
    setFormError('')
  }

  async function submitRequest() {
    if (!selected || !screenshot) return
    setSubmitting(true)
    setMessage('')
    setFormError('')
    try {
      await subscriptionApi.submit({ plan: selected.id, screenshot })
      setScreenshot(null)
      setSelectedPlan(null)
      setMessage('Ariza yuborildi! Administrator tasdiqlashini kuting.')
      if (refreshUser) await refreshUser()
      await loadPlans()
    } catch (error) {
      setFormError(errorText(error))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="dashboard-page">
      <PageHeading
        eyebrow="HISOB / TARIF"
        title="Obuna"
        description="Har bir tarifning imkoniyatlarini ko'ring va kerakli tarifga o'ting."
      />

      {loading && (
        <div className="page-loader">
          <Loader size="sm" />
        </div>
      )}

      {loadError && <Alert color="red" mb="lg">{loadError}</Alert>}
      {!loading && !loadError && plans.length === 0 && (
        <Alert color="yellow" mb="lg">Tariflar topilmadi.</Alert>
      )}

      {!loading && !loadError && (
        <Alert
          color={activePlan ? 'blue' : 'gray'}
          mb="lg"
          icon={<i className={activePlan ? 'bi bi-stars' : 'bi bi-person'} aria-hidden="true" />}
        >
          Joriy tarif: <b>{currentLabel}</b>
          {activePlan && expiresAt
            ? ` · ${new Date(expiresAt).toLocaleDateString()} gacha amal qiladi`
            : ''}
          {!activePlan && currentPlan !== 'free' ? " · muddati o'tgan" : ''}
        </Alert>
      )}

      {pendingRequest && (
        <Alert
          color={STATUS_COLORS[pendingRequest.status] || 'blue'}
          icon={<i className="bi bi-hourglass-split" aria-hidden="true" />}
          mb="lg"
        >
          <b>{pendingRequest.plan_label || pendingRequest.plan}</b> tarifi uchun arizangiz
          {' '}{STATUS_LABELS[pendingRequest.status] || pendingRequest.status}.
        </Alert>
      )}

      {!loading && plans.length > 0 && (
        <section className="plan-list" aria-label="Obuna tariflari">
          {plans.map((item, index) => {
            const isCurrent = item.id === currentPlan && activePlan
            const isPending = Boolean(
              pendingRequest && pendingRequest.plan === item.id && pendingRequest.status === 'pending',
            )
            return (
              <article
                className={`plan-row${isCurrent ? ' plan-row-current' : ''}`}
                key={item.id}
              >
                <div className="plan-number">0{index + 1}</div>
                <div className="plan-details">
                  <Group gap="sm" mb={6}>
                    <Title order={3}>{item.label}</Title>
                    {isCurrent && <Badge color="blue">Joriy tarif</Badge>}
                    {isPending && <Badge color="yellow">Ko'rib chiqilmoqda</Badge>}
                    <Badge variant="light" color="teal">{formatPrice(item.price)}</Badge>
                    {item.days ? (
                      <Badge variant="outline" color="gray">{item.days} kun</Badge>
                    ) : null}
                  </Group>
                  <Text c="dimmed" size="sm">{item.description}</Text>
                  {item.price_per_day ? (
                    <Text c="dimmed" size="xs">
                      Kuniga taxminan {formatPrice(item.price_per_day)}
                    </Text>
                  ) : null}
                  <div className="plan-features">
                    {(item.features || []).map((feature) => (
                      <span className="plan-feature" key={feature.type}>
                        <i className="bi bi-check-circle-fill" aria-hidden="true" />
                        <b>{feature.display}</b> {feature.label}
                      </span>
                    ))}
                  </div>
                  {!isCurrent && (
                    <Button
                      size="xs"
                      mt="md"
                      variant={selectedPlan === item.id ? 'filled' : 'light'}
                      loading={submitting && selectedPlan === item.id}
                      disabled={isPending}
                      onClick={() => startPurchase(item.id)}
                    >
                      {isPending ? 'Ariza yuborilgan' : `Tanlash — ${formatPrice(item.price)}`}
                    </Button>
                  )}
                </div>
                <i
                  className={`bi ${isCurrent ? 'bi-check-circle-fill' : 'bi-circle'} plan-check`}
                  aria-hidden="true"
                />
              </article>
            )
          })}
        </section>
      )}

      {selected && (
        <section className="subscription-payment" aria-label="To'lov yo'riqnomasi">
          <Text className="section-kicker">TO'LOV YO'RIQNOMASI</Text>
          <Title order={2} mb="sm">{selected.label} tarifiga to'lov</Title>
          <Text size="sm" c="dimmed" mb="lg">
            Summa: <b>{formatPrice(selected.price)}</b>
            {selected.days ? ` · ${selected.days} kun` : ''}
          </Text>

          {message && <Alert color="green" mb="md">{message}</Alert>}
          {formError && <Alert color="red" mb="md">{formError}</Alert>}

          <ol className="payment-steps">
            <li>
              Quyidagi karta raqamiga <b>{formatPrice(selected.price)}</b> miqdorida pul tashlang:
              <div className="payment-card">
                <i className="bi bi-credit-card" aria-hidden="true" />
                <code>{cardNumber || 'Karta raqami kiritilmagan'}</code>
                {cardNumber && (
                  <Button
                    size="compact-xs"
                    variant="light"
                    onClick={() => navigator.clipboard?.writeText(cardNumber)}
                  >
                    Nusxalash
                  </Button>
                )}
              </div>
            </li>
            <li>To'lov qilganingizdan so'ng screenshot (rasm) oling.</li>
            <li>Quyidan screenshotni tanlang va yuboring.</li>
            <li>Administrator tasdiqlashini kuting — javob shu sahifada ko'rinadi.</li>
          </ol>

          <Group mt="md" align="flex-end">
            <FileButton
              onChange={setScreenshot}
              accept="image/png,image/jpeg,image/webp"
            >
              {(props) => (
                <Button variant="light" {...props}>
                  {screenshot ? screenshot.name : 'Screenshot tanlash'}
                </Button>
              )}
            </FileButton>
            <Button
              onClick={submitRequest}
              loading={submitting}
              disabled={!screenshot || !cardNumber}
            >
              Yuborish
            </Button>
            <Button
              variant="subtle"
              color="gray"
              onClick={() => {
                setSelectedPlan(null)
                setScreenshot(null)
                setFormError('')
              }}
            >
              Bekor qilish
            </Button>
          </Group>

          {submitting && (
            <Text size="sm" c="dimmed" mt="sm">Yuborilmoqda...</Text>
          )}
        </section>
      )}
    </main>
  )
}

export default SubscriptionPage
