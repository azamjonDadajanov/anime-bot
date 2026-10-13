import { NavLink, Outlet } from 'react-router-dom'
import PageHeading from '../../components/PageHeading'

const profileTabs = [
  { to: '/profile', label: "Ma'lumotlar", icon: 'bi-person-vcard', end: true },
  { to: '/profile/activity', label: 'Faolliklar', icon: 'bi-activity' },
  { to: '/profile/telegram', label: 'Telegram', icon: 'bi-telegram' },
  { to: '/profile/subscription', label: 'Obuna', icon: 'bi-ticket-perforated' },
  { to: '/profile/history', label: "Ko'rganlarim", icon: 'bi-clock-history' },
  { to: '/profile/settings', label: 'Sozlamalar', icon: 'bi-sliders' },
]

function ProfileLayout() {
  return (
    <main className="dashboard-page">
      <PageHeading
        eyebrow="HISOB / PROFIL"
        title="Profil"
        description="Hisob ma'lumotlari, faollik, Telegram, obuna va sozlamalar."
      />
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
