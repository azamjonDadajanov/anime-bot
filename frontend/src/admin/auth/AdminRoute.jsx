import { Loader } from '@mantine/core'
import { Navigate, useLocation } from 'react-router-dom'
import { useAdminAuth } from './useAdminAuth'

export function AdminRoute({ children }) {
  const { user, loading } = useAdminAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="admin-loading">
        <Loader size="lg" />
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/admin/login" replace state={{ from: location.pathname }} />
  }

  return children
}
