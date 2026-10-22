import { useEffect, useState } from 'react'
import { Menu, useMantineColorScheme } from '@mantine/core'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { profileApi } from '../apis/api'
import { useAuth } from '../apis/useAuth'
import SearchModal from './SearchModal'
import SupportModal from './SupportModal'

const NAV_ITEMS = [
  { to: '/', label: 'Bosh sahifa', end: true },
  { to: '/explore', label: 'Kashf etish' },
  { to: '/favorites', label: 'Sevimlilar' },
  { to: '/subscription', label: 'Obuna' },
  { to: '/rating', label: 'Reyting' },
]

const CATALOG_LINKS = [
  { to: '/anime', label: 'Animelar', icon: 'bi-stars' },
  { to: '/movies', label: 'Filmlar', icon: 'bi-film' },
  { to: '/series', label: 'Seriallar', icon: 'bi-collection-play' },
  { to: '/manga', label: 'Mangalar', icon: 'bi-journal-bookmark' },
  { to: '/latest', label: 'Yangi qo\u2019shilganlar', icon: 'bi-lightning-charge' },
  { to: '/upcoming', label: 'Kutilmoqda', icon: 'bi-hourglass-split' },
  { to: '/game', label: "O'yin", icon: 'bi-controller' },
]

const DOCK_ITEMS = [
  { to: '/', label: 'Asosiy', icon: 'bi-grid-1x2', end: true },
  { to: '/explore', label: 'Kashf', icon: 'bi-compass' },
  { to: '/favorites', label: 'Saqlangan', icon: 'bi-heart' },
  { to: '/subscription', label: 'Obuna', icon: 'bi-ticket-perforated' },
  { to: '/profile', label: 'Profil', icon: 'bi-person' },
]

export function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 44 44" fill="none" stroke="currentColor">
        <circle cx="22" cy="22" r="19.5" opacity=".28" />
        <path d="M22 5c6.6 5 9.8 10.4 9.8 17S28.6 34 22 39c-6.6-5-9.8-10.4-9.8-17S15.4 10 22 5Z" opacity=".45" />
        <path d="M5.5 16.2C10 12.6 15.5 10.6 22 10.6s12 2 16.5 5.6M5.5 27.8C10 31.4 15.5 33.4 22 33.4s12-2 16.5-5.6" opacity=".3" />
        <path d="M14.4 29.4 22 12.6l7.6 16.8" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M17.6 23.4h8.8" strokeWidth="2.2" strokeLinecap="round" />
      </svg>
    </span>
  )
}

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
      className="icon-button theme-toggle"
      type="button"
      aria-label={label}
      title={label}
      onClick={toggleTheme}
    >
      <i className={`bi ${isDark ? 'bi-sun' : 'bi-moon-stars'}`} aria-hidden="true" />
    </button>
  )
}

function Header({ user: headerUser }) {
  const { user: authUser, logout } = useAuth()
  const user = headerUser ?? authUser
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [searchOpened, setSearchOpened] = useState(false)
  const [supportOpened, setSupportOpened] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const active = Boolean(user?.subscription?.is_active)

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

  useEffect(() => {
    let frame = 0
    function onScroll() {
      if (frame) return
      frame = window.requestAnimationFrame(() => {
        setScrolled(window.scrollY > 10)
        frame = 0
      })
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [])

  useEffect(() => {
    setSearchOpened(false)
    setSupportOpened(false)
  }, [pathname])

  const initial = (user?.username || '?').trim().charAt(0).toUpperCase()

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <>
      <header className={`site-header${scrolled ? ' is-scrolled' : ''}`}>
        <div className="header-rail">
          <Link className="brand" to="/" aria-label="AniChopar bosh sahifa">
            <BrandMark />
            <span className="brand-copy">
              <span className="brand-word">Ani<em>Chopar</em></span>
              <span className="brand-sub">アニチョパール · 2026</span>
            </span>
          </Link>

          {user && (
            <nav className="primary-nav" aria-label="Asosiy navigatsiya">
              {NAV_ITEMS.slice(0, 2).map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => `nav-link${isActive ? ' is-active' : ''}`}
                >
                  {item.label}
                </NavLink>
              ))}
              <Menu position="bottom-start" width={228} shadow="md">
                <Menu.Target>
                  <button className="nav-link" type="button" aria-label="Katalog bo'limlari">
                    Katalog <i className="bi bi-chevron-down" aria-hidden="true" style={{ fontSize: 9 }} />
                  </button>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Label>Bo'limlar</Menu.Label>
                  {CATALOG_LINKS.map((item) => (
                    <Menu.Item
                      key={item.to}
                      component={Link}
                      to={item.to}
                      leftSection={<i className={`bi ${item.icon}`} aria-hidden="true" />}
                    >
                      {item.label}
                    </Menu.Item>
                  ))}
                </Menu.Dropdown>
              </Menu>
              {NAV_ITEMS.slice(2).map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => `nav-link${isActive ? ' is-active' : ''}`}
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          )}

          <div className="header-tools">
            <button
              className="search-trigger"
              type="button"
              aria-label="Katalogdan qidirish"
              title="Qidirish"
              onClick={() => setSearchOpened(true)}
            >
              <i className="bi bi-search" aria-hidden="true" />
              <span className="search-trigger-label">Qidirish</span>
              <kbd className="kbd">Ctrl K</kbd>
            </button>

            {user && (
              <button
                className="icon-button"
                type="button"
                aria-label="Adminga xabar yozish"
                title="Adminga xabar"
                onClick={() => setSupportOpened(true)}
              >
                <i className="bi bi-envelope" aria-hidden="true" />
              </button>
            )}

            <ThemeButton />

            {user && (
              <Menu position="bottom-end" width={220} shadow="md">
                <Menu.Target>
                  <button className="profile-button" type="button" aria-label="Profil menyusi">
                    <span className={`profile-avatar${active ? ' profile-avatar--subscribed' : ''}`} aria-hidden="true">{initial}</span>
                    <span className="profile-name">{user.username}</span>
                    <i className="bi bi-chevron-down" aria-hidden="true" />
                  </button>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Label>{user.username}</Menu.Label>
                  <Menu.Item component={Link} to="/profile" leftSection={<i className="bi bi-person" aria-hidden="true" />}>
                    Profil
                  </Menu.Item>
                  <Menu.Item component={Link} to="/profile/history" leftSection={<i className="bi bi-clock-history" aria-hidden="true" />}>
                    Ko&apos;rganlarim
                  </Menu.Item>
                  <Menu.Item component={Link} to="/profile/settings" leftSection={<i className="bi bi-sliders" aria-hidden="true" />}>
                    Sozlamalar
                  </Menu.Item>
                  <Menu.Item component={Link} to="/game" leftSection={<i className="bi bi-controller" aria-hidden="true" />}>
                    Anime o&apos;yini
                  </Menu.Item>
                  <Menu.Divider />
                  <Menu.Item
                    color="red"
                    onClick={handleLogout}
                    leftSection={<i className="bi bi-box-arrow-right" aria-hidden="true" />}
                  >
                    Hisobdan chiqish
                  </Menu.Item>
                </Menu.Dropdown>
              </Menu>
            )}
          </div>
        </div>
        <SearchModal opened={searchOpened} onClose={() => setSearchOpened(false)} />
        <SupportModal opened={supportOpened} onClose={() => setSupportOpened(false)} />
      </header>

      {user && (
        <nav className="dock" aria-label="Mobil navigatsiya">
          {DOCK_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `dock-link${isActive ? ' is-active' : ''}`}
            >
              <i className={`bi ${item.icon}`} aria-hidden="true" />
              <span className="dock-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>
      )}
    </>
  )
}

export default Header
