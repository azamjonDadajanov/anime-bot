import { useEffect } from 'react'
import { Loader } from '@mantine/core'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../apis/useAuth'
import AiAssistantChat from './AiAssistantChat'
import Header, { BrandMark } from './Header'

const FOOTER_LINKS = [
  { to: '/explore', label: 'Kashf etish' },
  { to: '/anime', label: 'Animelar' },
  { to: '/movies', label: 'Filmlar' },
  { to: '/manga', label: 'Mangalar' },
  { to: '/rating', label: 'Reyting' },
  { to: '/game', label: "O'yin" },
  { to: '/subscription', label: 'Obuna' },
]

function DashboardLayout({ children }) {
  const { user, loading } = useAuth()
  const { pathname } = useLocation()

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' })
  }, [pathname])

  if (loading) return <div className="loading-state"><Loader size="sm" /></div>
  if (!user) return <Navigate to="/login" replace />

  return (
    <>
      <div className="ambient" aria-hidden="true">
        <div className="ambient-grid" />
        <div className="ambient-orb ambient-orb-a" />
        <div className="ambient-orb ambient-orb-b" />
        <div className="ambient-grain" />
      </div>

      <Header user={user} />

      <div id="main" className="page-shell" key={pathname}>
        {children}
      </div>

      <footer className="site-footer">
        <div className="footer-rail">
          <div className="footer-brand">
            <BrandMark />
            <div className="footer-word">Ani<span>Chopar</span></div>
            <p className="footer-tag">
              O&apos;zbek tilidagi anime, kino, serial va manga — bitta orbital
              katalogda. Toshkentdan translyatsiya.
            </p>
          </div>
          <nav className="footer-links" aria-label="Sayt bo'limlari">
            {FOOTER_LINKS.map((item) => (
              <Link key={item.to} to={item.to}>{item.label}</Link>
            ))}
          </nav>
          <div className="footer-meta">
            <span className="pill pill-live">Tizim onlayn</span>
            <span>© 2026 · Toshkent</span>
            <span>AniChopar · Signal 02</span>
          </div>
        </div>
      </footer>

      {/* AI yordamchi: a launcher in the bottom-right corner, subscribers only.
          The API enforces the same rule, so hiding it is only about not
          advertising a paid feature to accounts that cannot use it. */}
      {user.subscription?.is_active && <AiAssistantChat />}
    </>
  )
}

export default DashboardLayout
