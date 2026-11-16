import { Spin } from 'antd'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { useSession } from '../stores/session'

export function FullPageSpin() {
  return (
    <div className="full-page-spin">
      <Spin size="large" />
    </div>
  )
}

/** Renders children only for signed-in users; otherwise sends them to /login. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const status = useSession((s) => s.status)
  const location = useLocation()
  if (status === 'loading') return <FullPageSpin />
  if (status === 'anon') return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return <>{children}</>
}

/** Pages like /login that signed-in users shouldn't see. */
export function GuestOnly({ children }: { children: ReactNode }) {
  const status = useSession((s) => s.status)
  if (status === 'loading') return <FullPageSpin />
  if (status === 'authed') return <Navigate to="/" replace />
  return <>{children}</>
}
