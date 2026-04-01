import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { authAPI } from '../lib/api'

interface User {
    id: string
    email: string
    first_name: string
    last_name: string
    role: string
    status: string
    must_change_password: boolean
    last_login: string | null
    created_at: string
    updated_at: string
}

interface AuthState {
    user: User | null
    permissions: string[]
    isLoading: boolean
    isAuthenticated: boolean
}

interface AuthContextType extends AuthState {
    login: (email: string, password: string) => Promise<{ must_change_password: boolean }>
    logout: () => void
    refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
    const [state, setState] = useState<AuthState>({
        user: null,
        permissions: [],
        isLoading: true,
        isAuthenticated: false,
    })

    const refreshUser = async () => {
        try {
            const token = sessionStorage.getItem('sleepreach_token')
            if (!token) {
                setState({ user: null, permissions: [], isLoading: false, isAuthenticated: false })
                return
            }
            const res = await authAPI.me()
            setState({
                user: res.data.user,
                permissions: res.data.permissions || [],
                isLoading: false,
                isAuthenticated: true,
            })
        } catch {
            sessionStorage.removeItem('sleepreach_token')
            sessionStorage.removeItem('sleepreach_refresh_token')
            setState({ user: null, permissions: [], isLoading: false, isAuthenticated: false })
        }
    }

    useEffect(() => {
        refreshUser()
    }, [])

    const login = async (email: string, password: string) => {
        const res = await authAPI.login(email, password)
        const { access_token, refresh_token, user, must_change_password } = res.data
        sessionStorage.setItem('sleepreach_token', access_token)
        sessionStorage.setItem('sleepreach_refresh_token', refresh_token)
        setState({
            user,
            permissions: [],
            isLoading: false,
            isAuthenticated: true,
        })
        // Fetch full permissions
        refreshUser()
        return { must_change_password }
    }

    const logout = () => {
        authAPI.logout().catch(() => { })
        sessionStorage.removeItem('sleepreach_token')
        sessionStorage.removeItem('sleepreach_refresh_token')
        setState({ user: null, permissions: [], isLoading: false, isAuthenticated: false })
    }

    return (
        <AuthContext.Provider value={{ ...state, login, logout, refreshUser }}>
            {children}
        </AuthContext.Provider>
    )
}

export function useAuth() {
    const ctx = useContext(AuthContext)
    if (!ctx) throw new Error('useAuth must be used within AuthProvider')
    return ctx
}
