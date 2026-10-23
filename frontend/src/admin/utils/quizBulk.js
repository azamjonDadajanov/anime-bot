// Ommaviy test kiritish matnini parse qilish.
//
// Format (testlar orasida bo'sh qator):
//   savol matni
//   to'g'ri javob[togri]
//   noto'g'ri javob
//   noto'g'ri javob
//
//   keyingi savol matni
//   ...

const CORRECT_MARK = /\[togri\]/i

export const BULK_FORMAT_EXAMPLE = `Qahramonning ismi nima?
Naruto[togri]
Sasuke
Sakura
Kakashi

Kim 7-suzuvchi hokim? (masalan)
Asuma[togri]
Kakashi
Guy`

/**
 * Matnni testlar ro'yxatiga ajratadi.
 *
 * @returns {{tests: Array<{text: string, choices: string[], correct_index: number, line: number}>,
 *            errors: Array<{line: number, message: string}>,
 *            blockCount: number}}
 */
export function parseBulkQuizText(raw) {
  const tests = []
  const errors = []
  const lines = String(raw ?? '')
    .replace(/\r\n?/g, '\n')
    .split('\n')

  let current = []
  let blockCount = 0

  const flush = () => {
    if (!current.length) return
    blockCount += 1
    const [questionLine, ...answerLines] = current
    current = []
    const label = `${blockCount}-test`

    const choices = []
    const correct = []
    let firstAnswerLine = questionLine.line

    for (const line of answerLines) {
      const marked = CORRECT_MARK.test(line.text)
      const value = line.text.replace(/\[togri\]/gi, '').replace(/\s+/g, ' ').trim()
      if (!value) continue
      if (correct.length === 0 && marked) firstAnswerLine = line.line
      if (marked) correct.push(choices.length)
      choices.push(value)
    }

    const question = questionLine.text.replace(/\s+/g, ' ').trim()

    if (!question) {
      errors.push({ line: questionLine.line, message: `${label}: savol matni bo'sh.` })
    } else if (question.length > 500) {
      errors.push({
        line: questionLine.line,
        message: `${label}: savol matni 500 belgidan uzun (hozir ${question.length}).`,
      })
    } else if (choices.length < 2) {
      errors.push({ line: questionLine.line, message: `${label}: kamida 2 ta javob kerak.` })
    } else if (choices.length > 6) {
      errors.push({ line: firstAnswerLine, message: `${label}: ko'pi bilan 6 ta variant (kiritilgan ${choices.length}). Testlar orasida bo'sh qator qoldiring.` })
    } else if (correct.length === 0) {
      errors.push({
        line: firstAnswerLine,
        message: `${label}: to'g'ri javob belgilanmagan — javob oxiriga [togri] qo'shing.`,
      })
    } else if (correct.length > 1) {
      errors.push({
        line: firstAnswerLine,
        message: `${label}: ${correct.length} ta javob belgilangan — faqat bittasi [togri] bo'lishi kerak.`,
      })
    } else {
      tests.push({ text: question, choices, correct_index: correct[0], line: questionLine.line })
    }
  }

  lines.forEach((rawLine, index) => {
    const text = rawLine.trim()
    if (!text) {
      flush()
      return
    }
    current.push({ line: index + 1, text })
  })
  flush()

  return { tests, errors, blockCount }
}
