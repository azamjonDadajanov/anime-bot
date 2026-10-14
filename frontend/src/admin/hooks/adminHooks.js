import { useCallback, useEffect, useRef, useState } from 'react'

export function useAsync(callback, deps = [], { immediate = true } = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(immediate)
  const [error, setError] = useState(null)
  const mounted = useRef(true)
  const callbackRef = useRef(callback)
  callbackRef.current = callback

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const run = useCallback(async (...args) => {
    setLoading(true)
    setError(null)
    try {
      const result = await callbackRef.current(...args)
      if (mounted.current) setData(result)
      return result
    } catch (err) {
      if (mounted.current) {
        setError(err?.response?.data?.detail || err?.message || 'Xatolik yuz berdi.')
      }
      throw err
    } finally {
      if (mounted.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (immediate) {
      run().catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { data, loading, error, run, setData }
}

export function usePaginated(fetcher, { pageSize = 20 } = {}) {
  const [items, setItems] = useState([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const fetcherRef = useRef(fetcher)

  useEffect(() => {
    fetcherRef.current = fetcher
  }, [fetcher])

  const load = useCallback(async (nextPage = page, extra = {}) => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetcherRef.current({ page: nextPage, page_size: pageSize, ...extra })
      const results = Array.isArray(data) ? data : data.results || []
      setItems(results)
      setCount(data.count ?? results.length)
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Yuklashda xatolik.')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [page, pageSize])

  useEffect(() => {
    load(page)
  }, [load, page])

  const totalPages = Math.max(1, Math.ceil(count / pageSize))

  return { items, count, page, setPage, totalPages, loading, error, reload: () => load(page) }
}

export function usePolling(callback, intervalMs = 5000, enabled = true) {
  const saved = useRef(callback)

  useEffect(() => {
    saved.current = callback
  }, [callback])

  useEffect(() => {
    if (!enabled) return undefined
    const id = setInterval(() => {
      saved.current().catch(() => {})
    }, intervalMs)
    return () => clearInterval(id)
  }, [intervalMs, enabled])
}
