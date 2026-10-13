import { useEffect, useRef, useState } from 'react'
import { errorText } from './profileUtils'

/**
 * Load a profile resource and refetch whenever `key` changes.
 * `reload()` repeats the same request; `loading` is true until the
 * response for the current request arrives.
 */
export function useApi(load, key = '') {
  const loadRef = useRef(load)
  const [result, setResult] = useState({ key: null, data: null, error: '' })
  const [tick, setTick] = useState(0)
  const requestKey = `${key}#${tick}`

  useEffect(() => {
    loadRef.current = load
  })

  useEffect(() => {
    let active = true
    loadRef.current()
      .then((data) => {
        if (active) setResult({ key: requestKey, data, error: '' })
      })
      .catch((error) => {
        if (active) setResult({ key: requestKey, data: null, error: errorText(error) })
      })
    return () => { active = false }
  }, [requestKey])

  const current = result.key === requestKey
  return {
    data: current ? result.data : null,
    error: current ? result.error : '',
    loading: !current,
    reload: () => setTick((value) => value + 1),
  }
}
