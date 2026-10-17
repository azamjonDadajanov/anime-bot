import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ActionIcon, Badge, Loader, ScrollArea, Text, Textarea } from '@mantine/core'
import { aiApi } from '../apis/api'

const MAX_QUERY = 300
// How many results one answer shows, and the most we ever ask for: the search
// finds *every* matching title, so the answer is a page of the strongest ones
// and the rest is one click away (see the "show more" button).
const PAGE_SIZE = 6
const MAX_RESULTS = 30

// Anything that shows off what the search can do: the words below never appear
// in a title, a genre or a synopsis — that is the point of the feature.
const SUGGESTIONS = [
  "sarguzasht va qo'rqinchli animelar",
  "romantik maktab hayoti haqida",
  "kuchli qahramon janglari",
  "sirli va o'ylantiradigan seriallar",
]

function timestamp() {
  return new Date().toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' })
}

function parseAnswer(data, limit) {
  const results = Array.isArray(data?.results) ? data.results : []
  // The reasoning model's own words: an answer plus the short "fikrlash"
  // trace it produced before choosing. Both are empty when no model is
  // configured, and the list below is the whole answer then.
  const answer = String(data?.answer || '')
  const thinking = String(data?.thinking || '')
  if (!results.length) {
    // The model answered a conversational question ("who are you", "what can
    // you do") rather than searching: show only its words.
    if (data?.conversational && answer) {
      return { role: 'ai', kind: 'answer', query: data?.query || '', answer, thinking }
    }
    return { role: 'ai', kind: 'empty', query: data?.query || '', answer, thinking }
  }
  return {
    role: 'ai',
    kind: 'results',
    query: data.query,
    results,
    answer,
    thinking,
    // `total` counts every match in the catalogue, `results` the ones returned.
    total: Number(data.total ?? results.length),
    limit,
  }
}

function ResultCard({ item }) {
  const score = Math.round((item.score || 0) * 100)
  const meta = [item.type_display, item.release_year, item.rating ? `⭐ ${item.rating}/10` : '']
    .filter(Boolean)
    .join(' · ')

  return (
    <li className="ai-result">
      <Link className="ai-result-title" to={`/media/${item.slug}`}>
        {item.title}
      </Link>
      <div className="ai-result-meta">
        <span>{meta}</span>
        {score > 0 && (
          <Badge size="xs" variant="light" color="blue">
            {score}% mos
          </Badge>
        )}
      </div>
      {/* One sentence, exactly as the API computed it from the synopsis. */}
      <p className="ai-result-summary">{item.summary}</p>
    </li>
  )
}

function AiSearchChat() {
  const [opened, setOpened] = useState(false)
  const [text, setText] = useState('')
  const [messages, setMessages] = useState([])
  const [busy, setBusy] = useState(false)
  const inputRef = useRef(null)
  const viewportRef = useRef(null)

  useEffect(() => {
    if (!opened) return undefined
    const timer = setTimeout(() => inputRef.current?.focus(), 60)
    return () => clearTimeout(timer)
  }, [opened])

  useEffect(() => {
    if (!opened) return undefined
    function handleKeydown(event) {
      if (event.key === 'Escape') setOpened(false)
    }
    window.addEventListener('keydown', handleKeydown)
    return () => window.removeEventListener('keydown', handleKeydown)
  }, [opened])

  useEffect(() => {
    const viewport = viewportRef.current
    if (viewport) viewport.scrollTo({ top: viewport.scrollHeight, behavior: 'smooth' })
  }, [messages, busy])

  function push(message) {
    setMessages((current) => [...current, message])
  }

  async function request(query, limit) {
    setBusy(true)
    try {
      const data = await aiApi.search(query, { limit })
      return parseAnswer(data, limit)
    } catch (error) {
      const status = error.response?.status
      const detail = error.response?.data?.detail
      if (status === 403) {
        return { role: 'ai', kind: 'locked', detail }
      }
      if (status === 503) {
        return { role: 'ai', kind: 'unavailable', detail }
      }
      return { role: 'ai', kind: 'error', detail }
    } finally {
      setBusy(false)
    }
  }

  async function ask(value) {
    const query = (value ?? text).trim()
    if (!query || busy) return
    push({ role: 'user', text: query })
    setText('')
    push(await request(query, PAGE_SIZE))
  }

  /** Re-ask the same question with a larger limit, in place of the old answer. */
  async function showMore(message, index) {
    if (busy) return
    const limit = Math.min(message.results.length + PAGE_SIZE, MAX_RESULTS)
    const answer = await request(message.query, limit)
    setMessages((current) => current.map((item, at) => (at === index ? answer : item)))
  }

  function handleKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      ask()
    }
  }

  return (
    <>
      {opened && (
        <aside className="ai-panel" aria-label="AI qidiruv">
          <header className="ai-panel-head">
            <span className="ai-panel-badge" aria-hidden="true">
              <i className="bi bi-robot" />
            </span>
            <div className="ai-panel-heading">
              <strong>AI qidiruv</strong>
              <span>Kontentni ma'nosi bo'yicha topadi</span>
            </div>
            <ActionIcon
              variant="subtle"
              color="gray"
              aria-label="AI qidiruvni yopish"
              onClick={() => setOpened(false)}
            >
              <i className="bi bi-x-lg" aria-hidden="true" />
            </ActionIcon>
          </header>

          <ScrollArea type="auto" viewportRef={viewportRef} className="ai-panel-body" offsetScrollbars>
            <div className="ai-chat">
              {messages.length === 0 && (
                <div className="ai-intro">
                  <p>
                    Nima ko'rmoqchi ekaningizni o'z so'zingiz bilan yozing — masalan
                    &ldquo;sarguzasht va qo'rqinchli animelar&rdquo;. Natijalar nomi emas,
                    mazmuni bo'yicha tanlanadi.
                  </p>
                  <div className="ai-chips">
                    {SUGGESTIONS.map((suggestion) => (
                      <button
                        key={suggestion}
                        type="button"
                        className="ai-chip"
                        onClick={() => ask(suggestion)}
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((message, index) => {
                if (message.role === 'user') {
                  return (
                    <div className="ai-message ai-message-user" key={`u-${index}`}>
                      <p>{message.text}</p>
                      <time>{timestamp()}</time>
                    </div>
                  )
                }
                return (
                  <div className="ai-message ai-message-ai" key={`a-${index}`}>
                    {message.kind === 'results' && (
                      <>
                        {message.answer && <p className="ai-answer">{message.answer}</p>}
                        {message.thinking && (
                          <details className="ai-thinking">
                            <summary>
                              <i className="bi bi-lightbulb" aria-hidden="true" /> Fikrlash jarayoni
                            </summary>
                            <p>{message.thinking}</p>
                          </details>
                        )}
                        <p className="ai-message-lead">
                          <strong>{message.query}</strong> uchun{' '}
                          {message.total > message.results.length
                            ? `${message.total} ta mos kontent — eng mos ${message.results.length} tasi:`
                            : `${message.total} ta mos kontent:`}
                        </p>
                        <ul className="ai-results">
                          {message.results.map((item) => (
                            <ResultCard item={item} key={item.id} />
                          ))}
                        </ul>
                        {message.total > message.results.length &&
                          message.results.length < MAX_RESULTS && (
                            <button
                              type="button"
                              className="ai-more"
                              disabled={busy}
                              onClick={() => showMore(message, index)}
                            >
                              <i className="bi bi-arrow-down-circle" aria-hidden="true" /> Yana{' '}
                              {Math.min(message.total - message.results.length, PAGE_SIZE)} tasini
                              ko&rsquo;rsatish
                            </button>
                          )}
                      </>
                    )}
                    {message.kind === 'answer' && (
                      <>
                        <p className="ai-answer">{message.answer}</p>
                        {message.thinking && (
                          <details className="ai-thinking">
                            <summary>
                              <i className="bi bi-lightbulb" aria-hidden="true" /> Fikrlash jarayoni
                            </summary>
                            <p>{message.thinking}</p>
                          </details>
                        )}
                      </>
                    )}
                    {message.kind === 'empty' && (
                      <>
                        <p>
                          <strong>{message.query}</strong> bo'yicha mos kontent topilmadi. So'rovni
                          boshqacha yozib ko'ring yoki katalogdan foydalaning.
                        </p>
                        {message.answer && <p className="ai-answer">{message.answer}</p>}
                        {message.thinking && (
                          <details className="ai-thinking">
                            <summary>
                              <i className="bi bi-lightbulb" aria-hidden="true" /> Fikrlash jarayoni
                            </summary>
                            <p>{message.thinking}</p>
                          </details>
                        )}
                      </>
                    )}
                    {message.kind === 'locked' && (
                      <>
                        <p>
                          {message.detail ||
                            "AI qidiruv faqat obunachilar uchun. Faol obuna kerak."}
                        </p>
                        <Link className="ai-upsell" to="/subscription">
                          <i className="bi bi-ticket-perforated" aria-hidden="true" /> Obunani tanlash
                        </Link>
                      </>
                    )}
                    {message.kind === 'unavailable' && (
                      <p>
                        {message.detail ||
                          "AI qidiruv hozircha ishga tushmagan. Keyinroq urinib ko'ring."}
                      </p>
                    )}
                    {message.kind === 'error' && (
                      <p>Xatolik yuz berdi. Iltimos, birozdan so'ng qayta urinib ko'ring.</p>
                    )}
                  </div>
                )
              })}

              {busy && (
                <div className="ai-message ai-message-ai ai-message-busy">
                  <Loader size="xs" />
                  <span>AI o'ylayapti: so'rovni tahlil qilib, mos kontentlarni tanlayapti…</span>
                </div>
              )}
            </div>
          </ScrollArea>

          <form
            className="ai-composer"
            onSubmit={(event) => {
              event.preventDefault()
              ask()
            }}
          >
            <Textarea
              ref={inputRef}
              className="ai-composer-input"
              placeholder="Masalan: menga sarguzasht va qo'rqinchli animelar ayt"
              aria-label="AI qidiruv savoli"
              autosize
              minRows={1}
              maxRows={4}
              maxLength={MAX_QUERY}
              value={text}
              disabled={busy}
              onChange={(event) => setText(event.currentTarget.value)}
              onKeyDown={handleKeydown}
            />
            <ActionIcon
              type="submit"
              size="lg"
              radius="xl"
              variant="filled"
              aria-label="Yuborish"
              disabled={busy || !text.trim()}
            >
              <i className="bi bi-send" aria-hidden="true" />
            </ActionIcon>
            <Text size="xs" c="dimmed" className="ai-composer-hint">
              Enter — yuborish · Shift+Enter — yangi qator
            </Text>
          </form>
        </aside>
      )}

      <button
        type="button"
        className={`ai-launcher${opened ? ' ai-launcher-open' : ''}`}
        aria-label={opened ? 'AI qidiruvni yopish' : 'AI qidiruvni ochish'}
        aria-expanded={opened}
        title="AI qidiruv"
        onClick={() => setOpened((current) => !current)}
      >
        <i className={`bi ${opened ? 'bi-x-lg' : 'bi-robot'}`} aria-hidden="true" />
        {!opened && <span className="ai-launcher-label">AI qidiruv</span>}
      </button>
    </>
  )
}

export default AiSearchChat
