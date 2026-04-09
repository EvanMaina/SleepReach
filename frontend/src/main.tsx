import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { AuthProvider } from './contexts/AuthContext'
import App from './App'
import './index.css'

const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: false,
        },
    },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
        <QueryClientProvider client={queryClient}>
            <AuthProvider>
                <App />
                <Toaster
                    position="bottom-center"
                    toastOptions={{
                        duration: 3000,
                        style: {
                            borderRadius: '12px',
                            background: '#1e293b',
                            color: '#fff',
                            fontSize: '14px',
                            padding: '12px 20px',
                            boxShadow: '0 8px 30px rgba(0,0,0,0.12)',
                        },
                        success: {
                            iconTheme: { primary: '#10b981', secondary: '#fff' },
                        },
                        error: {
                            iconTheme: { primary: '#ef4444', secondary: '#fff' },
                        },
                    }}
                />
            </AuthProvider>
        </QueryClientProvider>
    </React.StrictMode>,
)
