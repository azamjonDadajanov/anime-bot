import { Navigate, Route, Routes } from 'react-router-dom'
import Header from './components/Header'
import DashboardLayout from './components/DashboardLayout'
import AuthPage from './pages/AuthPage'
import TelegramAuthPage from './pages/TelegramAuthPage'
import HomePage from './pages/HomePage'
import FavoritesPage from './pages/FavoritesPage'
import MediaDetailPage from './pages/MediaDetailPage'
import CatalogSectionPage from './pages/CatalogSectionPage'
import MangaReaderPage from './pages/MangaReaderPage'
import SubscriptionPage from './pages/SubscriptionPage'
import ProfileLayout from './pages/profile/ProfileLayout'
import ProfileOverviewPage from './pages/profile/ProfileOverviewPage'
import ProfileActivityPage from './pages/profile/ProfileActivityPage'
import ProfileTelegramPage from './pages/profile/ProfileTelegramPage'
import ProfileSubscriptionPage from './pages/profile/ProfileSubscriptionPage'
import ProfileHistoryPage from './pages/profile/ProfileHistoryPage'
import ProfileSettingsPage from './pages/profile/ProfileSettingsPage'
import 'bootstrap-icons/font/bootstrap-icons.css'
import './App.css'

const sectionRoutes = ['latest', 'popular', 'upcoming', 'movies', 'anime', 'manga', 'series']

export default function App() {
  return (
    <div className="app-shell">
      <Routes>
        <Route path="/login" element={<><Header /><AuthPage mode="login" /></>} />
        <Route path="/register" element={<><Header /><AuthPage mode="register" /></>} />
        <Route path="/telegram-auth" element={<><Header /><TelegramAuthPage /></>} />
        <Route path="/" element={<DashboardLayout><HomePage /></DashboardLayout>} />
        {sectionRoutes.map((key) => (
          <Route
            key={key}
            path={`/${key}`}
            element={<DashboardLayout><CatalogSectionPage section={key} /></DashboardLayout>}
          />
        ))}
        <Route path="/favorites" element={<DashboardLayout><FavoritesPage /></DashboardLayout>} />
        <Route path="/media/:slug" element={<DashboardLayout><MediaDetailPage /></DashboardLayout>} />
        <Route path="/read/:slug/:number?" element={<MangaReaderPage />} />
        <Route path="/subscription" element={<DashboardLayout><SubscriptionPage /></DashboardLayout>} />
        <Route path="/profile" element={<DashboardLayout><ProfileLayout /></DashboardLayout>}>
          <Route index element={<ProfileOverviewPage />} />
          <Route path="activity" element={<ProfileActivityPage />} />
          <Route path="telegram" element={<ProfileTelegramPage />} />
          <Route path="subscription" element={<ProfileSubscriptionPage />} />
          <Route path="history" element={<ProfileHistoryPage />} />
          <Route path="settings" element={<ProfileSettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}