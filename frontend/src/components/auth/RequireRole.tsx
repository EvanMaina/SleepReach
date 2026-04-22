import { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'

interface RequireRoleProps {
    roles: string[]
    children: ReactNode
    redirectTo?: string
}

/**
 * RequireRole — blocks a route from users whose role isn't in the allowed list.
 * Redirects unauthorized users to `redirectTo` (default: dashboard).
 *
 * Must be rendered inside AuthProvider and HashRouter. Assumes the user is
 * already authenticated — unauthenticated users are handled by AuthGate
 * before any route ever mounts.
 */
export function RequireRole({ roles, children, redirectTo = '/' }: RequireRoleProps) {
    const { user } = useAuth()
    if (!user || !roles.includes(user.role)) {
        return <Navigate to={redirectTo} replace />
    }
    return <>{children}</>
}
