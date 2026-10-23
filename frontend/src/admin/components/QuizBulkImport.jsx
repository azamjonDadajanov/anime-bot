import { Badge, Group, Stack, Text, Textarea, Title } from '@mantine/core'
import { useMemo, useState } from 'react'
import { adminQuizApi } from '../api/adminApi'
import { formatError } from '../utils/formUtils'
import { BULK_FORMAT_EXAMPLE, parseBulkQuizText } from '../utils/quizBulk'
import { ErrorAlert, SuccessAlert } from './adminShared'

const PREVIEW_LIMIT = 30

/**
 * Ommaviy test qo'shish: bitta textarea'ga ko'p testni matn ko'rinishida tashlab,
 * bir so'rovdan bazaga saqlash.
 *
 * `titleId` — qaysi anime uchun (media sahifasida oldindan ma'lum);
 * `titleSelector` — umumiy sahifada anime tanlash uchun tugma-ichidagi select.
 * `onCreated` — muvaffaqiyatli saqlangandan keyin chaqiriladi (ro'yxatni yangilash).
 */
export default function QuizBulkImport({ titleId, titleSelector, onCreated }) {
  const [text, setText] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  const parsed = useMemo(() => parseBulkQuizText(text), [text])
  const ready = Boolean(titleId) && parsed.tests.length > 0 && parsed.errors.length === 0

  async function handleSubmit(event) {
    event.preventDefault()
    if (!ready || saving) return
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const payload = {
        title: Number(titleId),
        questions: parsed.tests.map((test) => ({
          text: test.text,
          choices: test.choices,
          correct_index: test.correct_index,
          is_active: true,
        })),
      }
      const result = await adminQuizApi.bulkCreate(payload)
      const created = Number(result?.created) || parsed.tests.length
      setSuccess(`${created} ta savol saqlandi.`)
      setText('')
      onCreated?.()
    } catch (err) {
      setError(formatError(err, 'Ommaviy saqlashda xatolik.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="admin-panel">
      <Title order={5} mb="sm">Ommaviy qo'shish (matn orqali)</Title>
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>
      <form onSubmit={handleSubmit}>
        {titleSelector ? <Group align="flex-end" mb="sm">{titleSelector}</Group> : null}
        <Textarea
          label="Testlar"
          description="Har bir test: savol qatori, so'ng javoblar. To'g'ri javob yozilgandan keyin [togri] belgisi qo'yiladi. Testlar orasida bo'sh qator qoldiring — istalgancha testni bir vaqtda qo'shish mumkin."
          placeholder={BULK_FORMAT_EXAMPLE}
          minRows={10}
          value={text}
          onChange={(event) => setText(event.currentTarget.value)}
          styles={{ input: { fontFamily: 'var(--font-mono)', fontSize: 13, lineHeight: 1.6 } }}
        />

        {!text ? (
          <Text size="xs" c="dimmed" mt="xs">
            Namuna: savol qatori, javoblar (to'g'risiga [togri]), keyin bo'sh qator va keyingi test.
          </Text>
        ) : parsed.errors.length ? (
          <div className="admin-alert admin-alert-error" role="alert" style={{ marginTop: 12 }}>
            <i className="bi bi-exclamation-triangle" aria-hidden="true" />
            <span>
              <Text size="sm" fw={600}>Formatda xatolik: {parsed.errors.length} ta</Text>
              {parsed.errors.map((item, index) => (
                <Text key={`${item.line}-${index}`} size="xs">
                  {item.message} — {item.line}-qator
                </Text>
              ))}
            </span>
          </div>
        ) : parsed.tests.length ? (
          <div className="admin-alert admin-alert-success" role="status" style={{ marginTop: 12 }}>
            <i className="bi bi-check-circle" aria-hidden="true" />
            <span>
              <Text size="sm" fw={600}>
                {parsed.tests.length} ta test topildi — saqlashga tayyor
              </Text>
              <Text size="xs">
                Ko'rsatilayotgani: {Math.min(parsed.tests.length, PREVIEW_LIMIT)} ta
                {parsed.tests.length > PREVIEW_LIMIT ? `, qolgan ${parsed.tests.length - PREVIEW_LIMIT} ta saqlanadi` : ''}.
              </Text>
            </span>
          </div>
        ) : null}

        {parsed.tests.length ? (
          <Stack gap={4} mt="sm" mah={220} style={{ overflowY: 'auto' }}>
            {parsed.tests.slice(0, PREVIEW_LIMIT).map((test, index) => (
              <Group key={`${test.line}-${index}`} gap="xs" wrap="nowrap" align="flex-start">
                <Badge size="xs" variant="light" mt={2}>{index + 1}</Badge>
                <Text size="xs" lineClamp={1} style={{ flex: 1 }}>{test.text}</Text>
                <Text size="xs" c="green" style={{ whiteSpace: 'nowrap' }}>
                  ✓ {test.choices[test.correct_index]}
                </Text>
              </Group>
            ))}
          </Stack>
        ) : null}

        <Group align="flex-end" mt="md">
          <button type="submit" className="admin-btn admin-btn-primary" disabled={!ready || saving}>
            {saving
              ? 'Saqlanmoqda…'
              : `Saqlash${parsed.tests.length ? ` (${parsed.tests.length} ta)` : ''}`}
          </button>
          {text ? (
            <button
              type="button"
              className="admin-btn admin-btn-secondary"
              onClick={() => setText('')}
              disabled={saving}
            >
              Tozalash
            </button>
          ) : null}
        </Group>
      </form>
    </div>
  )
}
