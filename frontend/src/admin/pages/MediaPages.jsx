import {
  ActionIcon,
  Checkbox,
  FileButton,
  Group,
  Image,
  Loader,
  Modal,
  MultiSelect,
  NumberInput,
  Select,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  adminGenreApi,
  adminMediaApi,
  coverDataUrl,
} from '../api/adminApi'
import { adminPath } from '../adminBase'
import { coverSrc } from '../../apis/mediaUrl'
import {
  ACCESS_PLAN_LABELS,
  ConfirmDialog,
  EmptyState,
  ErrorAlert,
  MEDIA_TYPE_LABELS,
  PaginationBar,
  SectionHeading,
  SuccessAlert,
} from '../components/adminShared'
import {
  copyText,
  formatError,
  inputHandler,
  numberHandler,
  selectHandler,
  toBase64,
} from '../utils/formUtils'

const TYPE_OPTIONS = Object.entries(MEDIA_TYPE_LABELS).map(([value, label]) => ({ value, label }))
const STATUS_OPTIONS = [
  { value: 'upcoming', label: 'Kutilmoqda' },
  { value: 'ongoing', label: 'Davom etmoqda' },
  { value: 'completed', label: 'Tugallangan' },
]
const PLAN_OPTIONS = [
  { value: 'free', label: 'Bepul' },
  { value: 'paid', label: 'Obunaga' },
]
const MEDIA_KIND_OPTIONS = [
  { value: 'video', label: 'Video' },
  { value: 'photo', label: 'Rasm' },
  { value: 'document', label: 'Fayl' },
]

const DEFAULT_YEAR = new Date().getFullYear()

const EMPTY_MEDIA_FORM = {
  title: '',
  type: 'movie',
  synopsis: '',
  required_plan: 'free',
  rating: 5,
  release_year: DEFAULT_YEAR,
  status: 'upcoming',
  episode_count: '',
  duration_minutes: '',
  language: "O'zbekcha",
  default_quality: '1080',
}

export function MediaListPage({ typeFilter = null }) {
  const [params, setParams] = useSearchParams()
  const [search, setSearch] = useState(params.get('search') || '')
  const [page, setPage] = useState(Number(params.get('page') || 1))
  const [data, setData] = useState({ results: [], count: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const query = { page, page_size: 20 }
      if (search) query.search = search
      if (typeFilter) query.type = typeFilter
      const result = await adminMediaApi.list(query)
      setData(Array.isArray(result) ? { results: result, count: result.length } : result)
    } catch (err) {
      setError(formatError(err, 'Medialarni yuklashda xatolik.'))
    } finally {
      setLoading(false)
    }
  }, [page, search, typeFilter])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const next = new URLSearchParams()
    if (search) next.set('search', search)
    if (page > 1) next.set('page', String(page))
    setParams(next, { replace: true })
  }, [search, page, setParams])

  async function confirmDelete() {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await adminMediaApi.remove(deleteTarget.slug)
      setSuccess("Media o'chirildi.")
      setDeleteTarget(null)
      await load()
    } catch (err) {
      setError(formatError(err, "O'chirishda xatolik."))
      setDeleteTarget(null)
    } finally {
      setDeleting(false)
    }
  }

  const results = data.results || []
  const count = data.count || 0
  const totalPages = Math.max(1, Math.ceil(count / 20))

  return (
    <Stack gap="lg">
      <SectionHeading
        title={typeFilter ? MEDIA_TYPE_LABELS[typeFilter] || typeFilter : 'Medialar'}
        description="Katalogni boshqarish: qo'shish, tahrirlash, o'chirish."
        actions={
          <Link className="admin-btn admin-btn-primary" to={adminPath('/media/new')}>
            <i className="bi bi-plus-lg" aria-hidden="true" /> Yangi media
          </Link>
        }
      />
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>
      <Group align="flex-end">
        <TextInput
          label="Qidiruv"
          placeholder="Nomi yoki kod"
          value={search}
          onChange={(event) => {
            setSearch(event.currentTarget.value)
            setPage(1)
          }}
          w={{ base: '100%', sm: 320 }}
        />
      </Group>

      {loading ? (
        <div className="admin-loading"><Loader /></div>
      ) : results.length === 0 ? (
        <EmptyState
          icon="bi-film"
          title="Media topilmadi"
          description="Yangi media qo'shing yoki qidiruvni o'zgartiring."
          action={
            <Link className="admin-btn admin-btn-primary" to={adminPath('/media/new')}>
              Yangi media
            </Link>
          }
        />
      ) : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Media</th>
                <th>Turi</th>
                <th>Kod</th>
                <th>Holat</th>
                <th>Tarif</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {results.map((item) => (
                <tr key={item.id}>
                  <td>
                    <Group gap="sm" wrap="nowrap">
                      <div className="admin-thumb">
                        {coverDataUrl(item) ? (
                          <img src={coverDataUrl(item)} alt="" />
                        ) : (
                          <i className="bi bi-film" aria-hidden="true" />
                        )}
                      </div>
                      <div>
                        <Text fw={600} size="sm">{item.title}</Text>
                        <Text size="xs" c="dimmed">/{item.slug}</Text>
                      </div>
                    </Group>
                  </td>
                  <td>{MEDIA_TYPE_LABELS[item.type] || item.type}</td>
                  <td>
                    <Group gap={4} wrap="nowrap">
                      <code>{item.code}</code>
                      <ActionIcon
                        variant="subtle"
                        size="xs"
                        onClick={() => copyText(item.code)}
                        title="Kodni nusxalash"
                      >
                        <i className="bi bi-clipboard" />
                      </ActionIcon>
                    </Group>
                  </td>
                  <td>{STATUS_OPTIONS.find((s) => s.value === item.status)?.label || item.status}</td>
                  <td>{ACCESS_PLAN_LABELS[item.required_plan] || item.required_plan}</td>
                  <td>
                    <Group gap={4} wrap="nowrap">
                      <ActionIcon
                        variant="subtle"
                        color="blue"
                        component={Link}
                        to={adminPath(`/media/${item.slug}`)}
                        title="Qismlar"
                      >
                        <i className="bi bi-collection-play" />
                      </ActionIcon>
                      <ActionIcon
                        variant="subtle"
                        color="green"
                        component={Link}
                        to={adminPath(`/media/${item.slug}/quiz`)}
                        title="Test savollari"
                      >
                        <i className="bi bi-question-circle" />
                      </ActionIcon>
                      <ActionIcon
                        variant="subtle"
                        color="blue"
                        component={Link}
                        to={adminPath(`/media/${item.slug}/edit`)}
                        title="Tahrirlash"
                      >
                        <i className="bi bi-pencil" />
                      </ActionIcon>
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        onClick={() => setDeleteTarget(item)}
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
        title="Mediani o'chirish"
        message={`"${deleteTarget?.title}" mediasi va barcha qismlari o'chiriladi.`}
        confirmLabel="O'chirish"
        danger
        loading={deleting}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
      />
    </Stack>
  )
}

export function MediaFormPage() {
  const { slug } = useParams()
  const navigate = useNavigate()
  const isEdit = Boolean(slug)
  const [form, setForm] = useState(EMPTY_MEDIA_FORM)
  const [genreIds, setGenreIds] = useState([])
  const [genres, setGenres] = useState([])
  const [coverFile, setCoverFile] = useState(null)
  const [coverPreview, setCoverPreview] = useState('')
  const [coverBase64, setCoverBase64] = useState('')
  const [loading, setLoading] = useState(isEdit)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  useEffect(() => {
    let active = true
    adminGenreApi.list({ page_size: 100 })
      .then((items) => {
        if (active) setGenres(items)
      })
      .catch(() => {
        if (active) setGenres([])
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!slug) return undefined
    let active = true
    adminMediaApi.detail(slug)
      .then((item) => {
        if (!active) return
        setForm({
          title: item.title || '',
          type: item.type || 'movie',
          synopsis: item.synopsis || '',
          required_plan: item.required_plan || 'free',
          rating: item.rating ?? 5,
          release_year: item.release_year || DEFAULT_YEAR,
          status: item.status || 'upcoming',
          episode_count: item.episode_count ?? '',
          duration_minutes: item.duration_minutes ?? '',
          language: item.language || "O'zbekcha",
          default_quality: item.default_quality || '1080',
        })
        setGenreIds((item.genres || []).map((id) => String(id)))
        setCoverPreview(coverDataUrl(item))
        setCoverBase64(item.cover || '')
      })
      .catch((err) => {
        if (active) setError(formatError(err, 'Media topilmadi.'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [slug])

  const genreOptions = useMemo(
    () => genres.map((genre) => ({ value: String(genre.id), label: genre.name })),
    [genres],
  )

  async function handleCover(file) {
    if (!file) {
      setCoverFile(null)
      setCoverBase64('')
      return
    }
    setCoverFile(file)
    const base64 = await toBase64(file)
    setCoverBase64(base64)
    setCoverPreview(`data:${file.type || 'image/jpeg'};base64,${base64}`)
  }

  function handleCoverBase64Paste(event) {
    const raw = (event.currentTarget?.value || '').trim()
    setCoverBase64(raw)
    setCoverFile(null)
    if (!raw) {
      setCoverPreview('')
      return
    }
    // The pasted value may be base64, a data: URL, or the stored
    // /media/covers/... path echoed back from the form.
    setCoverPreview(coverSrc({ cover: raw }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const payload = {
        title: form.title,
        type: form.type,
        synopsis: form.synopsis || '',
        required_plan: form.required_plan,
        rating: Number(form.rating) || 5,
        release_year: form.release_year ? Number(form.release_year) : null,
        status: form.status,
        episode_count: form.episode_count === '' || form.episode_count === null ? null : Number(form.episode_count),
        duration_minutes:
          form.duration_minutes === '' || form.duration_minutes === null
            ? null
            : Number(form.duration_minutes),
        language: form.language || "O'zbekcha",
        default_quality: form.default_quality || '1080',
        genres: genreIds.map(Number),
      }
      let saved
      if (isEdit) {
        saved = await adminMediaApi.update(slug, payload)
      } else {
        saved = await adminMediaApi.create(payload)
      }
      if (coverBase64) {
        const clean = coverBase64.replace(/^data:[^;]+;base64,/, '')
        await adminMediaApi.update(saved.slug, {
          cover: clean,
          cover_content_type: coverFile?.type || 'image/jpeg',
        })
      }
      setSuccess(isEdit ? 'Media yangilandi.' : 'Media yaratildi.')
      if (!isEdit && saved?.slug) {
        navigate(adminPath(`/media/${saved.slug}`))
      }
    } catch (err) {
      setError(formatError(err, "Saqlashda xatolik."))
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="admin-loading"><Loader size="lg" /></div>

  return (
    <Stack gap="lg" maw={720}>
      <SectionHeading
        title={isEdit ? 'Mediani tahrirlash' : 'Yangi media'}
        description="Katalog uchun asosiy ma'lumotlar va muqova. Slug avtomatik yaratiladi."
        actions={
          <Link className="admin-btn admin-btn-secondary" to={adminPath('/media')}>
            Orqaga
          </Link>
        }
      />
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>
      <form className="admin-panel" onSubmit={handleSubmit}>
        <Stack gap="md">
          <TextInput
            label="Nomi"
            value={form.title}
            onChange={inputHandler(setForm, 'title')}
            required
          />
          <Group grow align="flex-start">
            <Select
              label="Turi"
              data={TYPE_OPTIONS}
              value={form.type}
              onChange={selectHandler(setForm, 'type')}
              allowDeselect={false}
            />
            <Select
              label="Tarif"
              data={PLAN_OPTIONS}
              value={form.required_plan}
              onChange={selectHandler(setForm, 'required_plan')}
              allowDeselect={false}
            />
          </Group>
          <Group grow align="flex-start">
            <Select
              label="Holat"
              data={STATUS_OPTIONS}
              value={form.status}
              onChange={selectHandler(setForm, 'status')}
              allowDeselect={false}
            />
            <NumberInput
              label="Reyting"
              min={1}
              max={10}
              value={form.rating}
              onChange={numberHandler(setForm, 'rating')}
            />
          </Group>
          <Group grow align="flex-start">
            <NumberInput
              label="Chiqarilgan yil"
              min={1900}
              max={2100}
              value={form.release_year}
              onChange={numberHandler(setForm, 'release_year')}
            />
            <NumberInput
              label="Qismlar soni"
              min={0}
              value={form.episode_count}
              onChange={numberHandler(setForm, 'episode_count')}
            />
            <NumberInput
              label="Davomiylik (daqiqa)"
              min={0}
              max={1440}
              value={form.duration_minutes}
              onChange={numberHandler(setForm, 'duration_minutes')}
            />
          </Group>
          <MultiSelect
            label="Janrlar"
            data={genreOptions}
            value={genreIds}
            onChange={setGenreIds}
            searchable
            clearable
          />
          <Textarea
            label="Tavsif"
            minRows={4}
            value={form.synopsis}
            onChange={inputHandler(setForm, 'synopsis')}
          />
          <Group align="flex-end">
            <div className="admin-cover-preview">
              {coverPreview ? (
                <Image src={coverPreview} alt="Muqova" radius="sm" w={120} h={160} fit="cover" />
              ) : (
                <div className="admin-cover-placeholder">
                  <i className="bi bi-image" aria-hidden="true" />
                </div>
              )}
            </div>
            <Stack gap="xs" style={{ flex: 1 }}>
              <FileButton onChange={handleCover} accept="image/*">
                {(props) => (
                  <button type="button" className="admin-btn admin-btn-secondary" {...props}>
                    Muqova yuklash
                  </button>
                )}
              </FileButton>
              <Textarea
                label="Yoki base64 hash (masalan /9j/4AAQ...)"
                placeholder="/9j/4AAQSkZJRgABAQEAeAB4AD..."
                minRows={2}
                value={coverBase64}
                onChange={handleCoverBase64Paste}
              />
            </Stack>
          </Group>
          <Group justify="flex-end">
            <button type="submit" className="admin-btn admin-btn-primary" disabled={saving}>
              {saving ? 'Saqlanmoqda…' : isEdit ? 'Saqlash' : 'Yaratish'}
            </button>
          </Group>
        </Stack>
      </form>
    </Stack>
  )
}

export function MediaPartsPage() {
  const { slug } = useParams()
  const [media, setMedia] = useState(null)
  const [parts, setParts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [partModal, setPartModal] = useState(false)
  const [editingPart, setEditingPart] = useState(null)
  const [partForm, setPartForm] = useState({ number: 1, season_number: '', title: '' })
  const [savingPart, setSavingPart] = useState(false)
  const [deletePart, setDeletePart] = useState(null)
  const [mediaPartId, setMediaPartId] = useState(null)
  const [fileIdForm, setFileIdForm] = useState({ file_id: '', media_type: 'video', order: 1, caption: '' })
  const [addingMedia, setAddingMedia] = useState(false)
  const [deleteMediaItem, setDeleteMediaItem] = useState(null)
  const [busy, setBusy] = useState(false)
  // The slug the announcement card was opened for (null = closed). Keying it to
  // the slug means navigating to another media can never leave a stale card.
  const [announceFor, setAnnounceFor] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const detail = await adminMediaApi.detail(slug)
      setMedia(detail)
      setParts(detail.parts || [])
    } catch (err) {
      setError(formatError(err, 'Media topilmadi.'))
    } finally {
      setLoading(false)
    }
  }, [slug])

  useEffect(() => {
    load()
  }, [load])

  function openTelegramMediaForm(partId) {
    if (mediaPartId === partId) {
      setMediaPartId(null)
      return
    }
    setMediaPartId(partId)
    setFileIdForm((prev) => ({ ...prev, order: 1, caption: '' }))
    adminMediaApi
      .telegramMedia(partId)
      .then((list) => {
        const maxOrder = list.reduce((max, m) => Math.max(max, m.order || 0), 0)
        setFileIdForm((prev) => ({ ...prev, order: maxOrder + 1 }))
      })
      .catch(() => {})
  }

  function openCreatePart() {
    setEditingPart(null)
    setPartForm({
      number: (parts[parts.length - 1]?.number || 0) + 1,
      season_number: '',
      title: '',
    })
    setPartModal(true)
  }

  function openEditPart(part) {
    setEditingPart(part)
    setPartForm({
      number: part.number,
      season_number: part.season_number ?? '',
      title: part.title || '',
    })
    setPartModal(true)
  }

  async function handleSavePart(event) {
    event.preventDefault()
    setSavingPart(true)
    setError(null)
    try {
      const payload = {
        number: Number(partForm.number) || 1,
        season_number: partForm.season_number === '' || partForm.season_number === null
          ? null
          : Number(partForm.season_number),
        title: partForm.title || '',
      }
      if (editingPart) {
        await adminMediaApi.updatePart(editingPart.id, payload)
        setSuccess('Qism yangilandi.')
      } else {
        await adminMediaApi.createPart({ ...payload, content: media.id })
        setSuccess('Qism yaratildi.')
      }
      setPartModal(false)
      setEditingPart(null)
      await load()
    } catch (err) {
      setError(formatError(err, "Qism saqlashda xatolik."))
    } finally {
      setSavingPart(false)
    }
  }

  async function handleDeletePart() {
    if (!deletePart) return
    setBusy(true)
    try {
      await adminMediaApi.deletePart(deletePart.id)
      setDeletePart(null)
      setSuccess("Qism o'chirildi.")
      await load()
    } catch (err) {
      setError(formatError(err, "O'chirishda xatolik."))
      setDeletePart(null)
    } finally {
      setBusy(false)
    }
  }

  async function handleUploadPdf(file, part) {
    if (!file || !part) return
    setError(null)
    try {
      await adminMediaApi.uploadPdf(part.id, file)
      setSuccess("PDF saqlandi.")
      await load()
    } catch (err) {
      setError(formatError(err, 'PDF yuklashda xatolik.'))
    }
  }

  async function handleAddTelegramMedia(event) {
    event.preventDefault()
    if (!mediaPartId) return
    setAddingMedia(true)
    setError(null)
    try {
      const result = await adminMediaApi.addTelegramMedia({
        part: mediaPartId,
        file_id: fileIdForm.file_id,
        media_type: fileIdForm.media_type,
        order: Number(fileIdForm.order) || 1,
        caption: fileIdForm.caption || '',
      })
      if (result?.storage_error) {
        setError(`Media qo'shildi, lekin Cloud kanalga ko'chirilmadi: ${result.storage_error}`)
      } else {
        setSuccess("Telegram media qo'shildi va Cloud kanalga ko'chirildi.")
      }
      setFileIdForm((prev) => ({
        file_id: '',
        media_type: prev.media_type,
        order: (Number(prev.order) || 0) + 1,
        caption: '',
      }))
      setMediaPartId(null)
      await load()
    } catch (err) {
      setError(formatError(err, "Media qo'shishda xatolik."))
    } finally {
      setAddingMedia(false)
    }
  }

  async function handleDeleteMediaItem() {
    if (!deleteMediaItem) return
    setBusy(true)
    try {
      await adminMediaApi.deleteTelegramMedia(deleteMediaItem.id)
      setDeleteMediaItem(null)
      setSuccess("Media o'chirildi.")
      await load()
    } catch (err) {
      setError(formatError(err, "O'chirishda xatolik."))
      setDeleteMediaItem(null)
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <div className="admin-loading"><Loader size="lg" /></div>
  if (!media) return <ErrorAlert>{error || 'Media topilmadi.'}</ErrorAlert>

  return (
    <Stack gap="lg">
      <SectionHeading
        title={`${media.title} — qismlar`}
        description="Qismlar, Telegram file_id va PDF fayllarni boshqarish."
        actions={
          <Group gap="xs">
            <Link className="admin-btn admin-btn-secondary" to={adminPath('/media')}>
              Ro'yxat
            </Link>
            <Link className="admin-btn admin-btn-secondary" to={adminPath(`/media/${slug}/quiz`)}>
              <i className="bi bi-question-circle" aria-hidden="true" /> Test savollari
            </Link>
            <button
              type="button"
              className="admin-btn admin-btn-secondary"
              onClick={() => setAnnounceFor(slug)}
            >
              <i className="bi bi-megaphone" aria-hidden="true" /> E'lon qilish
            </button>
            <button type="button" className="admin-btn admin-btn-primary" onClick={openCreatePart}>
              <i className="bi bi-plus-lg" aria-hidden="true" /> Qism qo'shish
            </button>
          </Group>
        }
      />
      <ErrorAlert>{error}</ErrorAlert>
      <SuccessAlert>{success}</SuccessAlert>

      {parts.length === 0 ? (
        <EmptyState
          icon="bi-collection-play"
          title="Qismlar yo'q"
          description="Avval qism qo'shing, so'ng unga media fayl ulang."
          action={
            <button type="button" className="admin-btn admin-btn-primary" onClick={openCreatePart}>
              Qism qo'shish
            </button>
          }
        />
      ) : (
        <Stack gap="md">
          {parts.map((part) => (
            <div key={part.id} className="admin-panel admin-part-card">
              <Group justify="space-between" align="flex-start" wrap="wrap">
                <div>
                  <Title order={5}>
                    {part.season_number ? `${part.season_number}-fasl · ` : ''}
                    {part.number}-qism
                    {part.title ? ` — ${part.title}` : ''}
                  </Title>
                  <Text size="xs" c="dimmed">
                    PDF: {part.has_pdf ? 'ha' : "yo'q"} · ID: {part.id}
                  </Text>
                </div>
                <Group gap="xs">
                  <button
                    type="button"
                    className="admin-btn admin-btn-secondary"
                    onClick={() => openTelegramMediaForm(part.id)}
                  >
                    <i className="bi bi-link-45deg" aria-hidden="true" /> file_id
                  </button>
                  <label className="admin-btn admin-btn-secondary admin-file-label">
                    PDF yuklash
                    <input
                      type="file"
                      accept="application/pdf"
                      hidden
                      onChange={(event) => {
                        const file = event.target.files?.[0]
                        event.target.value = ''
                        if (file) handleUploadPdf(file, part)
                      }}
                    />
                  </label>
                  <ActionIcon
                    variant="subtle"
                    color="blue"
                    onClick={() => openEditPart(part)}
                    title="Tahrirlash"
                  >
                    <i className="bi bi-pencil" />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    onClick={() => setDeletePart(part)}
                    title="O'chirish"
                  >
                    <i className="bi bi-trash" />
                  </ActionIcon>
                </Group>
              </Group>

              {mediaPartId === part.id ? (
                <form className="admin-inline-form" onSubmit={handleAddTelegramMedia}>
                  <TextInput
                    label="Telegram file_id"
                    placeholder="BAACAgUAAxk..."
                    description="Qo'shilganda fayl avtomatik Cloud kanalga ko'chiriladi."
                    value={fileIdForm.file_id}
                    onChange={inputHandler(setFileIdForm, 'file_id')}
                    required
                    w={{ base: '100%', md: 320 }}
                  />
                  <Select
                    label="Turi"
                    data={MEDIA_KIND_OPTIONS}
                    value={fileIdForm.media_type}
                    onChange={selectHandler(setFileIdForm, 'media_type')}
                    w={140}
                    allowDeselect={false}
                  />
                  <NumberInput
                    label="Tartib"
                    min={1}
                    value={fileIdForm.order}
                    onChange={numberHandler(setFileIdForm, 'order')}
                    w={100}
                  />
                  <TextInput
                    label="Izoh"
                    value={fileIdForm.caption}
                    onChange={inputHandler(setFileIdForm, 'caption')}
                    w={{ base: '100%', md: 200 }}
                  />
                  <button type="submit" className="admin-btn admin-btn-primary" disabled={addingMedia}>
                    {addingMedia ? "Qo'shilmoqda…" : "Qo'shish"}
                  </button>
                </form>
              ) : null}

              <PartMediaList
                partId={part.id}
                onError={setError}
                onDelete={(item) => setDeleteMediaItem(item)}
              />
            </div>
          ))}
        </Stack>
      )}

      <Modal
        opened={partModal}
        onClose={() => {
          setPartModal(false)
          setEditingPart(null)
        }}
        title={editingPart ? 'Qismni tahrirlash' : 'Yangi qism'}
        centered
      >
        <form onSubmit={handleSavePart}>
          <Stack>
            <NumberInput
              label="Qism raqami"
              min={1}
              value={partForm.number}
              onChange={numberHandler(setPartForm, 'number')}
              required
            />
            <NumberInput
              label="Fasl raqami (ixtiyoriy)"
              min={1}
              value={partForm.season_number}
              onChange={numberHandler(setPartForm, 'season_number')}
            />
            <TextInput
              label="Sarlavha (ixtiyoriy)"
              value={partForm.title}
              onChange={inputHandler(setPartForm, 'title')}
            />
            <Group justify="flex-end">
              <button
                type="button"
                className="admin-btn admin-btn-secondary"
                onClick={() => {
                  setPartModal(false)
                  setEditingPart(null)
                }}
              >
                Bekor
              </button>
              <button type="submit" className="admin-btn admin-btn-primary" disabled={savingPart}>
                {savingPart ? 'Saqlanmoqda…' : editingPart ? 'Saqlash' : 'Yaratish'}
              </button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(deletePart)}
        title="Qismni o'chirish"
        message={`${deletePart?.number}-qism va undagi barcha media o'chiriladi.`}
        confirmLabel="O'chirish"
        danger
        loading={busy}
        onCancel={() => setDeletePart(null)}
        onConfirm={handleDeletePart}
      />

      <ConfirmDialog
        open={Boolean(deleteMediaItem)}
        title="Telegram media o'chirish"
        message="Ushbu media fayl qismdan o'chiriladi."
        confirmLabel="O'chirish"
        danger
        loading={busy}
        onCancel={() => setDeleteMediaItem(null)}
        onConfirm={handleDeleteMediaItem}
      />

      {announceFor === slug ? (
        <AnnounceModal
          open
          media={media}
          onClose={() => setAnnounceFor(null)}
          onSent={setSuccess}
        />
      ) : null}
    </Stack>
  )
}

// «📢 E'lon qilish»: the exact message is previewed before anything is sent and
// the operator chooses where it goes — the public channel, every bot user, or
// both at once. An ongoing title only asks which episode(s) to announce; a
// finished one always announces the whole run.
function AnnounceModal({ open, media, onClose, onSent }) {
  const isOngoing = media?.status === 'ongoing'
  const [scope, setScope] = useState('last')
  const [targets, setTargets] = useState(['channel'])
  const [preview, setPreview] = useState(null)
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)

  const effectiveScope = isOngoing ? scope : 'all'

  useEffect(() => {
    if (!open || !media?.slug) return undefined
    let active = true
    setLoading(true)
    setError(null)
    adminMediaApi
      .announcePreview(media.slug, effectiveScope)
      .then((data) => {
        if (active) setPreview(data)
      })
      .catch((err) => {
        if (active) setError(formatError(err, "E'lon ma'lumotini yuklashda xatolik."))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [open, media?.slug, effectiveScope])

  function toggleTarget(value) {
    setTargets((prev) =>
      prev.includes(value) ? prev.filter((item) => item !== value) : [...prev, value],
    )
  }

  async function handleSend() {
    if (!targets.length) {
      setError('Kamida bitta manzilni tanlang: kanal yoki foydalanuvchilar.')
      return
    }
    setSending(true)
    setError(null)
    try {
      const result = await adminMediaApi.announce(media.slug, {
        targets,
        scope: effectiveScope,
      })
      const parts = []
      if (result.channel_message_id) parts.push('Kanalga joylandi')
      if (result.channel_error) parts.push(`Kanal: ${result.channel_error}`)
      if (result.users_started) {
        parts.push(`${result.users_total} ta foydalanuvchiga yuborilmoqda`)
      }
      if (result.users_error) parts.push(result.users_error)
      onSent?.(parts.join(' · ') || "E'lon yuborildi.")
      onClose()
    } catch (err) {
      setError(formatError(err, "E'lon yuborishda xatolik."))
    } finally {
      setSending(false)
    }
  }

  const previewText = (preview?.caption || '').replace(/<\/?b>/g, '')

  return (
    <Modal
      opened={open}
      onClose={onClose}
      title="E'lon qilish"
      centered
      size="lg"
    >
      <Stack gap="md">
        <Text size="sm" c="dimmed">
          E'lon quyidagi ko'rinishda yuboriladi: muqova, nomi, qismlar, reyting,
          davomiyligi, qism/umumiy qism, sifat va «{preview?.button_label || '▶️ Tomosha qilish'}»
          tugmasi (botga start havolasi bilan).
        </Text>

        {isOngoing ? (
          <Select
            label="Qaysi qismlar e'lon qilinsin?"
            data={[
              { value: 'last', label: 'Faqat oxirgi qism' },
              { value: 'all', label: 'Barcha qismlar' },
            ]}
            value={scope}
            onChange={(value) => setScope(value || 'last')}
            allowDeselect={false}
          />
        ) : (
          <Text size="sm">
            Bu media tugallangan — e'lon barcha qismlar bilan yuboriladi.
          </Text>
        )}

        <Stack gap="xs">
          <Text fw={600} size="sm">Kimga yuborilsin?</Text>
          <Checkbox
            checked={targets.includes('channel')}
            onChange={() => toggleTarget('channel')}
            label="Kanalga"
            description={
              preview?.channel_title || "E'lon kanali sozlamalarda tanlanmagan"
            }
          />
          <Checkbox
            checked={targets.includes('users')}
            onChange={() => toggleTarget('users')}
            label="Barcha foydalanuvchilarga"
            description={`${preview?.recipients ?? 0} ta bot foydalanuvchisi`}
          />
        </Stack>

        <div>
          <Text fw={600} size="sm" mb={6}>Xabar ko'rinishi</Text>
          {loading ? (
            <Loader size="sm" />
          ) : (
            <pre className="admin-announce-preview">{previewText || '—'}</pre>
          )}
        </div>

        <ErrorAlert>{error}</ErrorAlert>

        <Group justify="flex-end">
          <button
            type="button"
            className="admin-btn admin-btn-secondary"
            onClick={onClose}
            disabled={sending}
          >
            Bekor
          </button>
          <button
            type="button"
            className="admin-btn admin-btn-primary"
            onClick={handleSend}
            disabled={sending || loading || !targets.length}
          >
            {sending ? 'Yuborilmoqda…' : "E'lon qilish"}
          </button>
        </Group>
      </Stack>
    </Modal>
  )
}

function PartMediaList({ partId, onError, onDelete }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [copiedId, setCopiedId] = useState(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    adminMediaApi
      .telegramMedia(partId)
      .then((data) => {
        if (active) setItems(data)
      })
      .catch((err) => {
        if (active) onError?.(formatError(err))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [partId, onError])

  async function copyFileId(item) {
    const ok = await copyText(item.file_id)
    if (ok) {
      setCopiedId(item.id)
      setTimeout(() => setCopiedId(null), 1500)
    }
  }

  if (loading) return <Text size="sm" c="dimmed" mt="sm">Yuklanmoqda…</Text>
  if (!items.length) {
    return (
      <Text size="sm" c="dimmed" mt="sm">
        Ushbu qismda Telegram media yo'q. file_id bilan qo'shing.
      </Text>
    )
  }

  return (
    <div className="admin-media-list" style={{ marginTop: 10 }}>
      {items.map((item) => (
        <Group key={item.id} justify="space-between" className="admin-media-row" py={4}>
          <Group gap="xs" style={{ minWidth: 0 }}>
            <i
              className={`bi bi-${item.media_type === 'video' ? 'play-btn' : item.media_type === 'photo' ? 'image' : 'file-earmark'}`}
              aria-hidden="true"
            />
            <Text size="sm">{item.media_type} · #{item.order}</Text>
            <Text size="xs" c="dimmed" style={{ fontFamily: 'monospace' }}>
              {item.file_id.slice(0, 32)}…
            </Text>
            {copiedId === item.id ? (
              <Text size="xs" c="green">nusxalandi</Text>
            ) : null}
          </Group>
          <Group gap={4} wrap="nowrap">
            <ActionIcon
              variant="subtle"
              size="sm"
              onClick={() => copyFileId(item)}
              title="file_id nusxalash"
            >
              <i className="bi bi-clipboard" />
            </ActionIcon>
            <ActionIcon
              variant="subtle"
              color="red"
              size="sm"
              onClick={() => onDelete?.(item)}
              title="O'chirish"
            >
              <i className="bi bi-x" />
            </ActionIcon>
          </Group>
        </Group>
      ))}
    </div>
  )
}
