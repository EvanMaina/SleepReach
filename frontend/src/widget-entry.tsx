/**
 * Widget Embed Entry Point
 *
 * SleepReach floating launcher that mirrors the TMS/NeuroReach pattern:
 * clicking the CTA opens the dedicated assessment page in a new tab.
 */
import { createRoot } from 'react-dom/client'
import { useEffect, useState } from 'react'

function getApiBaseUrl(): string {
    const scripts = document.querySelectorAll('script[src*="widget-embed"]')
    for (const script of scripts) {
        const src = script.getAttribute('src') || ''
        try {
            const url = new URL(src, window.location.href)
            return `${url.protocol}//${url.host}`
        } catch {
            // Ignore invalid script URLs and keep checking.
        }
    }

    return window.location.origin
}

const API_BASE = getApiBaseUrl()

const STYLES = `
#sleepreach-widget-root,
#sleepreach-widget-root *,
#sleepreach-widget-root *::before,
#sleepreach-widget-root *::after {
    box-sizing: border-box;
}

#sleepreach-widget-root {
    font-family: 'Montserrat', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

.sr-card-widget {
    position: fixed;
    top: 50%;
    right: 0;
    transform: translateY(-50%) translateX(60px);
    z-index: 99;
    width: 230px;
    border-radius: 14px 0 0 14px;
    overflow: hidden;
    border: 1px solid rgba(59, 80, 104, 0.16);
    border-right: none;
    background: rgba(255, 255, 255, 0.98);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    opacity: 0;
    pointer-events: none;
    box-shadow: -3px 4px 12px rgba(15, 23, 42, 0.08), -6px 12px 28px rgba(15, 23, 42, 0.12);
}

.sr-card-widget.sr-card-visible {
    opacity: 1;
    pointer-events: auto;
    animation:
        sr-card-entrance 0.9s cubic-bezier(0.16, 1, 0.3, 1) both,
        sr-card-float 5s ease-in-out 1.2s infinite;
}

@keyframes sr-card-entrance {
    0% { opacity: 0; transform: translateY(-50%) translateX(60px); }
    100% { opacity: 1; transform: translateY(-50%) translateX(0); }
}

@keyframes sr-card-float {
    0%, 100% { transform: translateY(-50%) translateX(0); }
    25% { transform: translateY(calc(-50% - 4px)) translateX(0); }
    50% { transform: translateY(calc(-50% - 7px)) translateX(0); }
    75% { transform: translateY(calc(-50% - 4px)) translateX(0); }
}

.sr-card-inner {
    overflow: hidden;
}

.sr-card-bar-top,
.sr-card-bar-bottom {
    height: 3px;
    background: linear-gradient(90deg, #243448, #38516b, #53708d, #38516b, #243448);
    background-size: 300% 100%;
    animation: sr-wave 6s ease-in-out infinite;
}

@keyframes sr-wave {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}

.sr-card-body {
    padding: 28px 20px 24px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    min-height: 278px;
}

.sr-card-headline {
    margin: 0;
    font-size: 20px;
    font-weight: 700;
    line-height: 1.35;
    letter-spacing: -0.02em;
    text-align: center;
    background: linear-gradient(135deg, #243448 0%, #38516b 50%, #53708d 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.sr-card-cta {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    width: 100%;
    min-height: 50px;
    padding: 14px 16px;
    border: none;
    border-radius: 8px;
    color: #ffffff;
    background: linear-gradient(135deg, #243448 0%, #38516b 100%);
    box-shadow: 0 0 8px rgba(56, 81, 107, 0.18);
    font-family: inherit;
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-align: center;
    text-decoration: none;
    cursor: pointer;
    position: relative;
    overflow: hidden;
    transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.3s cubic-bezier(0.16, 1, 0.3, 1), background 0.3s ease;
    animation: sr-breathe 3s ease-in-out infinite;
}

@keyframes sr-breathe {
    0%, 100% { box-shadow: 0 0 8px rgba(56, 81, 107, 0.18); }
    50% { box-shadow: 0 0 18px rgba(56, 81, 107, 0.32), 0 0 36px rgba(56, 81, 107, 0.08); }
}

.sr-card-cta::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.18), transparent);
    animation: sr-shimmer 4s ease-in-out infinite;
}

@keyframes sr-shimmer {
    0% { left: -100%; }
    50% { left: 100%; }
    100% { left: 100%; }
}

.sr-card-cta:hover {
    background: linear-gradient(135deg, #38516b 0%, #243448 100%);
    box-shadow: 0 4px 16px rgba(56, 81, 107, 0.35);
    transform: translateY(-2px);
    animation: none;
}

.sr-card-cta:hover::before {
    animation: none;
    left: 100%;
}

.sr-card-cta:focus-visible {
    outline: 3px solid #53708d;
    outline-offset: 3px;
}

.sr-card-cta:active {
    transform: translateY(0);
    box-shadow: 0 2px 6px rgba(56, 81, 107, 0.18);
}

.sr-card-cta-arrow {
    display: inline-block;
    font-size: 17px;
    animation: sr-nudge 3s ease-in-out infinite;
}

@keyframes sr-nudge {
    0%, 70%, 100% { transform: translateX(0); }
    80% { transform: translateX(4px); }
    90% { transform: translateX(2px); }
}

.sr-card-trust {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    font-size: 10px;
    line-height: 1.4;
    letter-spacing: 0.02em;
    color: #8c98a8;
}

.sr-card-trust-sep {
    display: none;
}

@media (hover: hover) and (pointer: fine) {
    .sr-card-widget:hover {
        box-shadow: -4px 6px 16px rgba(15, 23, 42, 0.12), -8px 16px 36px rgba(15, 23, 42, 0.14);
    }
}

@media (min-width: 1440px) {
    .sr-card-widget {
        width: 240px;
        right: 0;
    }

    .sr-card-body {
        padding: 32px 22px 28px;
        gap: 22px;
        min-height: 308px;
    }

    .sr-card-headline {
        font-size: 22px;
    }

    .sr-card-cta {
        min-height: 52px;
        padding: 15px 18px;
        font-size: 16px;
    }

    .sr-card-cta-arrow {
        font-size: 18px;
    }

    .sr-card-trust {
        font-size: 11px;
        gap: 5px;
    }
}

@media (min-width: 1025px) and (max-width: 1279px) {
    .sr-card-widget {
        width: 210px;
        right: 0;
    }

    .sr-card-body {
        padding: 24px 18px 22px;
        gap: 18px;
        min-height: 251px;
    }

    .sr-card-headline {
        font-size: 18px;
    }

    .sr-card-cta {
        min-height: 46px;
        padding: 13px 14px;
        font-size: 14px;
        gap: 6px;
    }

    .sr-card-cta-arrow {
        font-size: 16px;
    }

    .sr-card-trust {
        font-size: 9px;
        gap: 3px;
    }
}

@media (min-width: 769px) and (max-width: 1023px) {
    .sr-card-widget {
        top: auto;
        bottom: 28px;
        right: auto;
        left: 0;
        width: 175px;
        border-radius: 0 12px 12px 0;
        border-left: none;
        border-right: 1px solid rgba(59, 80, 104, 0.16);
        transform: translateX(-30px);
        transform-origin: bottom left;
        box-shadow: 2px 3px 10px rgba(15, 23, 42, 0.08), 4px 8px 20px rgba(15, 23, 42, 0.1);
    }

    .sr-card-widget.sr-card-visible {
        animation:
            sr-card-entrance-mobile 0.9s cubic-bezier(0.16, 1, 0.3, 1) both,
            sr-card-float-mobile 5s ease-in-out 1.2s infinite;
    }

    .sr-card-bar-top,
    .sr-card-bar-bottom {
        height: 2px;
    }

    .sr-card-body {
        padding: 26px 14px 22px;
        gap: 18px;
        min-height: 240px;
    }

    .sr-card-headline {
        font-size: 16.5px;
        line-height: 1.3;
    }

    .sr-card-cta {
        min-height: 46px;
        padding: 12px 14px;
        font-size: 13px;
        gap: 5px;
    }

    .sr-card-cta-arrow {
        font-size: 15px;
    }

    .sr-card-trust {
        font-size: 8px;
        gap: 4px;
    }
}

@media (max-width: 768px) {
    .sr-card-widget {
        top: auto;
        bottom: 20px;
        right: auto;
        left: 0;
        width: 160px;
        border-radius: 0 12px 12px 0;
        border-left: none;
        border-right: 1px solid rgba(59, 80, 104, 0.16);
        transform: translateX(-30px);
        transform-origin: bottom left;
        box-shadow: 2px 3px 10px rgba(15, 23, 42, 0.08), 4px 8px 20px rgba(15, 23, 42, 0.1);
    }

    .sr-card-widget.sr-card-visible {
        animation:
            sr-card-entrance-mobile 0.9s cubic-bezier(0.16, 1, 0.3, 1) both,
            sr-card-float-mobile 5s ease-in-out 1.2s infinite;
    }

    .sr-card-bar-top,
    .sr-card-bar-bottom {
        height: 2px;
    }

    .sr-card-body {
        padding: 22px 12px 18px;
        gap: 16px;
        min-height: 216px;
    }

    .sr-card-headline {
        font-size: 15px;
        line-height: 1.3;
    }

    .sr-card-cta {
        min-height: 44px;
        padding: 11px 12px;
        font-size: 12.5px;
        gap: 5px;
    }

    .sr-card-cta-arrow {
        font-size: 14px;
    }

    .sr-card-trust {
        font-size: 7.5px;
        gap: 3px;
    }
}

@media (min-width: 481px) and (max-width: 768px) {
    .sr-card-widget {
        width: 170px;
        bottom: 24px;
    }

    .sr-card-body {
        padding: 24px 14px 20px;
        gap: 18px;
        min-height: 233px;
    }

    .sr-card-headline {
        font-size: 16px;
    }

    .sr-card-cta {
        min-height: 46px;
        padding: 12px 14px;
        font-size: 13px;
    }

    .sr-card-cta-arrow {
        font-size: 15px;
    }

    .sr-card-trust {
        font-size: 8px;
    }
}

@media (max-width: 375px) {
    .sr-card-widget {
        bottom: 14px;
        width: 140px;
        border-radius: 0 10px 10px 0;
    }

    .sr-card-body {
        padding: 18px 10px 14px;
        gap: 14px;
        min-height: 191px;
    }

    .sr-card-headline {
        font-size: 13.5px;
    }

    .sr-card-cta {
        min-height: 42px;
        padding: 10px 10px;
        font-size: 11.5px;
        border-radius: 7px;
    }

    .sr-card-cta-arrow {
        font-size: 13px;
    }

    .sr-card-trust {
        font-size: 7px;
        gap: 2px;
    }
}

@keyframes sr-card-entrance-mobile {
    0% { opacity: 0; transform: translateX(-30px); }
    100% { opacity: 1; transform: translateX(0); }
}

@keyframes sr-card-float-mobile {
    0%, 100% { transform: translateX(0) translateY(0); }
    25% { transform: translateX(0) translateY(-3px); }
    50% { transform: translateX(0) translateY(-5px); }
    75% { transform: translateX(0) translateY(-3px); }
}

@media (prefers-reduced-motion: reduce) {
    .sr-card-widget,
    .sr-card-widget * {
        animation: none !important;
        transition: none !important;
    }

    .sr-card-widget.sr-card-visible {
        opacity: 1;
        pointer-events: auto;
        transform: translateY(-50%) translateX(0) !important;
    }

    .sr-card-cta:hover {
        transform: none;
    }
}

@media (min-width: 769px) and (max-width: 1023px) and (prefers-reduced-motion: reduce) {
    .sr-card-widget.sr-card-visible {
        transform: translateX(0) !important;
    }
}

@media (max-width: 768px) and (prefers-reduced-motion: reduce) {
    .sr-card-widget.sr-card-visible {
        transform: translateX(0) !important;
    }
}
`

function injectWidgetFont(): void {
    if (document.querySelector('link[data-sr-widget-font]')) return

    const font = document.createElement('link')
    font.rel = 'stylesheet'
    font.href = 'https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700&display=swap'
    font.setAttribute('data-sr-widget-font', 'true')
    document.head.appendChild(font)
}

function WidgetApp() {
    const [launcherVisible, setLauncherVisible] = useState(false)
    const assessmentUrl = `${API_BASE}/assessment?utm_source=floating_widget&utm_medium=cta`

    useEffect(() => {
        const timer = window.setTimeout(() => setLauncherVisible(true), 1500)
        return () => window.clearTimeout(timer)
    }, [])

    return (
        <aside
            className={`sr-card-widget${launcherVisible ? ' sr-card-visible' : ''}`}
            role="complementary"
            aria-label="SleepReach assessment widget"
        >
            <div className="sr-card-inner">
                <div className="sr-card-bar-top" />
                <div className="sr-card-body">
                    <h2 className="sr-card-headline">Could sleep therapy help?</h2>
                    <a
                        href={assessmentUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="sr-card-cta"
                        aria-label="Take a free sleep assessment in a new tab"
                    >
                        <span>Take Free Assessment</span>
                        <span className="sr-card-cta-arrow">&rarr;</span>
                    </a>
                    <div className="sr-card-trust" aria-hidden="true">
                        <span>Confidential</span>
                        <span className="sr-card-trust-sep">&middot;</span>
                        <span>HIPAA</span>
                        <span className="sr-card-trust-sep">&middot;</span>
                        <span>256-bit</span>
                    </div>
                </div>
                <div className="sr-card-bar-bottom" />
            </div>
        </aside>
    )
}

function mount() {
    if (document.getElementById('sleepreach-widget-root')) return

    injectWidgetFont()

    const style = document.createElement('style')
    style.setAttribute('data-sr-widget-style', 'true')
    style.textContent = STYLES
    document.head.appendChild(style)

    const container = document.createElement('div')
    container.id = 'sleepreach-widget-root'
    container.className = 'sr-widget-root'
    document.body.appendChild(container)

    ;(window as any).__SLEEPREACH_API_BASE__ = API_BASE

    const root = createRoot(container)
    root.render(<WidgetApp />)
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount)
} else {
    mount()
}
