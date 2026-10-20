import { useMantineColorScheme } from '@mantine/core'
import { NavLink, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAdminAuth } from '../auth/useAdminAuth'
import { adminPath } from '../adminBase'

const NAV_ITEMS = [
  { to: '/', end: true, icon: 'bi-speedometer2', label: 'Boshqaruv' },
  { to: '/media', icon: 'bi-film', label: 'Medialar' },
  { to: '/parts', icon: 'bi-collection-play', label: 'Qismlar' },
  { to: '/manga', icon: 'bi-book', label: 'Manga' },
  { to: '/podcast', icon: 'bi-mic', label: 'Podcast' },
  { to: '/broadcast', icon: 'bi-broadcast', label: 'Broadcast' },
  { to: '/users', icon: 'bi-people', label: 'Foydalanuvchilar' },
  { to: '/subscriptions', icon: 'bi-ticket-perforated', label: 'Arizalar' },
  { to: '/income', icon: 'bi-cash-coin', label: 'Tushumlar' },
  { to: '/genres', icon: 'bi-tags', label: 'Janrlar' },
  { to: '/coupons', icon: 'bi-percent', label: 'Kuponlar' },
  { to: '/quiz', icon: 'bi-question-circle', label: "O'yin savollari" },
  { to: '/game-ratings', icon: 'bi-trophy', label: 'O\'yin reytingi' },
  { to: '/channels', icon: 'bi-megaphone', label: 'Kanallar' },
  { to: '/logs', icon: 'bi-journal-text', label: 'Jurnallar' },
  { to: '/settings', icon: 'bi-gear', label: 'Sozlamalar' },
]

export default function AdminLayout() {
  const { user, logout } = useAdminAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const { colorScheme, setColorScheme } = useMantineColorScheme()
  const isDark = colorScheme === 'dark'

  function toggleTheme() {
    setColorScheme(isDark ? 'light' : 'dark')
  }

  if (!user) return <Navigate to={adminPath('/login')} replace />

  function handleLogout() {
    logout()
    navigate(adminPath('/login'), { replace: true })
  }

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-brand">
          <i className="bi bi-shield-lock" aria-hidden="true" />
          <span>AniChopar Admin</span>
        </div>
        <nav className="admin-nav" aria-label="Admin navigatsiya">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={adminPath(item.to)}
              end={item.end}
              className={({ isActive }) =>
                `admin-nav-link${isActive || (item.to !== '/' && location.pathname.startsWith(adminPath(item.to))) ? ' active' : ''}`
              }
            >
              <i className={`bi ${item.icon}`} aria-hidden="true" />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="admin-sidebar-footer">
          <div className="admin-user-chip">
            <i className="bi bi-person-circle" aria-hidden="true" />
            <span>{user.username || user.email || 'Admin'}</span>
          </div>
          <button
            type="button"
            className="admin-btn admin-btn-secondary admin-logout-btn"
            onClick={toggleTheme}
            title={isDark ? 'Kunduzgi rejim' : 'Tungi rejim'}
          >
            <i className={`bi ${isDark ? 'bi-sun' : 'bi-moon-stars'}`} aria-hidden="true" />
            {isDark ? 'Kunduzgi rejim' : 'Tungi rejim'}
          </button>
          <button type="button" className="admin-btn admin-btn-danger admin-logout-btn" onClick={handleLogout}>
            Chiqish
          </button>
        </div>
      </aside>
      <main className="admin-main">
        <Outlet />
      </main>
    </div>
  )
}
