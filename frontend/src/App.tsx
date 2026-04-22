import { useEffect, useState } from 'react'
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './contexts/AuthContext'
import LoginPage from './pages/LoginPage'
import ChangePasswordPage from './pages/ChangePasswordPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import ResetPasswordPage from './pages/ResetPasswordPage'
import RequestInvitationPage from './pages/RequestInvitationPage'
import WidgetPage from './pages/WidgetPage'
import DashboardLayout from './layouts/DashboardLayout'
import DashboardPage from './pages/DashboardPage'
import CoordinatorPage from './pages/CoordinatorPage'
import AllLeadsPage from './pages/AllLeadsPage'
import DeletedLeadsPage from './pages/DeletedLeadsPage'
import ProvidersPage from './pages/ProvidersPage'
import AnalyticsPage from './pages/AnalyticsPage'
import AIInsightsPage from './pages/AIInsightsPage'
import SettingsPage from './pages/SettingsPage'
import { RequireRole } from './components/auth/RequireRole'
import { Moon } from 'lucide-react'

function getPublicHashRoute(hash: string) {
    if (hash.startsWith('#forgot-password')) return 'forgot-password'
    if (hash.startsWith('#reset-password')) return 'reset-password'
    if (hash.startsWith('#request-invitation')) return 'request-invitation'
    return null
}

/**
 * AuthGate — renders LoginPage when unauthenticated.
 * Replicates SleepReach's auth gate pattern: the entire app
 * is gated behind authentication BEFORE any routing happens.
 * This prevents any flash of dashboard content for unauthenticated users.
 */
function AuthGate() {
    const { isAuthenticated, isLoading, user } = useAuth()
    const [hash, setHash] = useState(window.location.hash)

    useEffect(() => {
        const onHashChange = () => setHash(window.location.hash)
        window.addEventListener('hashchange', onHashChange)
        return () => window.removeEventListener('hashchange', onHashChange)
    }, [])

    const publicRoute = getPublicHashRoute(hash)

    // Show loading spinner while checking auth token
    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gray-50">
                <div className="text-center">
                    <div className="w-12 h-12 rounded-2xl bg-sleep-900 flex items-center justify-center mx-auto mb-4">
                        <Moon className="w-6 h-6 text-sleep-200 animate-pulse" />
                    </div>
                    <p className="text-sm text-gray-500">Loading...</p>
                </div>
            </div>
        )
    }

    // CRITICAL: If not authenticated, show login page immediately.
    // No routing, no redirect, no flash of dashboard content.
    if (!isAuthenticated) {
        if (publicRoute === 'forgot-password') {
            return <ForgotPasswordPage />
        }
        if (publicRoute === 'reset-password') {
            return <ResetPasswordPage />
        }
        if (publicRoute === 'request-invitation') {
            return <RequestInvitationPage />
        }
        return <LoginPage />
    }

    // If user must change password, show LoginPage (inline password form)
    if (user?.must_change_password) {
        return <LoginPage />
    }

    // Authenticated — render the full app with routing
    return (
        <HashRouter>
            <Routes>
                <Route path="/login" element={<Navigate to="/" replace />} />
                <Route path="/change-password" element={<ChangePasswordPage />} />
                <Route path="/widget" element={<WidgetPage />} />
                <Route path="/" element={<DashboardLayout />}>
                    <Route index element={<DashboardPage />} />
                    <Route path="coordinator" element={<CoordinatorPage />} />
                    <Route path="coordinator/:queue" element={<CoordinatorPage />} />
                    <Route path="leads" element={<AllLeadsPage />} />
                    <Route path="deleted" element={<DeletedLeadsPage />} />
                    <Route path="providers" element={<ProvidersPage />} />
                    <Route path="analytics" element={<AnalyticsPage />} />
                    <Route path="ai-insights" element={<AIInsightsPage />} />
                    <Route
                        path="settings"
                        element={
                            <RequireRole roles={['primary_admin', 'administrator']}>
                                <SettingsPage />
                            </RequireRole>
                        }
                    />
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </HashRouter>
    )
}

export default function App() {
    return <AuthGate />
}
