export function inputHandler(setForm, key) {
  return (event) => {
    const value = event?.currentTarget?.value ?? event?.target?.value ?? ''
    setForm((prev) => ({ ...prev, [key]: value }))
  }
}

export function numberHandler(setForm, key) {
  return (value) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }
}

export function checkboxHandler(setForm, key) {
  return (event) => {
    const checked = event?.currentTarget?.checked ?? event?.target?.checked ?? false
    setForm((prev) => ({ ...prev, [key]: checked }))
  }
}

export function selectHandler(setForm, key) {
  return (value) => {
    setForm((prev) => ({ ...prev, [key]: value ?? '' }))
  }
}

export function formatError(err, fallback = 'Xatolik yuz berdi.') {
  const data = err?.response?.data
  if (!data) return err?.message || fallback
  if (typeof data === 'string') return data
  if (data.detail) return String(data.detail)
  if (Array.isArray(data)) return data.join(', ')
  if (typeof data === 'object') {
    const parts = Object.entries(data).map(([key, value]) => {
      const text = Array.isArray(value) ? value.join(', ') : String(value)
      return `${key}: ${text}`
    })
    if (parts.length) return parts.join(' · ')
  }
  return fallback
}

export async function copyText(text) {
  if (!text) return false
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* fall through to textarea */
  }
  try {
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.left = '-9999px'
    document.body.appendChild(area)
    area.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(area)
    return ok
  } catch {
    return false
  }
}

export function todayISODate() {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function currentYearMonth() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

export function currentYearNumber() {
  return new Date().getFullYear()
}

export function toBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result)
      resolve(result.split(',')[1] || '')
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}
