import React from 'react'
import ReactDOM from 'react-dom/client'
import AssessmentPage from './pages/AssessmentPage'
import './styles/assessment.css'

const rootEl = document.getElementById('assessment-root')

if (rootEl) {
    rootEl.className = 'sr-assessment-root'
    ;(window as any).__SLEEPREACH_API_BASE__ = rootEl.getAttribute('data-api-url') || window.location.origin

    const root = ReactDOM.createRoot(rootEl)
    root.render(
        <React.StrictMode>
            <AssessmentPage apiUrl={(window as any).__SLEEPREACH_API_BASE__} />
        </React.StrictMode>,
    )
} else if (import.meta.env.DEV) {
    console.error('[Assessment] #assessment-root element not found')
}
