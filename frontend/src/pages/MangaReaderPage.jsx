import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Badge, Button, Loader, Text } from '@mantine/core'
import { Link, useNavigate, useParams } from 'react-router-dom'
import * as pdfjsLib from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { getAccessToken, hasAccessToken, mediaApi, readingApi } from '../apis/api'
import { useAuth } from '../apis/useAuth'
import {
  computeResume,
  loadTitleProgress,
  orderParts,
  saveLocalProgress,
} from '../reading'

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl

const MAX_CANVAS_DIM = 8192

function isCompactViewport() {
  return typeof window !== 'undefined' && window.innerWidth <= 850
}

function documentParams(partId) {
  const params = {
    url: mediaApi.partPdfUrl(partId),
    disableRange: true,
    disableStream: true,
  }
  const token = getAccessToken()
  if (token) params.httpHeaders = { Authorization: `Bearer ${token}` }
  return params
}

function partLabel(part) {
  if (!part) return ''
  const season = part.season_number ? `${part.season_number}-fasl · ` : ''
  return `${season}${part.number}-qism`
}

function errorText(error) {
  const data = error.response?.data
  if (!data) return 'Server bilan bog\'lanishda xatolik yuz berdi.'
  if (typeof data.detail === 'string') return data.detail
  if (typeof data === 'string') return data
  return 'Ma\'lumotni yuklab bo\'lmadi.'
}

function MangaReaderPage() {
  const { slug, number } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const isStaff = Boolean(user?.is_staff)
  const initialNumberRef = useRef(number)

  const [item, setItem] = useState(null)
  const [parts, setParts] = useState([])
  const [progress, setProgress] = useState({})
  const [currentPart, setCurrentPart] = useState(null)
  const [loadedKey, setLoadedKey] = useState('')
  const [error, setError] = useState('')
  const [errorKey, setErrorKey] = useState('')

  const [pdfDoc, setPdfDoc] = useState(null)
  const [page, setPage] = useState(1)
  const [numPages, setNumPages] = useState(0)
  const [loadedPdfId, setLoadedPdfId] = useState(null)
  const [pdfError, setPdfError] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(() => !isCompactViewport())
  const [upload, setUpload] = useState({ uploading: false, progress: 0, error: '' })
  const [layoutKey, setLayoutKey] = useState(0)

  const mainRef = useRef(null)
  const pagesRef = useRef(null)
  const canvasRefs = useRef({})
  const pageRefs = useRef({})
  const pdfTaskRef = useRef(null)
  const fileInputRef = useRef(null)
  const activePageRef = useRef(1)
  const lastPersistRef = useRef(0)
  const scrollTargetRef = useRef(null)

  const key = slug
  const loading = loadedKey !== key

  useEffect(() => {
    let active = true
    mediaApi.detail(slug)
      .then(async (data) => {
        const ordered = orderParts(data.parts || [])
        const stored = await loadTitleProgress(slug)
        if (!active) return
        const resume = computeResume(stored, ordered)
        const requestedNumber = initialNumberRef.current
        const requested = requestedNumber
          ? ordered.find((part) => String(part.number) === String(requestedNumber))
          : null
        const target = requested || (resume ? resume.part : ordered[0]) || null
        const startPage = requested
          ? 1
          : resume && target && resume.part.id === target.id
            ? resume.page
            : 1
        activePageRef.current = startPage
        lastPersistRef.current = startPage
        setItem(data)
        setParts(ordered)
        setProgress(stored)
        setCurrentPart(target)
        setPage(startPage)
        setError('')
        setLoadedKey(key)
      })
      .catch((requestError) => {
        if (!active) return
        setError(errorText(requestError))
        setErrorKey(key)
        setLoadedKey(key)
      })
    return () => { active = false }
  }, [slug, key])

  useEffect(() => {
    if (!currentPart || !currentPart.has_pdf) return undefined
    let cancelled = false
    mediaApi.partPdfMeta(currentPart.id)
      .then((meta) => {
        if (cancelled) return null
        if (!meta?.available) {
          setPdfError({ partId: currentPart.id, message: meta?.reason || 'PDF yuklanmadi.' })
          setLoadedPdfId(currentPart.id)
          return null
        }
        const task = pdfjsLib.getDocument(documentParams(currentPart.id))
        pdfTaskRef.current = task
        return task.promise
          .then((doc) => {
            if (cancelled) {
              doc.destroy()
              return
            }
            scrollTargetRef.current = activePageRef.current
            setPdfDoc(doc)
            setNumPages(doc.numPages)
            setPage((prev) => Math.min(Math.max(prev, 1), doc.numPages))
            setLoadedPdfId(currentPart.id)
            setPdfError(null)
          })
          .catch((loadError) => {
            if (cancelled) return
            setPdfError({ partId: currentPart.id, message: errorText(loadError) || 'PDF yuklanmadi.' })
            setLoadedPdfId(currentPart.id)
          })
      })
      .catch((metaError) => {
        if (cancelled) return
        setPdfError({ partId: currentPart.id, message: errorText(metaError) || 'PDF yuklanmadi.' })
        setLoadedPdfId(currentPart.id)
      })
    return () => {
      cancelled = true
      pdfTaskRef.current?.destroy?.()
      pdfTaskRef.current = null
    }
  }, [currentPart])

  const persist = useCallback((part, pageValue, isRead) => {
    if (!part) return
    const record = saveLocalProgress(slug, part, { page: pageValue, isRead })
    setProgress((prev) => ({ ...prev, [part.id]: record }))
    if (hasAccessToken()) {
      readingApi.save({ part: part.id, page: pageValue, isRead }).catch(() => {})
    }
  }, [slug])

  useEffect(() => {
    const doc = pdfDoc
    const container = mainRef.current
    const pages = pagesRef.current
    if (!doc || !container || !pages) return undefined
    const ratio = Math.min(window.devicePixelRatio || 1, 2)
    const rendered = new Set()
    let cancelled = false

    const renderPage = async (pageNumber, canvas) => {
      if (cancelled || !canvas || rendered.has(pageNumber)) return
      rendered.add(pageNumber)
      try {
        const pdfPage = await doc.getPage(pageNumber)
        if (cancelled) return
        const base = pdfPage.getViewport({ scale: 1 })
        const available = Math.max(280, (pages.clientWidth || container.clientWidth || 900) - 4)
        const layoutScale = Math.max(0.2, Math.min(available / base.width, 2.5))
        const cssWidth = base.width * layoutScale
        const cssHeight = base.height * layoutScale
        const pageRatio = Math.max(
          1,
          Math.min(ratio, MAX_CANVAS_DIM / cssWidth, MAX_CANVAS_DIM / cssHeight),
        )
        canvas.width = Math.max(1, Math.round(cssWidth * pageRatio))
        canvas.height = Math.max(1, Math.round(cssHeight * pageRatio))
        canvas.style.width = `${Math.round(cssWidth)}px`
        canvas.style.height = `${Math.round(cssHeight)}px`
        const viewport = pdfPage.getViewport({ scale: layoutScale })
        await pdfPage.render({
          canvas,
          canvasContext: canvas.getContext('2d'),
          viewport,
          transform: pageRatio !== 1 ? [pageRatio, 0, 0, pageRatio, 0, 0] : undefined,
        }).promise
      } catch {
        rendered.delete(pageNumber)
      }
    }

    const renderObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        const pageNumber = Number(entry.target.dataset.page)
        renderPage(pageNumber, canvasRefs.current[pageNumber])
      }
    }, { root: container, rootMargin: '300% 0px' })

    const pageObserver = new IntersectionObserver((entries) => {
      let best = null
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        const pageNumber = Number(entry.target.dataset.page)
        if (best === null || pageNumber < best) best = pageNumber
      }
      if (best === null) return
      activePageRef.current = best
      setPage(best)
      if (best !== lastPersistRef.current) {
        lastPersistRef.current = best
        persist(currentPart, best, best >= numPages ? true : undefined)
      }
    }, { root: container, rootMargin: '-45% 0px -45% 0px', threshold: 0 })

    Object.values(pageRefs.current).forEach((element) => {
      if (!element) return
      renderObserver.observe(element)
      pageObserver.observe(element)
    })

    const target = scrollTargetRef.current
    if (target && pageRefs.current[target]) {
      scrollTargetRef.current = null
      requestAnimationFrame(() => {
        pageRefs.current[target]?.scrollIntoView({ block: 'start' })
      })
    }

    return () => {
      cancelled = true
      renderObserver.disconnect()
      pageObserver.disconnect()
    }
  }, [pdfDoc, numPages, layoutKey, currentPart, persist])

  useEffect(() => {
    const container = mainRef.current
    if (!container || typeof ResizeObserver === 'undefined') return undefined
    let timer = null
    let first = true
    const observer = new ResizeObserver(() => {
      if (first) {
        first = false
        return
      }
      clearTimeout(timer)
      timer = setTimeout(() => setLayoutKey((value) => value + 1), 150)
    })
    observer.observe(container)
    return () => {
      clearTimeout(timer)
      observer.disconnect()
    }
  }, [loadedKey])

  const goToPage = useCallback((next) => {
    if (!numPages) return
    const target = Math.min(Math.max(next, 1), numPages)
    activePageRef.current = target
    lastPersistRef.current = target
    setPage(target)
    persist(currentPart, target, target >= numPages ? true : undefined)
    pageRefs.current[target]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [numPages, currentPart, persist])

  const openPart = useCallback((part) => {
    if (!part) return
    setCurrentPart(part)
    setPage(1)
    setPdfDoc(null)
    setNumPages(0)
    setPdfError(null)
    activePageRef.current = 1
    lastPersistRef.current = 0
    if (isCompactViewport()) setSidebarOpen(false)
    persist(part, 1)
    mainRef.current?.scrollTo({ top: 0 })
    navigate(`/read/${slug}/${part.number}`, { replace: true })
  }, [navigate, slug, persist])

  const handlePdfSelected = useCallback(async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !currentPart) return
    setUpload({ uploading: true, progress: 0, error: '' })
    try {
      await mediaApi.uploadPartPdf(currentPart.id, file, (progress) => {
        setUpload((prev) => ({ ...prev, progress }))
      })
      const partId = currentPart.id
      setParts((prev) => prev.map((part) => (part.id === partId ? { ...part, has_pdf: true } : part)))
      setCurrentPart((prev) => (prev && prev.id === partId ? { ...prev, has_pdf: true } : prev))
      setPdfError(null)
      setUpload({ uploading: false, progress: 100, error: '' })
    } catch (uploadError) {
      setUpload({ uploading: false, progress: 0, error: errorText(uploadError) })
    }
  }, [currentPart])

  useEffect(() => {
    function onKeyDown(event) {
      if (event.key === 'ArrowRight') goToPage(page + 1)
      if (event.key === 'ArrowLeft') goToPage(page - 1)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [goToPage, page])

  if (loading) return <div className="reader-state"><Loader /></div>
  if (errorKey === key && error) {
    return <div className="reader-state"><Alert color="red" title="Xatolik">{error}</Alert></div>
  }
  if (!item) return <div className="reader-state"><Alert color="red">Manga topilmadi.</Alert></div>

  const currentIndex = parts.findIndex((part) => part.id === currentPart?.id)
  const prevPart = currentIndex > 0 ? parts[currentIndex - 1] : null
  const nextPart = currentIndex >= 0 && currentIndex < parts.length - 1 ? parts[currentIndex + 1] : null
  const hasPdf = Boolean(currentPart?.has_pdf)
  const pdfReady = Boolean(currentPart) && loadedPdfId === currentPart.id
  const currentPdfError = pdfError && currentPart && pdfError.partId === currentPart.id
    ? pdfError.message
    : ''

  return (
    <div className="reader">
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        hidden
        onChange={handlePdfSelected}
      />
      <header className="reader-navbar">
        <Button
          variant="subtle"
          size="compact-sm"
          className="reader-parts-btn"
          leftSection={<i className="bi bi-layout-sidebar-inset" aria-hidden="true" />}
          onClick={() => setSidebarOpen((open) => !open)}
          aria-label="Qismlar paneli"
        >
          Qismlar
        </Button>
        <Link className="reader-back" to={`/media/${slug}`}>
          <i className="bi bi-arrow-left" aria-hidden="true" />
        </Link>
        <div className="reader-title">
          <b>{item.title}</b>
          <span>{partLabel(currentPart)}</span>
        </div>
        <div className="reader-pager">
          <Button.Group>
            <Button variant="default" disabled={page <= 1} onClick={() => goToPage(page - 1)} aria-label="Oldingi sahifa">
              <i className="bi bi-chevron-left" aria-hidden="true" />
            </Button>
            <Button variant="default" disabled={!numPages || page >= numPages} onClick={() => goToPage(page + 1)} aria-label="Keyingi sahifa">
              <i className="bi bi-chevron-right" aria-hidden="true" />
            </Button>
          </Button.Group>
          <Text size="sm" className="reader-page-count">{page} / {numPages || '—'}</Text>
        </div>
        {isStaff && (
          <Button
            variant="light"
            size="compact-sm"
            className="reader-upload-btn"
            leftSection={<i className="bi bi-upload" aria-hidden="true" />}
            loading={upload.uploading}
            onClick={() => fileInputRef.current?.click()}
          >
            {hasPdf ? 'PDF almashtirish' : 'PDF yuklash'}
          </Button>
        )}
      </header>

      <div className="reader-body">
        {sidebarOpen && (
          <aside className="reader-sidebar" aria-label="Qismlar">
            <Text className="reader-sidebar-title">Qismlar</Text>
            <div className="reader-sidebar-list">
              {parts.map((part) => {
                const info = progress[part.id]
                const isRead = Boolean(info?.isRead)
                const isActive = part.id === currentPart?.id
                return (
                  <button
                    key={part.id}
                    type="button"
                    className={`reader-part${isActive ? ' active' : ''}`}
                    onClick={() => openPart(part)}
                  >
                    <span className="reader-part-main">
                      <b>{part.number}-qism</b>
                      <span>{part.title || item.title}</span>
                    </span>
                    {isRead
                      ? <i className="bi bi-check-circle-fill reader-part-read" aria-label="O'qilgan" />
                      : <span className="reader-part-dot" aria-hidden="true" />}
                  </button>
                )
              })}
            </div>
          </aside>
        )}

        <main className="reader-main" ref={mainRef}>
          {upload.uploading && (
            <div className="reader-upload-status">
              <Text size="sm">PDF yuklanmoqda… {upload.progress}%</Text>
            </div>
          )}
          {upload.error && (
            <Alert className="reader-upload-status" color="red" title="Yuklashda xatolik">
              {upload.error}
            </Alert>
          )}
          {currentPdfError && (
            <div className="reader-message">
              <i className="bi bi-file-earmark-x" aria-hidden="true" />
              <Text>{currentPdfError}</Text>
              {isStaff && <Text size="sm" c="dimmed">PDF ni yuklash uchun yuqoridagi «PDF yuklash» tugmasini bosing.</Text>}
            </div>
          )}
          {!currentPdfError && currentPart && !hasPdf && (
            <div className="reader-message">
              <i className="bi bi-file-earmark-x" aria-hidden="true" />
              <Text>Bu qism uchun PDF hali yuklanmagan.</Text>
              {isStaff && <Text size="sm" c="dimmed">PDF ni yuklash uchun yuqoridagi «PDF yuklash» tugmasini bosing.</Text>}
            </div>
          )}
          {!currentPdfError && hasPdf && !pdfReady && (
            <div className="reader-message"><Loader /></div>
          )}
          {!currentPdfError && pdfReady && (
            <div className="reader-pages" ref={pagesRef}>
              {Array.from({ length: numPages }, (_, index) => index + 1).map((pageNumber) => (
                <div
                  key={pageNumber}
                  className="reader-page"
                  data-page={pageNumber}
                  ref={(element) => {
                    if (element) pageRefs.current[pageNumber] = element
                    else delete pageRefs.current[pageNumber]
                  }}
                >
                  <canvas
                    className="reader-canvas"
                    ref={(element) => {
                      if (element) canvasRefs.current[pageNumber] = element
                      else delete canvasRefs.current[pageNumber]
                    }}
                  />
                </div>
              ))}
            </div>
          )}

          <div className="reader-bottom-bar">
            <Button variant="default" disabled={!prevPart} onClick={() => openPart(prevPart)}>
              <i className="bi bi-arrow-left" aria-hidden="true" /> Oldingi qism
            </Button>
            {progress[currentPart?.id]?.isRead && <Badge color="teal" variant="light">O'qilgan</Badge>}
            <Button variant="default" disabled={!nextPart} onClick={() => openPart(nextPart)}>
              Keyingi qism <i className="bi bi-arrow-right" aria-hidden="true" />
            </Button>
          </div>
        </main>
      </div>
    </div>
  )
}

export default MangaReaderPage
