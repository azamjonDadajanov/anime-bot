import { useState, useEffect, useRef } from 'react'
import { Modal, Text, Loader, Badge, Group } from '@mantine/core'
import { Link } from 'react-router-dom'
import { mediaApi } from '../apis/api'

const mediaTypeLabels = {
  movie: 'Kino',
  anime: 'Anime',
  series: 'Serial',
  manga: 'Manga',
}

const statusLabels = {
  upcoming: 'Kutilmoqda',
  ongoing: 'Davom etmoqda',
  completed: 'Tugallangan',
}

// Fallback glyph per media type, shown while (or instead of) a cover image.
const thumbIcons = {
  movie: 'bi-film',
  anime: 'bi-stars',
  series: 'bi-collection-play',
  manga: 'bi-journal-bookmark',
}

const PAGE_SIZE = 10

function SearchModal({ opened, onClose }) {
  const [query, setQuery] = useState('')
  const [items, setItems] = useState([])
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [searched, setSearched] = useState(false)
  const inputRef = useRef(null)
  const resultsRef = useRef(null)
  const sentinelRef = useRef(null)

  const search = query.trim()

  useEffect(() => {
    if (!opened) return
    const timer = window.setTimeout(() => inputRef.current?.focus(), 50)
    return () => window.clearTimeout(timer)
  }, [opened])

  useEffect(() => {
    const term = query.trim()
    if (!term) return

    let active = true
    const timer = window.setTimeout(() => {
      mediaApi.catalog({ search: term })
        .then((data) => {
          if (!active) return
          setItems(Array.isArray(data) ? data : data.results || [])
          setError('')
        })
        .catch(() => active && setError('Server bilan bog\'lanishda xatolik yuz berdi.'))
        .finally(() => {
          if (!active) return
          setLoading(false)
          setSearched(true)
        })
    }, 300)

    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [query])

  useEffect(() => {
    if (!opened) return
    const root = resultsRef.current
    const target = sentinelRef.current
    if (!root || !target) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisibleCount((count) => Math.min(count + PAGE_SIZE, items.length))
        }
      },
      { root, rootMargin: '100px 0px' },
    )
    observer.observe(target)
    return () => observer.disconnect()
  }, [opened, items.length, visibleCount])

  function handleChange(event) {
    setLoading(true)
    setError('')
    setVisibleCount(PAGE_SIZE)
    setQuery(event.currentTarget.value)
  }

  function handleClear() {
    setQuery('')
    setItems([])
    setError('')
    setSearched(false)
    setLoading(false)
    setVisibleCount(PAGE_SIZE)
    inputRef.current?.focus()
  }

  function handleClose() {
    setQuery('')
    setItems([])
    setError('')
    setSearched(false)
    setLoading(false)
    setVisibleCount(PAGE_SIZE)
    onClose()
  }

  const results = search ? items : []
  const visibleResults = results.slice(0, visibleCount)

  function handleScroll(event) {
    const list = event.currentTarget
    if (list.scrollHeight - list.scrollTop - list.clientHeight > 80) return
    setVisibleCount((count) => Math.min(count + PAGE_SIZE, results.length))
  }

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      centered
      size="xl"
      radius="lg"
      withCloseButton={false}
      classNames={{ content: 'search-modal', body: 'search-modal-body' }}
    >
      <div className="search-modal-field">
        <i className="bi bi-search search-modal-icon" aria-hidden="true" />
        <input
          ref={inputRef}
          className="search-modal-input"
          type="text"
          aria-label="Katalogdan qidirish"
          placeholder="Kino, anime, serial yoki manga qidirish"
          autoComplete="off"
          value={query}
          onChange={handleChange}
        />
        {search && (
          <button
            className="search-modal-clear"
            type="button"
            aria-label="Tozalash"
            title="Tozalash"
            onClick={handleClear}
          >
            <i className="bi bi-x-lg" aria-hidden="true" />
          </button>
        )}
        <kbd className="search-modal-kbd">Esc</kbd>
      </div>

      <div className="search-modal-results" ref={resultsRef} onScroll={handleScroll}>
        {loading && search && <div className="search-modal-state"><Loader size="sm" /></div>}
        {!loading && error && <Text className="search-modal-state" c="red">{error}</Text>}
        {!search && (
          <Text className="search-modal-state" c="dimmed">Qidirish uchun nom kiriting.</Text>
        )}
        {!loading && !error && search && searched && !results.length && (
          <Text className="search-modal-state" c="dimmed">Hech narsa topilmadi.</Text>
        )}
        {!loading && !error && visibleResults.map((item) => (
          <Link className="search-result" to={`/media/${item.slug}`} key={item.id} onClick={handleClose}>
            <Group gap="xs" wrap="nowrap">
              <span className="search-result-thumb" aria-hidden="true">
                {item.cover
                  ? <img src={`data:${item.cover_content_type || 'image/jpeg'};base64,${item.cover}`} alt="" loading="lazy" />
                  : <i className={`bi ${thumbIcons[item.type] || 'bi-film'}`} />}
              </span>
              <div>
                <Text className="search-result-title">{item.title}</Text>
                <Group gap="xs" className="search-result-meta">
                  <Badge variant="light">{statusLabels[item.status] || item.status || 'Noma\'lum'}</Badge>
                  <Text size="xs" c="dimmed">
                    {item.episode_count ? `${item.episode_count} qism` : 'Qismlar yo\'q'}
                  </Text>
                  <Text size="xs" c="dimmed">{mediaTypeLabels[item.type] || item.type}</Text>
                </Group>
              </div>
            </Group>
          </Link>
        ))}
        {!loading && !error && results.length > visibleCount && (
          <div className="search-modal-sentinel" ref={sentinelRef} />
        )}
      </div>
      {!loading && !error && visibleCount < results.length && (
        <Text className="search-modal-more" size="xs" c="dimmed">
          Pastga aylantiring · yana {results.length - visibleCount} ta natija
        </Text>
      )}
    </Modal>
  )
}

export default SearchModal
