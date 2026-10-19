import {
  ActionIcon,
  Badge,
  Center,
  Checkbox,
  Combobox,
  Group,
  InputBase,
  Loader,
  Stack,
  Switch,
  Text,
  TextInput,
  Title,
  useCombobox,
} from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { useCallback, useEffect, useRef, useState } from 'react'
import { adminMediaApi, adminQuizApi } from '../api/adminApi'
import {
  ConfirmDialog,
  EmptyState,
  ErrorAlert,
  PaginationBar,
  SectionHeading,
  SuccessAlert,
} from '../components/adminShared'
import { formatError, inputHandler, selectHandler } from '../utils/formUtils'

const PAGE_SIZE = 20
const ANIME_PAGE_SIZE = 30

const EMPTY_FORM = {
  title: '',
  text: '',
  choices: ['', '', '', ''],
  correct_index: 0,
  is_active: true,
}

function AnimeSelect({
  value,
  onChange,
  selectedLabel,
  label,
  placeholder = 'Tanlang',
  required,
  clearable,
  disabled,
  w,
}) {
  const combobox = useCombobox({
    onDropdownClose: () => combobox.resetSelectedOption(),
    onOptionSubmit: (optionValue) => {
      onChange?.(optionValue)
      combobox.closeDropdown()
    },
  })

  const [options, setOptions] = useState([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [debouncedSearch] = useDebouncedValue(search, 300)
  const requestRef = useRef(0)

  const totalPages = Math.max(1, Math.ceil(total / ANIME_PAGE_SIZE))

  const fetchPage = useCallback(async (targetPage, query) => {
    const requestId = requestRef.current + 1
    requestRef.current = requestId
    setLoading(true)
    try {
      const params = { type: 'anime', page: targetPage, page_size: ANIME_PAGE_SIZE }
      if (query) params.search = query
      const res = await adminMediaApi.list(params)
      if (requestId !== requestRef.current) return
      const rows = Array.isArray(res?.results) ? res.results : []
      const mapped = rows.map((t) => ({ value: String(t.id), label: t.title }))
      setOptions((prev) => (targetPage === 1 ? mapped : [...prev, ...mapped]))
      setTotal(res?.count || 0)
      setPage(targetPage)
    } catch {
      if (requestId !== requestRef.current) return
      if (targetPage === 1) {
        setOptions([])
        setTotal(0)
        setPage(1)
      }
    } finally {
      if (requestId === requestRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchPage(1, debouncedSearch)
  }, [debouncedSearch, fetchPage])

  function handleScroll(event) {
    if (loading || page >= totalPages) return
    const el = event.currentTarget
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 24) {
      fetchPage(page + 1, debouncedSearch)
    }
  }

  function clearValue(event) {
    event.stopPropagation()
    onChange?.('')
    setSearch('')
    combobox.closeDropdown()
  }

  const currentLabel =
    options.find((o) => o.value === value)?.label ||
    (value ? selectedLabel || `#${value}` : '')

  return (
    <Combobox
      store={combobox}
      withinPortal
      onOptionSubmit={(optionValue) => {
        onChange?.(optionValue)
        combobox.closeDropdown()
      }}
    >
      <Combobox.Target>
        <InputBase
          label={label}
          required={required}
          disabled={disabled}
          w={w}
          component="button"
          type="button"
          pointer
          rightSectionPointerEvents="auto"
          rightSection={
            <Group gap={2} wrap="nowrap" pr={4}>
              {clearable && value ? (
                <ActionIcon size="sm" variant="subtle" color="gray" onClick={clearValue} title="Tozalash">
                  <i className="bi bi-x-lg" />
                </ActionIcon>
              ) : null}
              <Combobox.Chevron size={14} />
            </Group>
          }
          onClick={() => combobox.toggleDropdown()}
        >
          {currentLabel ? (
            currentLabel
          ) : (
            <Text component="span" c="dimmed" size="sm">
              {placeholder}
            </Text>
          )}
        </InputBase>
      </Combobox.Target>
      <Combobox.Dropdown>
        <Combobox.Search
          value={search}
          onChange={(event) => setSearch(event.currentTarget.value)}
          placeholder="Qidirish…"
          onKeyDown={(event) => {
            if (event.key === 'Enter') event.preventDefault()
          }}
        />
        <div style={{ maxHeight: 280, overflowY: 'auto' }} onScroll={handleScroll}>
          <Combobox.Options>
            {options.length === 0 && !loading ? (
              <Combobox.Empty>Topilmadi</Combobox.Empty>
            ) : (
              options.map((option) => (
                <Combobox.Option key={option.value} value={option.value}>
                  {option.label}
                </Combobox.Option>
              ))
            )}
          </Combobox.Options>
          {loading ? (
            <Center py="xs">
              <Loader size="xs" />
            </Center>
          ) : page < totalPages ? (
            <Text size="xs" c="dimmed" ta="center" py={6}>
              Pastga suring — yana yuklanadi…
            </Text>
          ) : options.length > 0 ? (
            <Text size="xs" c="dimmed" ta="center" py={6}>
              Barchasi yuklandi
            </Text>
          ) : null}
        </div>
      </Combobox.Dropdown>
    </Combobox>
  )
}

export default function QuizQuestionsPage() {
  const [data, setData] = useState({ results: [], count: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [titleFilter, setTitleFilter] = useState('')
  const [page, setPage] = useState(1)
  const [form, setForm] = useState(EMPTY_FORM)
  const [editing, setEditing] = useState(null)
  const [saving, setSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [busy, setBusy] = useState(false)
  const [busyId, setBusyId] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = { page, page_size: PAGE_SIZE }
      if (query) params.search = query
      if (titleFilter) params.title = titleFilter
      setData(await adminQuizApi.list(params))
    } catch (err) {
      setError(formatError(err, 'Savollarni yuklashda xatolik.'))
    } finally {
      setLoading(false)
    }
  }, [page, query, titleFilter])

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
      title: String(question.title),
      text: question.text,
      choices: [...question.choices],
      correct_index: question.correct_index,
      is_active: question.is_active,
    })
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!form.title || !form.text.trim()) {
      setError('Anime va savol matni majburiy.')
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
        title: Number(form.title),
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
        setSuccess('Savol qo\'shildi.')
        setForm({ ...EMPTY_FORM, title: form.title })
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
      setSuccess(question.is_active ? 'Savol o\'chirildi (nofaol).' : 'Savol faollashtirildi.')
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
      setSuccess('Savol o\'chirildi.')
      setDeleteTarget(null)
      await load()
    } catch (err) {
      setError(formatError(err, "O'chirishda xatolik."))
      setDeleteTarget(null)
    } finally {
      setBusy(false)
    }
  }

  const results = data.results || []
  const count = data.count || 0
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE))

  return (
    <Stack gap="lg">
      <SectionHeading
        title="O'yin savollari"
        description="Anime reyting o'yini uchun quiz savollarini boshqarish: savol, variantlar, to'g'ri javob."
      />
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>

      <div className="admin-panel">
        <Title order={5} mb="sm">{editing ? `Tahrirlash: ${editing.text.slice(0, 40)}…` : 'Yangi savol'}</Title>
        <form onSubmit={handleSubmit}>
          <Group align="flex-end" grow>
            <AnimeSelect
              label="Anime"
              placeholder="Tanlang"
              value={form.title}
              onChange={selectHandler(setForm, 'title')}
              selectedLabel={editing?.title_title}
              required
            />
            <TextInput
              label="Savol matni"
              placeholder="Qahramonning ismi nima?"
              value={form.text}
              onChange={inputHandler(setForm, 'text')}
              required
            />
          </Group>
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

      <Group align="flex-end" justify="space-between" wrap="wrap">
        <Group align="flex-end" wrap="wrap">
          <TextInput
            label="Qidiruv"
            placeholder="Savol yoki anime bo'yicha"
            value={search}
            onChange={(event) => setSearch(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                setPage(1)
                setQuery(search.trim())
              }
            }}
            w={{ base: '100%', sm: 280 }}
          />
          <AnimeSelect
            label="Anime bo'yicha"
            placeholder="Barchasi"
            value={titleFilter}
            onChange={(value) => {
              setTitleFilter(value || '')
              setPage(1)
            }}
            clearable
            w={{ base: '100%', sm: 260 }}
          />
          <button
            type="button"
            className="admin-btn admin-btn-secondary"
            onClick={() => {
              setPage(1)
              setQuery(search.trim())
            }}
          >
            <i className="bi bi-search" /> Filtrlash
          </button>
        </Group>
        <button
          type="button"
          className="admin-btn admin-btn-secondary"
          onClick={() => {
            setSearch('')
            setQuery('')
            setTitleFilter('')
            setPage(1)
          }}
        >
          Tozalash
        </button>
      </Group>

      {loading ? (
        <div className="admin-loading"><Loader /></div>
      ) : results.length === 0 ? (
        <EmptyState
          icon="bi-question-circle"
          title="Savol yo'q"
          description="Yuqoridagi shakldan yangi quiz savoli qo'shing."
        />
      ) : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Anime</th>
                <th>Savol</th>
                <th>Variantlar</th>
                <th>To'g'ri</th>
                <th>Faol</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {results.map((question) => (
                <tr key={question.id}>
                  <td>
                    <Text size="sm" fw={500}>{question.title_title}</Text>
                    <Badge size="xs" variant="light" mt={2}>{question.title_type}</Badge>
                  </td>
                  <td>
                    <Text size="sm" lineClamp={2}>{question.text}</Text>
                  </td>
                  <td>
                    <Stack gap={2}>
                      {question.choices.map((choice, index) => (
                        <Text
                          key={index}
                          size="xs"
                          fw={index === question.correct_index ? 700 : 400}
                          c={index === question.correct_index ? 'green' : 'dimmed'}
                        >
                          {index === question.correct_index ? '✓' : '·'} {choice}
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

      <PaginationBar
        page={page}
        totalPages={totalPages}
        count={count}
        onChange={setPage}
        loading={loading}
      />

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
