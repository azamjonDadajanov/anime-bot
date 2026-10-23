import {
  ActionIcon,
  Badge,
  Checkbox,
  Group,
  Loader,
  NumberInput,
  Stack,
  Switch,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { adminMediaApi, adminQuizApi } from '../api/adminApi'
import { adminPath } from '../adminBase'
import QuizBulkImport from '../components/QuizBulkImport'
import {
  ConfirmDialog,
  EmptyState,
  ErrorAlert,
  SectionHeading,
  SuccessAlert,
} from '../components/adminShared'
import { formatError, inputHandler } from '../utils/formUtils'

const PAGE_SIZE = 100

const EMPTY_FORM = {
  text: '',
  choices: ['', '', '', ''],
  correct_index: 0,
  is_active: true,
}

export default function MediaQuizPage() {
  const { slug } = useParams()
  const [media, setMedia] = useState(null)
  const [questions, setQuestions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [editing, setEditing] = useState(null)
  const [saving, setSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [busy, setBusy] = useState(false)
  const [busyId, setBusyId] = useState(null)
  const [quizSize, setQuizSize] = useState('')
  const [savingSize, setSavingSize] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const detail = await adminMediaApi.detail(slug)
      setMedia(detail)
      setQuizSize(detail.quiz_size ?? '')
      const result = await adminQuizApi.list({ title: detail.id, page_size: PAGE_SIZE })
      setQuestions(Array.isArray(result) ? result : result.results || [])
    } catch (err) {
      setError(formatError(err, "Ma'lumotni yuklashda xatolik."))
    } finally {
      setLoading(false)
    }
  }, [slug])

  useEffect(() => {
    load()
  }, [load])

  function setChoice(index, value) {
    setForm((prev) => {
      const choices = [...prev.choices]
      choices[index] = value
      return { ...prev, choices }
    })
  }

  function cancelEdit() {
    setEditing(null)
    setForm(EMPTY_FORM)
  }

  function startEdit(question) {
    setEditing(question)
    setForm({
      text: question.text,
      choices: [...question.choices],
      correct_index: question.correct_index,
      is_active: question.is_active,
    })
  }

  async function handleSaveQuizSize() {
    const value = quizSize === '' || quizSize === null ? null : Number(quizSize)
    if (value !== null && (!Number.isInteger(value) || value < 1)) {
      setError("Savollar soni 1 dan katta butun son bo'lishi kerak.")
      return
    }
    setSavingSize(true)
    setError(null)
    setSuccess(null)
    try {
      const saved = await adminMediaApi.update(slug, { quiz_size: value })
      setMedia((prev) => (prev ? { ...prev, ...saved } : prev))
      setSuccess('Savollar soni saqlandi.')
    } catch (err) {
      setError(formatError(err, "Sozlarni saqlashda xatolik."))
    } finally {
      setSavingSize(false)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!form.text.trim()) {
      setError('Savol matni majburiy.')
      return
    }
    const choices = form.choices.map((c) => c.trim()).filter(Boolean)
    if (choices.length < 2) {
      setError('Kamida 2 ta variant kiriting.')
      return
    }
    if (form.correct_index >= choices.length) {
      setError("To'g'ri javob indeksi variantlar sonidan katta bo'lishi mumkin emas.")
      return
    }
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const payload = {
        title: Number(media.id),
        text: form.text.trim(),
        choices,
        correct_index: Number(form.correct_index) || 0,
        is_active: form.is_active,
      }
      if (editing) {
        await adminQuizApi.update(editing.id, payload)
        setSuccess('Savol yangilandi.')
        cancelEdit()
      } else {
        await adminQuizApi.create(payload)
        setSuccess("Savol qo'shildi.")
        setForm(EMPTY_FORM)
      }
      await load()
    } catch (err) {
      setError(formatError(err, 'Saqlashda xatolik.'))
    } finally {
      setSaving(false)
    }
  }

  async function handleToggleActive(question) {
    setBusyId(question.id)
    setError(null)
    try {
      await adminQuizApi.update(question.id, { is_active: !question.is_active })
      setSuccess(question.is_active ? "Savol o'chirildi (nofaol)." : 'Savol faollashtirildi.')
      await load()
    } catch (err) {
      setError(formatError(err, "Holatni o'zgartirishda xatolik."))
    } finally {
      setBusyId(null)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    setBusy(true)
    try {
      await adminQuizApi.remove(deleteTarget.id)
      setSuccess("Savol o'chirildi.")
      setDeleteTarget(null)
      await load()
    } catch (err) {
      setError(formatError(err, "O'chirishda xatolik."))
      setDeleteTarget(null)
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <div className="admin-loading"><Loader size="lg" /></div>
  if (!media) return <ErrorAlert>{error || 'Media topilmadi.'}</ErrorAlert>

  const activeCount = questions.filter((question) => question.is_active).length
  const effectiveSize = Math.min(
    Number(quizSize) || activeCount || 0,
    activeCount,
  )

  return (
    <Stack gap="lg">
      <SectionHeading
        title={`${media.title} — test savollari`}
        description="Anime ko'rgach beriladigan quiz: savollar qo'shing va nechta savolga javob berilishini belgilang. Savollar va variantlar foydalanuvchiga tasodifiy tartibda ko'rsatiladi."
        actions={
          <Group gap="xs">
            <Link className="admin-btn admin-btn-secondary" to={adminPath(`/media/${slug}`)}>
              Qismlar
            </Link>
            <Link className="admin-btn admin-btn-secondary" to={adminPath('/quiz')}>
              Barcha savollar
            </Link>
            <Link className="admin-btn admin-btn-secondary" to={adminPath('/media')}>
              Ro'yxat
            </Link>
          </Group>
        }
      />
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>

      <div className="admin-panel">
        <Title order={5} mb="sm">O'yin sozlamalari</Title>
        <Group align="flex-end" wrap="wrap">
          <NumberInput
            label="Nechta savolga javob berishi"
            description={`Faol savollar: ${activeCount}. Bo'sh qoldirsangiz, global sozlama (5) ishlatiladi.`}
            placeholder="Masalan: 5"
            value={quizSize}
            onChange={setQuizSize}
            min={1}
            max={Math.max(1, activeCount)}
            w={{ base: '100%', sm: 280 }}
          />
          <button
            type="button"
            className="admin-btn admin-btn-primary"
            onClick={handleSaveQuizSize}
            disabled={savingSize}
          >
            {savingSize ? 'Saqlanmoqda…' : 'Saqlash'}
          </button>
        </Group>
        <Text size="xs" c="dimmed" mt="xs">
          Masalan: 10 ta savol bo'lsa va bu yerda 5 korsangiz, foydalanuvchi animeni
          ko'rgach tasodifiy tanlangan 5 ta savolga javob beradi. O'tish uchun ~80%
          to'g'ri javob kerak.
          {effectiveSize > 0 ? ` Joriy: ${effectiveSize} savol.` : ''}
        </Text>
      </div>

      <div className="admin-panel">
        <Title order={5} mb="sm">{editing ? `Tahrirlash: ${editing.text.slice(0, 40)}…` : 'Yangi savol'}</Title>
        <form onSubmit={handleSubmit}>
          <TextInput
            label="Savol matni"
            placeholder="Qahramonning ismi nima?"
            value={form.text}
            onChange={inputHandler(setForm, 'text')}
            required
          />
          <Stack gap="xs" mt="md">
            <Text size="sm" fw={500}>Variantlar (kamida 2 ta)</Text>
            {form.choices.map((choice, index) => (
              <Group key={index} align="flex-end" grow wrap="nowrap">
                <TextInput
                  placeholder={`${index + 1}-variant`}
                  value={choice}
                  onChange={(event) => setChoice(index, event.currentTarget.value)}
                />
                <Checkbox
                  label="To'g'ri"
                  checked={form.correct_index === index}
                  onChange={() => setForm((prev) => ({ ...prev, correct_index: index }))}
                  w={100}
                />
              </Group>
            ))}
          </Stack>
          <Group align="flex-end" mt="md">
            <Switch
              label="Faol"
              checked={form.is_active}
              onChange={(event) => setForm((prev) => ({ ...prev, is_active: event.currentTarget.checked }))}
            />
            {editing ? (
              <button type="button" className="admin-btn admin-btn-secondary" onClick={cancelEdit}>
                Bekor
              </button>
            ) : null}
            <button type="submit" className="admin-btn admin-btn-primary" disabled={saving}>
              {saving ? 'Saqlanmoqda…' : editing ? 'Saqlash' : "Qo'shish"}
            </button>
          </Group>
        </form>
      </div>

      <QuizBulkImport titleId={media.id} onCreated={load} />

      {questions.length === 0 ? (
        <EmptyState
          icon="bi-question-circle"
          title="Savol yo'q"
          description="Yuqoridagi shakldan ushbu media uchun yangi test savoli qo'shing."
        />
      ) : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Savol</th>
                <th>Variantlar</th>
                <th>To'g'ri</th>
                <th>Faol</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {questions.map((question, index) => (
                <tr key={question.id}>
                  <td>{index + 1}</td>
                  <td>
                    <Text size="sm" lineClamp={2}>{question.text}</Text>
                    {!question.is_active ? (
                      <Badge size="xs" variant="light" mt={2} color="gray">Nofaol</Badge>
                    ) : null}
                  </td>
                  <td>
                    <Stack gap={2}>
                      {question.choices.map((choice, choiceIndex) => (
                        <Text
                          key={choiceIndex}
                          size="xs"
                          fw={choiceIndex === question.correct_index ? 700 : 400}
                          c={choiceIndex === question.correct_index ? 'green' : 'dimmed'}
                        >
                          {choiceIndex === question.correct_index ? '✓' : '·'} {choice}
                        </Text>
                      ))}
                    </Stack>
                  </td>
                  <td>
                    <Text size="sm" fw={600} c="green">
                      {question.choices[question.correct_index] || '—'}
                    </Text>
                  </td>
                  <td>
                    <Switch
                      checked={question.is_active}
                      onChange={() => handleToggleActive(question)}
                      size="sm"
                      disabled={busyId === question.id}
                    />
                  </td>
                  <td>
                    <Group gap={4} wrap="nowrap">
                      <ActionIcon
                        variant="subtle"
                        color="blue"
                        onClick={() => startEdit(question)}
                        title="Tahrirlash"
                      >
                        <i className="bi bi-pencil" />
                      </ActionIcon>
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        onClick={() => setDeleteTarget(question)}
                        title="O'chirish"
                      >
                        <i className="bi bi-trash" />
                      </ActionIcon>
                    </Group>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Savolni o'chirish"
        message={`"${deleteTarget?.text?.slice(0, 60) || ''}…" savoli o'chiriladi. Bu amalni qaytarib bo'lmaydi.`}
        confirmLabel="O'chirish"
        danger
        loading={busy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      />
    </Stack>
  )
}
