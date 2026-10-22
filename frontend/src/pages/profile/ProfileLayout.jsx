import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../../apis/useAuth'

const profileTabs = [
  { to: '/profile', label: "Ma'lumotlar", icon: 'bi-person-vcard', end: true },
  { to: '/profile/activity', label: 'Faolliklar', icon: 'bi-activity' },
  { to: '/profile/telegram', label: 'Telegram', icon: 'bi-telegram' },
  { to: '/profile/subscription', label: 'Obuna', icon: 'bi-ticket-perforated' },
  { to: '/profile/history', label: "Ko'rganlarim", icon: 'bi-clock-history' },
  { to: '/profile/settings', label: 'Sozlamalar', icon: 'bi-sliders' },
]

function ProfileLayout() {
  const { user } = useAuth()
  const initial = (user?.username || '?').trim().charAt(0).toUpperCase()
  const subscription = user?.subscription
  const active = Boolean(subscription?.is_active)
  const planLabel = subscription?.plan_label || (active ? 'Faol tarif' : 'Bepul')
  const daysLeft = subscription?.days_left

  return (
    <main className="dashboard-page">
      <section className="profile-hero">
        <div className="profile-hero-main">
          <span className={`profile-avatar-lg${active ? ' profile-avatar-lg--subscribed' : ''}`} aria-hidden="true">{initial}</span>
          <div className="profile-identity">
            <span className="eyebrow">Hisob / Profil</span>
            <h1 className="profile-name-lg">{user?.username || 'Profil'}</h1>
            <span className="profile-handle">
              {user?.email || 'AniChopar hisobi'} · ID #{user?.id ?? '—'}
            </span>
            <div className="profile-badges">
              <span className={`pill ${active ? 'pill-accent' : ''}`}>
                {active ? <i className="bi bi-stars" aria-hidden="true" /> : null}
                {planLabel}
              </span>
              <span className="pill">
                <i className="bi bi-telegram" aria-hidden="true" />
                {user?.telegram_id ? 'Telegram ulangan' : 'Telegram ulanmagan'}
              </span>
              <span className="pill">
                <i className="bi bi-broadcast" aria-hidden="true" /> AC / 26
              </span>
            </div>
          </div>
        </div>

        <div className="profile-hero-side">
          <NavLink className="profile-hero-stat" to="/profile/subscription">
            <b>{active ? (daysLeft ?? '∞') : '—'}</b>
            <span>Qolgan kun</span>
          </NavLink>
          <NavLink className="profile-hero-stat" to="/profile/history">
            <b>{subscription?.plan_label ? 'Pro' : 'Free'}</b>
            <span>Joriy tarif</span>
          </NavLink>
          <NavLink className="profile-hero-stat" to="/favorites">
            <b><i className="bi bi-heart" aria-hidden="true" /></b>
            <span>Kutubxona</span>
          </NavLink>
          <NavLink className="profile-hero-stat" to="/profile/telegram">
            <b><i className="bi bi-telegram" aria-hidden="true" /></b>
            <span>Bot aloqasi</span>
          </NavLink>
        </div>
      </section>

      <nav className="profile-tabs" aria-label="Profil bo'limlari">
        {profileTabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) => `profile-tab${isActive ? ' active' : ''}`}
          >
            <i className={`bi ${tab.icon}`} aria-hidden="true" />
            <span>{tab.label}</span>
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </main>
  )
}

export default ProfileLayout
