import { Alert, Button, Group, Loader, Text, Title } from '@mantine/core'
import { profileApi } from '../../apis/api'
import { ActivityList } from './profileWidgets'
import { useApi } from './useApi'

export function ProfileActivityPage() {
  const { data, loading, error, reload } = useApi(() => profileApi.activity(), 'activity')

  return (
    <section className="profile-edit-panel">
      <Group justify="space-between" align="center" mb="md">
        <div>
          <Text className="section-kicker">OXIRGI FAOLLIKLAR</Text>
          <Title order={2} mt={8}>Faollik tarixi</Title>
          <Text c="dimmed" size="sm" mt={4}>
            Sevimlilar, botda va saytda ochilgan medialar hamda obuna to'lovlari.
          </Text>
        </div>
        <Button
          variant="light"
          size="compact-sm"
          loading={loading}
          onClick={reload}
          leftSection={<i className="bi bi-arrow-clockwise" aria-hidden="true" />}
        >
          Yangilash
        </Button>
      </Group>

      {loading && <div className="page-loader"><Loader /></div>}
      {error && <Alert color="red">{error}</Alert>}
      {!loading && !error && (
        <ActivityList
          items={data.results}
          emptyTitle="Hozircha faollik yo'q"
          emptyDescription="Botda media ochsangiz yoki sevimlilarga qo'shsangiz, tarix shu yerda to'planadi."
        />
      )}
    </section>
  )
}

export default ProfileActivityPage
