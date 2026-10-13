import { Alert, Badge, Button, Group, Loader, Text, Title } from '@mantine/core'
import { profileApi } from '../../apis/api'
import { useAuth } from '../../apis/useAuth'
import { useApi } from './useApi'
import { formatDate, formatDateTime, TELEGRAM_BOT_URL } from './profileUtils'

export function ProfileTelegramPage() {
  const { user } = useAuth()
  const { data, loading, error } = useApi(() => profileApi.overview(), user?.id)

  if (loading) return <div className="page-loader"><Loader /></div>
  if (error) return <Alert color="red">{error}</Alert>

  const { telegram, stats } = data

  return (
    <div className="profile-sections">
      <section className="profile-info-panel">
        <Group justify="space-between" align="center">
          <Text className="section-kicker">TELEGRAM AKKAUNT</Text>
          <Badge color={telegram.linked ? 'green' : 'gray'} variant="light">
            {telegram.linked ? 'Botga ulangan' : 'Ulanmagan'}
          </Badge>
        </Group>
        <Title order={2}>Botga ulangan profil</Title>

        {telegram.linked ? (
          <>
            <div className="profile-row"><Text c="dimmed">Telegram ID</Text><Text fw={600}>{telegram.telegram_id}</Text></div>
            <div className="profile-row"><Text c="dimmed">Foydalanuvchi nomi</Text><Text fw={600}>{telegram.username ? `@${telegram.username}` : 'Belgilanmagan'}</Text></div>
            <div className="profile-row"><Text c="dimmed">Ism-familiya</Text><Text fw={600}>{telegram.full_name || '—'}</Text></div>
            <div className="profile-row"><Text c="dimmed">Interfeys tili</Text><Text fw={600}>{telegram.language_code || '—'}</Text></div>
            <div className="profile-row"><Text c="dimmed">Botga qo'shilgan</Text><Text fw={600}>{formatDate(telegram.joined_at)}</Text></div>
            <div className="profile-row"><Text c="dimmed">Oxirgi faollik</Text><Text fw={600}>{formatDateTime(telegram.last_seen_at)}</Text></div>
            <div className="profile-row">
              <Text c="dimmed">Botni bloklaganmi</Text>
              <Text fw={600}>{telegram.is_blocked ? 'Ha' : "Yo'q"}</Text>
            </div>
          </>
        ) : (
          <Text c="dimmed" mt="md">
            Bu hisob hali Telegram botga ulanmagan. <b>Botni ochish</b> tugmasini bosing —
            bot ochiladi va akkaunt avtomatik sayt hisobingizga ulanadi.
          </Text>
        )}

        <Button
          component="a"
          href={TELEGRAM_BOT_URL+`?start=${user.username}`}
          target="_blank"
          rel="noreferrer"
          mt="xl"
          leftSection={<i className="bi bi-telegram" aria-hidden="true" />}
        >
          Botni ochish
        </Button>
      </section>

      <section className="profile-info-panel">
        <Text className="section-kicker">BOTDAGI FAOLLIK</Text>
        <Title order={2}>Bot bilan bog'liq raqamlar</Title>
        <div className="profile-row"><Text c="dimmed">Sevimlilar</Text><Text fw={600}>{stats.favorites} ta</Text></div>
        <div className="profile-row"><Text c="dimmed">Botda ochilgan medialar</Text><Text fw={600}>{stats.views} ta</Text></div>
        <div className="profile-row"><Text c="dimmed">O'qish tarixi yozuvlari</Text><Text fw={600}>{stats.reading} ta</Text></div>
        <Text c="dimmed" size="sm" mt="lg">
          Botda media ochganingizda tarix avtomatik yangilanadi — saytdagi «Ko'rganlarim»
          bo'limida ham ko'rinadi.
        </Text>
      </section>
    </div>
  )
}

export default ProfileTelegramPage
