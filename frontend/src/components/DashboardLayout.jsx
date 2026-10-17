import { Loader } from '@mantine/core'
import { NavLink, Navigate } from 'react-router-dom'
import { useAuth } from '../apis/useAuth'
import AiSearchChat from './AiSearchChat'
import Header from './Header'

function DashboardLayout({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="loading-state"><Loader /></div>
  if (!user) return <Navigate to="/login" replace />

  return (
    <>
      <Header user={user} />
      <nav className="top-nav" aria-label="Asosiy navigatsiya">
        <div className="top-nav-inner">
          <NavLink end className={({ isActive }) => `top-nav-link${isActive ? ' active' : ''}`} to="/">
            <i className="bi bi-house-door top-nav-icon" aria-hidden="true" /><span>Bosh sahifa</span>
          </NavLink>
          <NavLink className={({ isActive }) => `top-nav-link${isActive ? ' active' : ''}`} to="/favorites">
            <i className="bi bi-heart top-nav-icon" aria-hidden="true" /><span>Sevimlilar</span>
          </NavLink>
          <NavLink className={({ isActive }) => `top-nav-link${isActive ? ' active' : ''}`} to="/subscription">
            <i className="bi bi-ticket-perforated top-nav-icon" aria-hidden="true" /><span>Obuna</span>
          </NavLink>
          <NavLink className={({ isActive }) => `top-nav-link${isActive ? ' active' : ''}`} to="/rating">
            <i className="bi bi-trophy top-nav-icon" aria-hidden="true" /><span>Reyting</span>
          </NavLink>
        </div>
      </nav>
      <div className="dashboard-shell">{children}</div>
      {/* AI search: a launcher in the bottom-right corner on every page. */}
      <AiSearchChat />
    </>
  )
}

export default DashboardLayout