import { Navigate, Route, Routes } from 'react-router-dom'
import { adminPath } from './adminBase'
import { AdminAuthProvider } from './auth/AdminAuthProvider'
import { AdminRoute } from './auth/AdminRoute'
import AdminLayout from './components/AdminLayout'
import AdminLoginPage from './pages/AdminLoginPage'
import BroadcastPage from './pages/BroadcastPage'
import ChannelsPage from './pages/ChannelsPage'
import CouponsPage from './pages/CouponsPage'
import DashboardPage from './pages/DashboardPage'
import GameRatingsPage from './pages/GameRatingsPage'
import GenresPage from './pages/GenresPage'
import IncomePage from './pages/IncomePage'
import LogsPage from './pages/LogsPage'
import { MediaFormPage, MediaListPage, MediaPartsPage } from './pages/MediaPages'
import MediaQuizPage from './pages/MediaQuizPage'
import PodcastPage from './pages/PodcastPage'
import QuizQuestionsPage from './pages/QuizQuestionsPage'
import SettingsPage from './pages/SettingsPage'
import SubscriptionsPage from './pages/SubscriptionsPage'
import UsersPage, { UserDetailPage } from './pages/UsersPage'
import './admin.css'

export default function AdminApp() {
  return (
    <AdminAuthProvider>
      <Routes>
        <Route path="login" element={<AdminLoginPage />} />
        <Route
          element={(
            <AdminRoute>
              <AdminLayout />
            </AdminRoute>
          )}
        >
          <Route index element={<DashboardPage />} />
          <Route path="media" element={<MediaListPage />} />
          <Route path="media/new" element={<MediaFormPage />} />
          <Route path="media/:slug" element={<MediaPartsPage />} />
          <Route path="media/:slug/edit" element={<MediaFormPage />} />
          <Route path="media/:slug/quiz" element={<MediaQuizPage />} />
          <Route path="parts" element={<MediaListPage />} />
          <Route path="manga" element={<MediaListPage typeFilter="manga" />} />
          <Route path="podcast" element={<PodcastPage />} />
          <Route path="broadcast" element={<BroadcastPage />} />
          <Route path="users" element={<UsersPage />} />
          <Route path="users/:userId" element={<UserDetailPage />} />
          <Route path="subscriptions" element={<SubscriptionsPage />} />
          <Route path="income" element={<IncomePage />} />
          <Route path="genres" element={<GenresPage />} />
          <Route path="coupons" element={<CouponsPage />} />
          <Route path="quiz" element={<QuizQuestionsPage />} />
          <Route path="game-ratings" element={<GameRatingsPage />} />
          <Route path="channels" element={<ChannelsPage />} />
          <Route path="logs" element={<LogsPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to={adminPath('/')} replace />} />
      </Routes>
    </AdminAuthProvider>
  )
}
