// A deliberately small markdown reader for the assistant's answers.
//
// The model writes markdown ("**qalin**", "- ro'yxat", "[nom](havola)"), and
// until now the chat showed those markers as literal text. This turns the text
// into plain data — blocks, then inline runs — so the React renderer can build
// real elements. Nothing here produces an HTML string, which means model output
// can never inject markup into the page: text stays text.

const HEADING = /^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$/
const RULE = /^\s*(?:[-*_])(?:\s*[-*_]){2,}\s*$/
const BULLET = /^(\s*)[-*+•]\s+(.*)$/
const ORDERED = /^(\s*)\d{1,3}[.)]\s+(.*)$/
const QUOTE = /^\s*>\s?(.*)$/
const FENCE = /^\s*```/

// Only links the app can actually follow become anchors; anything else
// (javascript:, data:, ...) keeps its label as plain text.
const SAFE_HREF = /^(?:https?:\/\/|tg:\/\/|\/)/i

function isSafeHref(href) {
  return SAFE_HREF.test(String(href || '').trim())
}

/** Split one line into text / emphasis / code / link runs. */
export function parseInline(source) {
  const text = String(source ?? '')
  const nodes = []
  let buffer = ''
  let index = 0

  const flush = () => {
    if (buffer) {
      nodes.push({ type: 'text', value: buffer })
      buffer = ''
    }
  }

  const push = (node, length) => {
    flush()
    nodes.push(node)
    index += length
  }

  while (index < text.length) {
    const rest = text.slice(index)

    if (rest[0] === '[') {
      // Balanced parentheses inside the URL (``.../a_(b)``) belong to it.
      const link = /^\[([^\]\n]*)\]\(((?:[^()\n]|\([^()\n]*\))*)\)/.exec(rest)
      if (link) {
        const href = link[2].trim()
        if (isSafeHref(href)) {
          push({ type: 'link', href, children: parseInline(link[1]) }, link[0].length)
        } else {
          push({ type: 'text', value: link[1] }, link[0].length)
        }
        continue
      }
    }

    if (rest[0] === '`') {
      const end = rest.indexOf('`', 1)
      if (end > 1 && !rest.slice(1, end).includes('\n')) {
        push({ type: 'code', value: rest.slice(1, end) }, end + 1)
        continue
      }
    }

    if (rest.startsWith('**') || rest.startsWith('__')) {
      const mark = rest.slice(0, 2)
      const end = rest.indexOf(mark, 2)
      if (end > 2 && !rest.slice(2, end).includes('\n')) {
        push({ type: 'strong', children: parseInline(rest.slice(2, end)) }, end + 2)
        continue
      }
    }

    if (rest.startsWith('~~')) {
      const end = rest.indexOf('~~', 2)
      if (end > 2 && !rest.slice(2, end).includes('\n')) {
        push({ type: 'del', children: parseInline(rest.slice(2, end)) }, end + 2)
        continue
      }
    }

    if (rest[0] === '*' || rest[0] === '_') {
      const mark = rest[0]
      const before = index === 0 ? ' ' : text[index - 1]
      const end = rest.indexOf(mark, 1)
      if (end > 1 && !/[0-9A-Za-z]/.test(before)) {
        const after = text[index + end + 1] || ' '
        if (!rest.slice(1, end).includes('\n') && !/[0-9A-Za-z]/.test(after)) {
          push({ type: 'em', children: parseInline(rest.slice(1, end)) }, end + 1)
          continue
        }
      }
    }

    buffer += text[index]
    index += 1
  }

  flush()
  return nodes
}

/** Read the answer into blocks the renderer can lay out. */
export function parseMarkdown(source) {
  const lines = String(source ?? '').replace(/\r\n?/g, '\n').split('\n')
  const blocks = []
  let paragraph = []
  let list = null
  let quote = null
  let code = null

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ type: 'paragraph', lines: paragraph })
      paragraph = []
    }
  }
  const flushList = () => {
    if (list) {
      blocks.push(list)
      list = null
    }
  }
  const flushQuote = () => {
    if (quote) {
      blocks.push({ type: 'quote', lines: quote })
      quote = null
    }
  }
  const flushAll = () => {
    flushParagraph()
    flushList()
    flushQuote()
  }

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, '')

    if (FENCE.test(line)) {
      if (code) {
        blocks.push({ type: 'code', text: code.join('\n') })
        code = null
      } else {
        flushAll()
        code = []
      }
      continue
    }
    if (code) {
      code.push(line)
      continue
    }

    if (!line.trim()) {
      flushAll()
      continue
    }

    const heading = HEADING.exec(line)
    if (heading) {
      flushAll()
      blocks.push({ type: 'heading', content: parseInline(heading[1]) })
      continue
    }

    if (RULE.test(line)) {
      flushAll()
      blocks.push({ type: 'rule' })
      continue
    }

    const quoted = QUOTE.exec(line)
    if (quoted) {
      flushParagraph()
      flushList()
      quote = quote || []
      if (quoted[1].trim()) quote.push(parseInline(quoted[1].trim()))
      continue
    }

    const bullet = BULLET.exec(line)
    if (bullet) {
      flushParagraph()
      flushQuote()
      if (list && list.ordered) flushList()
      list = list || { type: 'list', ordered: false, items: [] }
      list.items.push(parseInline(bullet[2]))
      continue
    }

    const ordered = ORDERED.exec(line)
    if (ordered) {
      flushParagraph()
      flushQuote()
      if (list && !list.ordered) flushList()
      list = list || { type: 'list', ordered: true, items: [] }
      list.items.push(parseInline(ordered[2]))
      continue
    }

    flushList()
    flushQuote()
    paragraph.push(parseInline(line))
  }

  if (code) blocks.push({ type: 'code', text: code.join('\n') })
  flushAll()
  return blocks
}
