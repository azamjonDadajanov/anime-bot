import { useState, useEffect, useRef } from 'react'
import { Modal, Loader } from '@mantine/core'
import { Link } from 'react-router-dom'
import { mediaApi } from '../apis/api'
import { coverSrc } from '../apis/mediaUrl'
import { episodeLabel, normalizeList, statusLabel, typeIcon, typeLabel } from '../mediaMeta'

const PAGE_SIZE = 10

function SearchModal({ opened, onClose }) {
  const [query, setQuery] = useState('')
  const [items, setItems] = useState([])
  const [suggestions, setSuggestions] = useState([])
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [searched, setSearched] = useState(false)
  const inputRef = useRef(null)
  const resultsRef = useRef(null)
  const sentinelRef = useRef(null)

  const search = query.trim()

  useEffect(() => {
    if (!opened) return undefined
    const timer = window.setTimeout(() => inputRef.current?.focus(), 50)
    return () => window.clearTimeout(timer)
  }, [opened])

  // Idle state: real trending titles instead of an empty box.
  useEffect(() => {
    if (!opened) return undefined
    let active = true
    mediaApi.popular()
      .then((data) => active && setSuggestions(normalizeList(data).slice(0, 5)))
      .catch(() => {})
    return () => { active = false }
  }, [opened])

  useEffect(() => {
    const term = query.trim()
    if (!term) return undefined

    let active = true
    const timer = window.setTimeout(() => {
      mediaApi.catalog({ search: term })
        .then((data) => {
          if (!active) return
          setItems(normalizeList(data))
          setError('')
        })
        .catch(() => active && setError("Server bilan bog'lanishda xatolik yuz berdi."))
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
    if (!opened) return undefined
    const root = resultsRef.current
    const target = sentinelRef.current
    if (!root || !target) return undefined

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

  function pickSuggestion(title) {
    setLoading(true)
    setError('')
    setVisibleCount(PAGE_SIZE)
    setQuery(title)
    inputRef.current?.focus()
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
        {!loading && error && <p className="search-modal-state is-error">{error}</p>}

        {!search && (
          <div className="search-idle">
            <span className="search-idle-title">Trenddagi signallar</span>
            <div className="search-suggestions">
              {suggestions.map((item) => (
                <button
                  className="search-suggestion"
                  type="button"
                  key={item.id}
                  onClick={() => pickSuggestion(item.title)}
                >
                  <i className={`bi ${typeIcon(item)}`} aria-hidden="true" />
                  {item.title}
                </button>
              ))}
              {!suggestions.length && (
                <span className="search-modal-state">Qidirish uchun nom kiriting.</span>
              )}
            </div>
            <div className="search-hint">
              <span><kbd className="search-modal-kbd">Ctrl</kbd> <kbd className="search-modal-kbd">K</kbd> ochish</span>
              <span>Enter — birinchi natija</span>
              <span>Esc — yopish</span>
            </div>
          </div>
        )}

        {!loading && !error && search && searched && !results.length && (
          <div className="search-idle">
            <p className="search-modal-state">Hech narsa topilmadi.</p>
            <div className="search-suggestions">
              {suggestions.slice(0, 3).map((item) => (
                <button
                  className="search-suggestion"
                  type="button"
                  key={item.id}
                  onClick={() => pickSuggestion(item.title)}
                >
                  <i className={`bi ${typeIcon(item)}`} aria-hidden="true" />
                  {item.title}
                </button>
              ))}
            </div>
          </div>
        )}

        {!loading && !error && visibleResults.map((item) => (
          <Link className="search-result" to={`/media/${item.slug}`} key={item.id} onClick={handleClose}>
            <span className="search-result-thumb">
              {coverSrc(item)
                ? <img src={coverSrc(item)} alt="" loading="lazy" />
                : <i className={`bi ${typeIcon(item)}`} aria-hidden="true" />}
            </span>
            <span className="search-result-body">
              <span className="search-result-title">{item.title}</span>
              <span className="search-result-meta">
                <span>{typeLabel(item)}</span>
                <span className="dot" aria-hidden="true" />
                <span>{statusLabel(item)}</span>
                <span className="dot" aria-hidden="true" />
                <span>{episodeLabel(item)}</span>
                {item.rating ? (
                  <>
                    <span className="dot" aria-hidden="true" />
                    <span>{item.rating}/10</span>
                  </>
                ) : null}
              </span>
            </span>
            <i className="bi bi-arrow-up-right search-result-arrow" aria-hidden="true" />
          </Link>
        ))}

        {!loading && !error && results.length > visibleCount && (
          <div className="search-modal-sentinel" ref={sentinelRef} />
        )}
      </div>

      {!loading && !error && visibleCount < results.length && (
        <p className="search-modal-more">
          Pastga aylantiring · yana {results.length - visibleCount} ta natija
        </p>
      )}
    </Modal>
  )
}

export default SearchModal
