import { useCallback, useEffect, useMemo, useState } from 'react'
import { mediaApi } from '../apis/api'
import {
  genreNames,
  normalizeList,
  sortByNewest,
  sortByRating,
  sortByTopRating,
} from '../mediaMeta'

const GENRE_GLYPHS = ['伝', '炎', '夢', '影', '星', '刃', '旅', '謎', '光', '響']
const GENRE_HUES = [245, 22, 280, 198, 156, 8, 265, 320]

/**
 * One catalogue request feeds the whole homepage: hero pick, newest drops,
 * rating chart, genre portals and the type index. Titles are small JSON rows
 * (covers are URLs), so a single cached read keeps the page fast.
 */
export function useCatalogIndex() {
  const [state, setState] = useState({ items: [], top: [], loading: true, error: '' })
  const [reloadKey, setReloadKey] = useState(0)

  const reload = useCallback(() => setReloadKey((value) => value + 1), [])

  useEffect(() => {
    let active = true
    setState((current) => ({ ...current, loading: true, error: '' }))
    // «Top reyting» is ranked on the server (average, then votes); the
    // catalogue page itself is not sorted by the live score. A failure only
    // costs the ranking, never the page.
    Promise.all([
      mediaApi.catalog(),
      mediaApi.topRated({ limit: 5 }).catch(() => null),
    ])
      .then(([data, top]) => {
        if (!active) return
        setState({
          items: normalizeList(data),
          top: normalizeList(top),
          loading: false,
          error: '',
        })
      })
      .catch(() => {
        if (!active) return
        setState({ items: [], top: [], loading: false, error: "Katalog bilan bog'lanishda xatolik yuz berdi." })
      })
    return () => { active = false }
  }, [reloadKey])

  const index = useMemo(() => {
    const items = state.items
    const rated = sortByRating(items)
    const latest = sortByNewest(items)

    const genreMap = new Map()
    items.forEach((item) => {
      genreNames(item).forEach((name) => {
        genreMap.set(name, (genreMap.get(name) || 0) + 1)
      })
    })
    const allGenres = Array.from(genreMap.entries())
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([name, count]) => ({ name, count }))

    const genres = allGenres
      .slice(0, 8)
      .map(({ name, count }, position) => ({
        name,
        count,
        glyph: GENRE_GLYPHS[position % GENRE_GLYPHS.length],
        hue: GENRE_HUES[position % GENRE_HUES.length],
        code: String(position + 1).padStart(2, '0'),
      }))

    return {
      featured: rated[0] || latest[0] || null,
      latest: latest.slice(0, 6),
      trending: rated.slice(0, 12),
      // The server's ranked list, or the same ranking computed locally when
      // the caller has not loaded it (cached page, offline request).
      top: state.top.length ? state.top.slice(0, 5) : sortByTopRating(items).slice(0, 5),
      editorial: rated.slice(1, 5),
      upcoming: items.filter((item) => item.status === 'upcoming').slice(0, 3),
      genres,
      allGenres,
      counts: {
        anime: items.filter((item) => item.type === 'anime').length,
        movie: items.filter((item) => item.type === 'movie').length,
        series: items.filter((item) => item.type === 'series').length,
        manga: items.filter((item) => item.type === 'manga').length,
        total: items.length,
      },
    }
  }, [state.items, state.top])

  return { ...state, ...index, items: state.items, reload }
}

export default useCatalogIndex
