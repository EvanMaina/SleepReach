import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
    plugins: [react()],
    server: {
        host: '0.0.0.0',
        port: 5173,
        // Polling is required for file-change detection when the source is
        // bind-mounted from a Windows host into a Linux container — inotify
        // events do not cross that boundary, so Vite's default watcher never
        // sees edits and keeps serving stale cached transforms.
        watch: {
            usePolling: true,
            interval: 300,
        },
        proxy: {
            '/api': {
                target: process.env.BACKEND_URL || 'http://localhost:8000',
                changeOrigin: true,
            },
            '/health': {
                target: process.env.BACKEND_URL || 'http://localhost:8000',
                changeOrigin: true,
            },
        },
    },
})
