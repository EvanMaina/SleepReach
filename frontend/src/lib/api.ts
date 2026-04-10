import axios from 'axios'

const api = axios.create({
    baseURL: '/api',
    headers: { 'Content-Type': 'application/json' },
    timeout: 15000,
})

// Attach JWT token to every request
api.interceptors.request.use((config) => {
    const token = sessionStorage.getItem('sleepreach_token')
    if (token) {
        config.headers.Authorization = `Bearer ${token}`
    }
    return config
})

// Handle 401 responses (token expired)
api.interceptors.response.use(
    (response) => response,
    async (error) => {
        if (error.response?.status === 401) {
            // Try refresh token
            const refreshToken = sessionStorage.getItem('sleepreach_refresh_token')
            if (refreshToken && !error.config._retry) {
                error.config._retry = true
                try {
                    const res = await axios.post('/api/auth/refresh', {
                        refresh_token: refreshToken,
                    })
                    const { access_token, refresh_token } = res.data
                    sessionStorage.setItem('sleepreach_token', access_token)
                    sessionStorage.setItem('sleepreach_refresh_token', refresh_token)
                    error.config.headers.Authorization = `Bearer ${access_token}`
                    return api(error.config)
                } catch {
                    sessionStorage.removeItem('sleepreach_token')
                    sessionStorage.removeItem('sleepreach_refresh_token')
                    window.location.hash = '#/login'
                }
            } else {
                sessionStorage.removeItem('sleepreach_token')
                sessionStorage.removeItem('sleepreach_refresh_token')
                window.location.hash = '#/login'
            }
        }
        return Promise.reject(error)
    }
)

export default api

// Auth API
export const authAPI = {
    login: (email: string, password: string) =>
        api.post('/auth/login', { email, password }),
    me: () => api.get('/auth/me'),
    changePassword: (current_password: string | null, new_password: string) =>
        api.post('/auth/change-password', { current_password, new_password }),
    logout: () => api.post('/auth/logout'),
    forgotPassword: (email: string) => api.post('/auth/forgot-password', { email }),
    validateResetToken: (token: string) => api.get('/auth/validate-reset-token', { params: { token } }),
    resetPassword: (token: string, new_password: string) =>
        api.post('/auth/reset-password', { token, new_password }),
    requestAccess: (data: { full_name: string; email: string; reason: string }) =>
        api.post('/auth/request-access', data),
}

// Leads API
export const leadsAPI = {
    list: (params?: Record<string, any>) => api.get('/leads', { params }),
    get: (id: string) => api.get(`/leads/${id}`),
    createManual: (data: any) => api.post('/leads/manual', data),
    update: (id: string, data: any) => api.patch(`/leads/${id}`, data),
    delete: (id: string) => api.delete(`/leads/${id}`),
    restore: (id: string) => api.post(`/leads/${id}/restore`),
    updateContactOutcome: (id: string, data: { contact_outcome: string; notes?: string; next_follow_up_at?: string }) =>
        api.patch(`/leads/${id}/contact-outcome`, data),
    updateConsultationOutcome: (id: string, data: { outcome: string; notes?: string; scheduled_callback_at?: string }) =>
        api.patch(`/leads/${id}/consultation-outcome`, data),
    schedule: (id: string, data: { scheduled_callback_at: string; contact_method: string; schedule_type?: string; scheduled_notes?: string }) =>
        api.post(`/leads/${id}/schedule`, data),
    getNotes: (id: string) => api.get(`/leads/${id}/notes`),
    createNote: (id: string, data: { note_text: string; note_type?: string; related_outcome?: string }) =>
        api.post(`/leads/${id}/notes`, data),
    queueSummary: () => api.get('/leads/queue-summary'),
}

// Communications API
export const communicationsAPI = {
    sendEmail: (data: { lead_id: string; category: string; subject: string; body: string }) =>
        api.post('/communications/email/send', data),
    sendSMS: (data: { lead_id?: string; to_phone?: string; category: string; message: string }) =>
        api.post('/communications/sms/send', data),
    getTemplates: () => api.get('/communications/templates'),
    updateTemplates: (data: any) => api.put('/communications/templates', data),
}

// Analytics API
export const analyticsAPI = {
    dashboard: () => api.get('/analytics/dashboard'),
}

// Users API
export const usersAPI = {
    list: () => api.get('/users'),
    create: (data: any) => api.post('/users', data),
    update: (id: string, data: any) => api.put(`/users/${id}`, data),
    delete: (id: string) => api.delete(`/users/${id}`),
    getPreferences: () => api.get('/users/me/preferences'),
    updatePreferences: (data: any) => api.put('/users/me/preferences', data),
    getClinicSettings: () => api.get('/users/clinic-settings'),
    updateClinicSettings: (data: any) => api.put('/users/clinic-settings', data),
}

// Providers API
export const providersAPI = {
    list: (params?: Record<string, any>) => api.get('/providers', { params }),
    get: (id: string) => api.get(`/providers/${id}`),
    create: (data: any) => api.post('/providers', data),
    update: (id: string, data: any) => api.patch(`/providers/${id}`, data),
    stats: () => api.get('/providers/stats'),
    referrals: (id: string, params?: Record<string, any>) => api.get(`/providers/${id}/referrals`, { params }),
    sendEmail: (id: string, data: { subject: string; message: string }) => api.post(`/providers/${id}/email`, data),
}

// AI Insights API
export const aiInsightsAPI = {
    get: (params?: { force_refresh?: boolean }) => api.get('/ai-insights', { params }),
}
