import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ActionIcon, Loader, ScrollArea, Text, Textarea } from '@mantine/core'
import { aiApi, supportApi } from '../apis/api'
import { useAuth } from '../apis/useAuth'
import { TELEGRAM_BOT_URL } from '../pages/profile/profileUtils'
import Markdown from './Markdown'

const MAX_QUERY = 300
// The support endpoint stores up to 2000 characters (users.support.MAX_LENGTH).
const MAX_ADMIN_MESSAGE = 2000
// How many earlier turns ride along with the next question: the model answers
// "nima aytgandingiz?" from the thread instead of guessing.
const HISTORY_LIMIT = 10
// How many titles one answer may show. The assistant itself decides what is
// relevant (its tools search the catalogue); this only keeps the bubble short.
const RESULT_LIMIT = 8

// Anything that shows off what the assistant can do — some are catalogue
// lookups, some are plain questions it answers on its own.
const SUGGESTIONS = [
  "sarguzasht va qo'rqinchli animelar tavsiya qil",
  "Qaysi anime eng yuqori reytingga ega?",
  "Naruto nechta qismdan iborat?",
  "katalogda qanday janrlar bor?",
]

// "Sevimlilar" mode: examples that only make sense with the account's
// favourites and last watched titles attached.
const TASTE_SUGGESTIONS = [
  'sevimlilarimga o‘xshash nima bor?',
  'oxirgi ko‘rganlarimga mos tavsiya ber',
  'men qanday janrlarni ko‘proq yoqtiraman?',
]

// Tezkor amallar: the panel is a chat, but the three things people look for
// most often are one click away — write to an admin, ask against the
// favourites ("Sevimlilar" mode), or compare the subscription plans.
const ACTIONS = [
  { key: 'admin', label: 'Adminga xabar', icon: 'bi bi-envelope-paper' },
  { key: 'favorites', label: 'Sevimlilar', icon: 'bi bi-heart' },
  { key: 'plans', label: 'Obunalarni taqqosla', icon: 'bi bi-ticket-perforated', to: '/subscription' },
]

function timestamp() {
  return new Date().toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' })
}

function parseAnswer(data) {
  const results = Array.isArray(data?.results) ? data.results : []
  // The assistant's own words. The titles under them are the rows its
  // catalogue functions actually returned, never invented by the model.
  const answer = String(data?.answer || '')
  const tools = Array.isArray(data?.tools) ? data.tools : []
  // An account action (izoh, yulduzcha, profil, obuna, ulash…): the server
  // built the confirmation card for the client — the model never saw it. The
  // card rides along with the assistant's sentence.
  if (data?.action?.token) {
    return {
      role: 'ai',
      kind: 'action',
      query: data?.query || '',
      answer,
      tools,
      action: data.action,
    }
  }
  if (!results.length) {
    // The assistant answered a conversational question ("who are you", "what
    // can you do") rather than looking content up: show only its words.
    if (data?.conversational && answer) {
      return { role: 'ai', kind: 'answer', query: data?.query || '', answer, tools }
    }
    return { role: 'ai', kind: 'empty', query: data?.query || '', answer, tools }
  }
  return {
    role: 'ai',
    kind: 'results',
    query: data?.query || '',
    results,
    answer,
    tools,
  }
}

function ResultCard({ item }) {
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
      </div>
      {/* One sentence, exactly as the API computed it from the synopsis. */}
      <p className="ai-result-summary">{item.summary}</p>
    </li>
  )
}

/**
 * The confirmation card for an account action. The fields arrive from the
 * server already filled («tayyor», never invented); the user edits what is
 * editable and only then does «Tasdiqlash» sign the request. «Bekor qilish»
 * just closes the card — nothing was ever sent.
 *
 * `kind: 'link'` has no confirm step at all: it opens the Telegram bot deep
 * link and polls the account until the bot reports the profile connected, at
 * which point the button flips to its disabled «Ulandi» state.
 */
function ActionCard({ action, user }) {
  const [fields, setFields] = useState(() =>
    (action.fields || []).map((field) => ({ ...field, file: null })),
  )
  const [link, setLink] = useState(() => action.link || null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState('')
  const [cancelled, setCancelled] = useState(false)
  const [error, setError] = useState('')

  const isLink = action.kind === 'link'
  const linked = isLink ? Boolean(link?.linked) : false
  const closed = Boolean(done || cancelled)

  function applyLink(data) {
    setLink(data)
    if (data?.linked) {
      // Keep the card's status row in step with the polled truth.
      setFields((current) =>
        current.map((field) =>
          field.key === 'status'
            ? { ...field, value: `Ulangan (@${data.username || ''})` }
            : field,
        ),
      )
    }
  }

  // The user taps «Telegramga ulash», confirms inside the bot — this card
  // notices on its own, no page reload.
  useEffect(() => {
    if (!isLink || linked || cancelled) return undefined
    let alive = true
    async function check() {
      try {
        const data = await aiApi.telegramLink()
        if (alive && data?.linked) applyLink(data)
      } catch {
        // A failed poll just waits for the next tick.
      }
    }
    const timer = setInterval(check, 3000)
    return () => {
      alive = false
      clearInterval(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLink, linked, cancelled])

  function patch(key, value) {
    setFields((current) => current.map((field) => (field.key === key ? { ...field, value } : field)))
  }

  function patchFile(key, file) {
    setFields((current) => current.map((field) => (field.key === key ? { ...field, file } : field)))
  }

  function stepScore(field, delta) {
    const has = field.value !== null && field.value !== undefined && field.value !== ''
    const min = Number(field.min ?? 1)
    const max = Number(field.max ?? 10)
    const base = has ? Number(field.value) : delta > 0 ? min - delta : max - delta
    patch(field.key, Math.min(max, Math.max(min, base + delta)))
  }

  async function checkLinkNow() {
    if (busy) return
    setBusy(true)
    try {
      const data = await aiApi.telegramLink()
      applyLink(data)
      if (!data?.linked) setError('Hali ulanmagan — botda tasdiqlang.')
    } catch {
      setError('Ulash holatini tekshirib bo‘lmadi. Qayta urinib ko‘ring.')
    } finally {
      setBusy(false)
    }
  }

  async function confirm() {
    if (busy || closed) return
    const values = {}
    let screenshot = null
    let avatarFile = null
    for (const field of fields) {
      if (!field.editable) continue
      if (field.type === 'file') {
        if (field.file) {
          if (field.key === 'screenshot') screenshot = field.file
          if (field.key === 'avatar_file') avatarFile = field.file
        }
        continue
      }
      const empty =
        field.value === null || field.value === undefined || String(field.value).trim() === ''
      if (field.required && empty) {
        setError(`${field.label}ni kiriting.`)
        return
      }
      if (field.type === 'int' && empty) continue
      values[field.key] = field.value
    }
    if (action.action === 'subscription_request' && !screenshot) {
      setError('To‘lov skrinshotini yuklang.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const data = await aiApi.confirmAction({ token: action.token, values, screenshot, avatarFile })
      setDone(data?.message || 'Amal bajarildi.')
    } catch (err) {
      setError(err.response?.data?.detail || 'Xatolik yuz berdi. Qayta urinib ko‘ring.')
    } finally {
      setBusy(false)
    }
  }

  function renderField(field) {
    const control = () => {
      switch (field.type) {
        case 'int': {
          const has = field.value !== null && field.value !== undefined && field.value !== ''
          return (
            <span className="ai-action-stepper">
              <button
                type="button"
                className="ai-action-step"
                aria-label={`Kamaytirish: ${field.label}`}
                disabled={closed}
                onClick={() => stepScore(field, -1)}
              >
                <i className="bi bi-dash-lg" aria-hidden="true" />
              </button>
              <span className="ai-action-step-value">{has ? field.value : '—'}</span>
              <button
                type="button"
                className="ai-action-step"
                aria-label={`Ko‘paytirish: ${field.label}`}
                disabled={closed}
                onClick={() => stepScore(field, 1)}
              >
                <i className="bi bi-plus-lg" aria-hidden="true" />
              </button>
            </span>
          )
        }
        case 'select':
          return (
            <select
              className="ai-action-input"
              value={String(field.value ?? '')}
              disabled={closed}
              onChange={(event) => patch(field.key, event.currentTarget.value)}
            >
              {!field.required && <option value="">—</option>}
              {(field.options || []).map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          )
        case 'bool':
          return (
            <button
              type="button"
              className={`ai-action-toggle${field.value ? ' is-on' : ''}`}
              aria-pressed={Boolean(field.value)}
              disabled={closed}
              onClick={() => patch(field.key, !field.value)}
            >
              <i className="bi" aria-hidden="true" />
              {field.value ? 'Yoqilgan' : 'O‘chirilgan'}
            </button>
          )
        case 'file':
          return (
            <span className="ai-action-file">
              <label className="ai-action-btn">
                <i className="bi bi-paperclip" aria-hidden="true" />
                {field.file ? field.file.name : 'Fayl tanlash'}
                <input
                  type="file"
                  accept={field.accept || 'image/*'}
                  disabled={closed}
                  onChange={(event) => patchFile(field.key, event.target.files?.[0] || null)}
                />
              </label>
              {field.value === true && !field.file && (
                <span className="ai-action-file-hint">Mavjud rasm saqlanadi</span>
              )}
            </span>
          )
        case 'text':
          return (
            <input
              className="ai-action-input"
              type="text"
              maxLength={field.max_length || undefined}
              value={String(field.value ?? '')}
              disabled={closed}
              onChange={(event) => patch(field.key, event.currentTarget.value)}
            />
          )
        case 'textarea':
          return (
            <textarea
              className="ai-action-input"
              rows={3}
              maxLength={field.max_length || undefined}
              value={String(field.value ?? '')}
              disabled={closed}
              onChange={(event) => patch(field.key, event.currentTarget.value)}
            />
          )
        default:
          return null
      }
    }

    if (field.type === 'static') {
      return (
        <div className="ai-action-row" key={field.key}>
          <span className="ai-action-label">{field.label}</span>
          <span className="ai-action-value">
            {field.href ? (
              <Link className="ai-action-link" to={field.href}>
                {field.value}
              </Link>
            ) : (
              field.value
            )}
          </span>
        </div>
      )
    }
    return (
      <label className="ai-action-row" key={field.key}>
        <span className="ai-action-label">
          {field.label}
          {field.required && <em aria-hidden="true"> *</em>}
        </span>
        {control()}
        {field.help && <span className="ai-action-help">{field.help}</span>}
      </label>
    )
  }

  const linkHref =
    link?.url ||
    (user?.username ? `${TELEGRAM_BOT_URL}?start=${encodeURIComponent(user.username)}` : TELEGRAM_BOT_URL)

  return (
    <div className={`ai-action${closed ? ' is-closed' : ''}`}>
      <div className="ai-action-head">
        <i className="bi bi-clipboard2-check" aria-hidden="true" />
        <strong>{action.label}</strong>
        {action.source === 'bot' && <span className="ai-action-tag">Telegram</span>}
      </div>
      <div className="ai-action-body">{fields.map(renderField)}</div>
      {error && (
        <p className="ai-action-status is-error" role="alert">
          <i className="bi bi-exclamation-triangle" aria-hidden="true" /> {error}
        </p>
      )}
      {done && (
        <p className="ai-action-status is-done" role="status">
          <i className="bi bi-check-circle-fill" aria-hidden="true" /> {done}
        </p>
      )}
      {cancelled && (
        <p className="ai-action-status" role="status">
          <i className="bi bi-x-circle" aria-hidden="true" /> Amal bekor qilindi.
        </p>
      )}
      {isLink ? (
        <div className="ai-action-foot">
          {linked ? (
            <button type="button" className="ai-action-btn is-primary" disabled>
              <i className="bi bi-check2-circle" aria-hidden="true" /> Ulandi
            </button>
          ) : (
            <>
              <a className="ai-action-btn is-primary" href={linkHref} target="_blank" rel="noreferrer">
                <i className="bi bi-send" aria-hidden="true" /> Telegramga ulash
              </a>
              <button type="button" className="ai-action-btn" disabled={busy} onClick={checkLinkNow}>
                <i className="bi bi-arrow-clockwise" aria-hidden="true" /> Tekshirish
              </button>
            </>
          )}
        </div>
      ) : !closed ? (
        <div className="ai-action-foot">
          <button
            type="button"
            className="ai-action-btn"
            disabled={busy}
            onClick={() => setCancelled(true)}
          >
            Bekor qilish
          </button>
          <button
            type="button"
            className="ai-action-btn is-primary"
            disabled={busy}
            onClick={confirm}
          >
            {busy ? 'Yuborilmoqda…' : 'Tasdiqlash'}
          </button>
        </div>
      ) : null}
    </div>
  )
}

/** The last turns of the chat, in the shape the ai-assistant API expects. */
function historyFrom(list) {
  return list
    .slice(-HISTORY_LIMIT)
    .map((message) => {
      if (message.role === 'user') return { role: 'user', text: message.text.slice(0, MAX_QUERY) }
      const text = message.answer || ''
      return text ? { role: 'ai', text: text.slice(0, MAX_QUERY) } : null
    })
    .filter(Boolean)
}

function AiAssistantChat() {
  const { user } = useAuth()
  const [opened, setOpened] = useState(false)
  // 'search' — AI yordamchi, 'admin' — the same composer writes to the
  // administrators, 'taste' — "Sevimlilar": any query, answered against the
  // account's favourites and last watched titles.
  const [mode, setMode] = useState('search')
  const [text, setText] = useState('')
  const [messages, setMessages] = useState([])
  const [busy, setBusy] = useState(false)
  const inputRef = useRef(null)
  const viewportRef = useRef(null)

  useEffect(() => {
    if (!opened) return undefined
    const timer = setTimeout(() => inputRef.current?.focus(), 60)
    return () => clearTimeout(timer)
  }, [opened, mode])

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

  async function request(query, { history = [], taste = false } = {}) {
    setBusy(true)
    try {
      const data = await aiApi.ask(query, { limit: RESULT_LIMIT, history, taste })
      return parseAnswer(data)
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

  /**
   * "Sevimlilar" mode: nothing is sent when the chip is pressed — the
   * composer stays open and the user writes any query themselves. On send
   * the server attaches the favourites and last watched titles, so the
   * answer is grounded in the account's actual taste.
   */
  async function ask(value) {
    const query = (value ?? text).trim()
    if (!query || busy) return
    push({ role: 'user', text: query })
    setText('')
    const taste = mode === 'taste'
    const answer = await request(query, { taste })
    // `taste` rides along so "show more" re-asks the same way.
    push({ ...answer, taste })
  }

  /** Deliver one message to the administrators and report the outcome. */
  async function deliverToAdmin(body) {
    try {
      const data = await supportApi.send(body)
      return {
        role: 'ai',
        kind: 'admin-sent',
        delivered: Boolean(data?.delivered),
        detail: data?.detail || '',
      }
    } catch (error) {
      return { role: 'ai', kind: 'admin-error', detail: error.response?.data?.detail || '' }
    }
  }

  /**
   * "Adminga xabar": the model analyses the message first (with the last
   * HISTORY_LIMIT turns for context) and answers; when that answer does not
   * help, the "Adminga yuborish" button under it sends the original text to
   * the administrators. A model that cannot answer at all (no key, no
   * subscription, outage) means the message goes to the admins straight away.
   */
  async function sendToAdmin(value) {
    const body = (value ?? text).trim()
    if (!body || busy) return
    const history = historyFrom(messages)
    push({ role: 'user', text: body })
    setText('')
    setBusy(true)
    let data
    try {
      // `support` switches the model to the technical-support persona: a
      // problem comes back as fix-it steps and advice, not small talk.
      data = await aiApi.ask(body.slice(0, MAX_QUERY), {
        limit: RESULT_LIMIT,
        history,
        support: true,
      })
    } catch {
      // No key, no subscription or an outage: the point of the mode was to
      // reach an administrator, so the text goes there instead.
      const sent = await deliverToAdmin(body)
      setBusy(false)
      push(sent)
      return
    }
    setBusy(false)
    push({
      role: 'ai',
      kind: 'admin-assist',
      text: body,
      answer: String(data?.answer || ''),
      results: Array.isArray(data?.results) ? data.results : [],
      total: Number(data?.total ?? 0),
    })
  }

  /** The "Adminga yuborish" button under an AI answer in admin mode. */
  async function forwardToAdmin(message, index) {
    if (busy || message.forwarded) return
    setBusy(true)
    const sent = await deliverToAdmin(message.text)
    setBusy(false)
    setMessages((current) =>
      current.map((item, at) => (at === index ? { ...item, forwarded: true, sent } : item)),
    )
  }

  /** The composer sends to the model or to the admins, depending on the mode. */
  function submit(value) {
    if (mode === 'admin') return sendToAdmin(value)
    return ask(value)
  }

  function openAction(action) {
    if (action.key === 'admin') {
      // Toggle the mode; the composer takes the user's own words from here.
      setMode((current) => (current === 'admin' ? 'search' : 'admin'))
      return
    }
    if (action.key === 'favorites') {
      // "Sevimlilar" is a mode, not a one-shot: nothing is sent until the
      // user writes a query themselves.
      setMode((current) => (current === 'taste' ? 'search' : 'taste'))
      return
    }
    // Anything with a `to` (the plans chip) just navigates and closes.
    setOpened(false)
  }

  function handleKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <>
      {opened && (
        <aside className="ai-panel" aria-label="AI yordamchi">
          <header className="ai-panel-head">
            <span className="ai-panel-badge" aria-hidden="true">
              <i
                className={`bi ${
                  mode === 'admin' ? 'bi-envelope-paper' : mode === 'taste' ? 'bi-heart' : 'bi-robot'
                }`}
              />
            </span>
            <div className="ai-panel-heading">
              <strong>
                {mode === 'admin' ? 'Adminga xabar' : mode === 'taste' ? 'Sevimlilar' : 'AI yordamchi'}
              </strong>
              <span>
                {mode === 'admin'
                  ? 'Texnik yordam: ko‘rsatma va maslahat beradi'
                  : mode === 'taste'
                    ? 'Sevimlilar va ko‘rganlaringiz asosida javob beradi'
                    : 'Savollarga javob beradi va kontent topadi'}
              </span>
            </div>
            <ActionIcon
              variant="subtle"
              color="gray"
              aria-label="AI yordamchini yopish"
              onClick={() => setOpened(false)}
            >
              <i className="bi bi-x-lg" aria-hidden="true" />
            </ActionIcon>
          </header>

          <ScrollArea type="auto" viewportRef={viewportRef} className="ai-panel-body" offsetScrollbars>
            <div className="ai-chat">
              <div className="ai-actions" role="group" aria-label="Tezkor amallar">
                {ACTIONS.map((action) => {
                  const content = (
                    <>
                      <i className={action.icon} aria-hidden="true" />
                      <span>{action.label}</span>
                    </>
                  )
                  if (action.to) {
                    return (
                      <Link
                        className="ai-chip ai-chip-link"
                        to={action.to}
                        key={action.key}
                        onClick={() => setOpened(false)}
                      >
                        {content}
                      </Link>
                    )
                  }
                  return (
                    <button
                      type="button"
                      className={`ai-chip ai-chip-action${
                        (action.key === 'admin' && mode === 'admin') ||
                        (action.key === 'favorites' && mode === 'taste')
                          ? ' ai-chip-active'
                          : ''
                      }`}
                      aria-pressed={
                        action.key === 'admin'
                          ? mode === 'admin'
                          : action.key === 'favorites'
                            ? mode === 'taste'
                            : undefined
                      }
                      key={action.key}
                      onClick={() => openAction(action)}
                    >
                      {content}
                    </button>
                  )
                })}
              </div>

              {messages.length === 0 && (
                <div className="ai-intro">
                  <p>
                    {mode === 'admin'
                      ? 'Muammo, savol yoki taklifni yozing — AI texnik yordam sifatida tahlil qilib, tuzatish ko‘rsatmalari va maslahatlar beradi. Javob qoniqmasa, «Adminga yuborish» tugmasi bilan xabar administratorlarga yetadi.'
                      : mode === 'taste'
                        ? 'Sevimlilar va oxirgi ko‘rganlaringiz asosida istalgan savol yozing — AI shaxsiy ma’lumotlaringizni hisobga oladi. Masalan: «sevimlilarimga o‘xshash nima bor?»'
                        : 'Savol bering yoki qidirayotganingizni yozing — AniVoy katalogdan o’zi qidirib, kerakli ma’lumotni oladi. Masalan: «qo’rqinchli animelar tavsiya qil» yoki «shu anime nechta qismdan iborat?»'}
                  </p>
                  {mode === 'admin' ? (
                    <div className="ai-chips">
                      <button
                        type="button"
                        className="ai-chip"
                        onClick={() => setText("Obuna to'lovim tasdiqlanmadi...")}
                      >
                        To‘lov tasdiqlanmadi
                      </button>
                      <button
                        type="button"
                        className="ai-chip"
                        onClick={() => setText('Video ochilmayapti: ')}
                      >
                        Video ochilmayapti
                      </button>
                      <button
                        type="button"
                        className="ai-chip"
                        onClick={() => setText('Parolni unutdim, akkaimga kira olmayapman')}
                      >
                        Parolni unutdim
                      </button>
                      <button
                        type="button"
                        className="ai-chip"
                        onClick={() => setText('Ilovada quyidagi muammo bor: ')}
                      >
                        Ilovada muammo bor
                      </button>
                    </div>
                  ) : mode === 'taste' ? (
                    <div className="ai-chips">
                      {TASTE_SUGGESTIONS.map((suggestion) => (
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
                  ) : (
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
                  )}
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
                        {message.answer && (
                          <Markdown className="ai-answer" text={message.answer} />
                        )}
                        <p className="ai-message-lead">
                          <strong>{message.query}</strong> uchun katalogdan topilganlar:
                        </p>
                        <ul className="ai-results">
                          {message.results.map((item) => (
                            <ResultCard item={item} key={item.id} />
                          ))}
                        </ul>
                      </>
                    )}
                    {message.kind === 'answer' && (
                      <Markdown className="ai-answer" text={message.answer} />
                    )}
                    {message.kind === 'action' && (
                      <>
                        {message.answer && (
                          <Markdown className="ai-answer" text={message.answer} />
                        )}
                        <ActionCard action={message.action} user={user} />
                      </>
                    )}
                    {message.kind === 'empty' && (
                      <>
                        <p>
                          <strong>{message.query}</strong> bo'yicha mos kontent topilmadi. So'rovni
                          boshqacha yozib ko'ring yoki katalogdan foydalaning.
                        </p>
                        {message.answer && (
                          <Markdown className="ai-answer" text={message.answer} />
                        )}
                      </>
                    )}
                    {message.kind === 'locked' && (
                      <>
                        <p>
                          {message.detail ||
                            "AI yordamchi faqat obunachilar uchun. Faol obuna kerak."}
                        </p>
                        <Link className="ai-upsell" to="/subscription">
                          <i className="bi bi-ticket-perforated" aria-hidden="true" /> Obunani tanlash
                        </Link>
                      </>
                    )}
                    {message.kind === 'unavailable' && (
                      <p>
                        {message.detail ||
                          "AI yordamchi hozircha ishga tushmagan. Keyinroq urinib ko'ring."}
                      </p>
                    )}
                    {message.kind === 'error' && (
                      <p>Xatolik yuz berdi. Iltimos, birozdan so'ng qayta urinib ko'ring.</p>
                    )}
                    {message.kind === 'admin-assist' && (
                      <>
                        {message.answer ? (
                          <Markdown className="ai-answer" text={message.answer} />
                        ) : (
                          <p>
                            AI bu savolga javob topa olmadi — xabaringizni administratorga
                            yuborishingiz mumkin.
                          </p>
                        )}
                        {message.results.length > 0 && (
                          <>
                            <p className="ai-message-lead">Katalogdan mos kontentlar:</p>
                            <ul className="ai-results">
                              {message.results.map((item) => (
                                <ResultCard item={item} key={item.id} />
                              ))}
                            </ul>
                          </>
                        )}
                        {message.forwarded ? (
                          <p className="ai-forwarded">
                            <i
                              className={`bi ${
                                message.sent?.delivered ? 'bi-check-circle-fill' : 'bi-clock-history'
                              }`}
                              aria-hidden="true"
                            />
                            {message.sent?.detail ||
                              (message.sent?.delivered
                                ? 'Xabaringiz administratorlarga yuborildi.'
                                : 'Xabar saqlandi, lekin hozircha yuborilmadi.')}
                          </p>
                        ) : (
                          <button
                            type="button"
                            className="ai-send-admin"
                            disabled={busy}
                            onClick={() => forwardToAdmin(message, index)}
                          >
                            <i className="bi bi-envelope-paper" aria-hidden="true" /> Adminga yuborish
                          </button>
                        )}
                      </>
                    )}
                    {message.kind === 'admin-sent' && (
                      <>
                        <p>
                          <i
                            className={`bi ${
                              message.delivered ? 'bi-check-circle-fill' : 'bi-clock-history'
                            }`}
                            aria-hidden="true"
                            style={{ marginRight: 6 }}
                          />
                          {message.detail ||
                            (message.delivered
                              ? 'Xabaringiz administratorlarga yuborildi.'
                              : 'Xabar saqlandi, lekin hozircha yuborilmadi. Administratorlar uni ko’radi.')}
                        </p>
                        <button
                          type="button"
                          className="ai-more"
                          onClick={() => setMode('search')}
                        >
                          <i className="bi bi-robot" aria-hidden="true" /> AI yordamchiga qaytish
                        </button>
                      </>
                    )}
                    {message.kind === 'admin-error' && (
                      <>
                        <p>{message.detail || 'Xabar yuborilmadi. Iltimos, qayta urinib ko’ring.'}</p>
                        <button
                          type="button"
                          className="ai-more"
                          onClick={() => setMode('search')}
                        >
                          <i className="bi bi-robot" aria-hidden="true" /> AI yordamchiga qaytish
                        </button>
                      </>
                    )}
                  </div>
                )
              })}

              {busy && (
                <div className="ai-message ai-message-ai ai-message-busy">
                  <Loader size="xs" />
                  <span>
                    {mode === 'admin'
                      ? 'AI muammoni tahlil qilib, tuzatish ko‘rsatmalarini tayyorlayapti…'
                      : mode === 'taste'
                        ? 'AI didingizni hisobga olib, mos kontentlarni tanlayapti…'
                        : "AI o'ylayapti: so'rovni tahlil qilib, mos kontentlarni tanlayapti…"}
                  </span>
                </div>
              )}
            </div>
          </ScrollArea>

          <form
            className="ai-composer"
            onSubmit={(event) => {
              event.preventDefault()
              submit()
            }}
          >
            <Textarea
              ref={inputRef}
              className="ai-composer-input"
              placeholder={
                mode === 'admin'
                  ? 'Muammoni yozing: AI tuzatish ko‘rsatmalarini beradi...'
                  : mode === 'taste'
                    ? 'Masalan: sevimlilarimga o‘xshash nima bor?'
                    : "Masalan: menga sarguzasht va qo'rqinchli animelar ayt"
              }
              aria-label={
                mode === 'admin'
                  ? 'Adminga xabar matni'
                  : mode === 'taste'
                    ? 'Sevimlilar bo‘yicha savol'
                    : 'AI yordamchi savoli'
              }
              autosize
              minRows={1}
              maxRows={4}
              maxLength={mode === 'admin' ? MAX_ADMIN_MESSAGE : MAX_QUERY}
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
              <i className={`bi ${mode === 'admin' ? 'bi-send-check' : 'bi-send'}`} aria-hidden="true" />
            </ActionIcon>
            <Text size="xs" c="dimmed" className="ai-composer-hint">
              {mode === 'admin'
                ? `Ko‘rsatma va maslahat · ${text.length}/${MAX_ADMIN_MESSAGE} · Enter — yuborish`
                : mode === 'taste'
                  ? `Sevimlilar asosida · Enter — yuborish`
                  : 'Enter — yuborish · Shift+Enter — yangi qator'}
            </Text>
          </form>
        </aside>
      )}

      <button
        type="button"
        className={`ai-launcher${opened ? ' ai-launcher-open' : ''}`}
        aria-label={opened ? 'AI yordamchini yopish' : 'AI yordamchini ochish'}
        aria-expanded={opened}
        title="AI yordamchi"
        onClick={() => setOpened((current) => !current)}
      >
        <i className={`bi ${opened ? 'bi-x-lg' : 'bi-robot'}`} aria-hidden="true" />
        {!opened && <span className="ai-launcher-label">AI yordamchi</span>}
      </button>
    </>
  )
}

export default AiAssistantChat
