import { useEffect, useState } from 'react'
import { useMantineColorScheme } from '@mantine/core'
import { Link } from 'react-router-dom'
import { profileApi } from '../apis/api'
import { useAuth } from '../apis/useAuth'
import SearchModal from './SearchModal'

function ThemeButton() {
  const { colorScheme, setColorScheme } = useMantineColorScheme()
  const { user } = useAuth()
  const isDark = colorScheme === 'dark'
  const label = isDark ? 'Kunduzgi mavzu' : 'Tungi mavzu'

  function toggleTheme() {
    const next = isDark ? 'light' : 'dark'
    setColorScheme(next)
    // Keep the saved profile preference in sync for signed-in visitors.
    if (user) profileApi.updateSettings({ theme: next }).catch(() => {})
  }

  return (
    <button
      className="header-icon-button theme-toggle"
      type="button"
      aria-label={label}
      title={label}
      onClick={toggleTheme}
    >
      <i className={`bi ${isDark ? 'bi-sun' : 'bi-moon-stars'}`} aria-hidden="true" />
    </button>
  )
}

function Header({ user }) {
  const [searchOpened, setSearchOpened] = useState(false)

  useEffect(() => {
    function handleKeydown(event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setSearchOpened(true)
      }
    }
    window.addEventListener('keydown', handleKeydown)
    return () => window.removeEventListener('keydown', handleKeydown)
  }, [])

  const initial = (user?.username || '').trim().charAt(0).toUpperCase()

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Link className="wordmark" to="/" aria-label="Kino Top bosh sahifa">
          <span className="wordmark-mark" aria-hidden="true">K</span>
          <span className="wordmark-text">KINO <b>TOP</b></span>
        </Link>

        <div className="header-actions">
          <button
            className="header-search"
            type="button"
            aria-label="Katalogdan qidirish"
            title="Qidirish"
            onClick={() => setSearchOpened(true)}
          >
            <i className="bi bi-search header-search-icon" aria-hidden="true" />
            <span className="header-search-label">Kino yoki anime qidirish</span>
            <kbd className="header-search-kbd">Ctrl K</kbd>
          </button>

          {user && (
            <Link className="header-user" to="/profile" title="Profil">
              <span className="header-avatar" aria-hidden="true">{initial}</span>
              <span className="header-user-name">{user.username}</span>
            </Link>
          )}

          <ThemeButton />
        </div>
      </div>
      <SearchModal opened={searchOpened} onClose={() => setSearchOpened(false)} />
    </header>
  )
}

export default Header
