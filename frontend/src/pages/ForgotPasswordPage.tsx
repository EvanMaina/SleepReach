import { FormEvent, useState } from 'react'
import { ArrowLeft, CheckCircle2, Lock, Mail, Server, Shield } from 'lucide-react'
import { authAPI } from '../lib/api'

function BackToLogin() {
    return (
        <button
            type="button"
            onClick={() => {
                window.location.hash = ''
            }}
            className="inline-flex items-center gap-2 text-sm font-medium text-sleep-700 transition-colors hover:text-sleep-900"
        >
            <ArrowLeft size={16} />
            Back to Login
        </button>
    )
}

function BrandPanel({
    title,
    description,
}: {
    title: string
    description: string
}) {
    return (
        <div
            className="hidden lg:flex lg:w-1/2 relative overflow-hidden flex-col"
            style={{
                background: 'radial-gradient(ellipse at 50% 35%, #3B5068 0%, #2C3E5A 40%, #1E2D3D 100%)',
            }}
        >
            <div className="absolute top-[20%] left-[50%] -translate-x-1/2 w-[600px] h-[400px] rounded-full pointer-events-none" style={{ background: 'radial-gradient(circle, rgba(100,150,190,0.12) 0%, transparent 70%)' }} />
            <div className="absolute bottom-[10%] left-[30%] w-[300px] h-[300px] rounded-full pointer-events-none" style={{ background: 'radial-gradient(circle, rgba(80,120,160,0.08) 0%, transparent 70%)' }} />

            <div className="relative z-10 px-10 xl:px-14 pt-5 shrink-0">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #C4A253, #D4A853)', boxShadow: '0 2px 8px rgba(196,162,83,0.3)' }}>
                        <span className="text-white font-bold text-sm tracking-tight">SR</span>
                    </div>
                    <div>
                        <span className="text-white font-semibold text-lg tracking-tight">SleepReach</span>
                        <span className="block text-white/50 text-[11px] uppercase tracking-[0.15em] font-medium">AI Platform</span>
                    </div>
                </div>
            </div>

            <div className="relative z-10 flex-1 flex flex-col items-center justify-center px-10 xl:px-14 min-h-0 pb-4 -mt-2">
                <div className="mb-6 shrink-0 rounded-2xl p-6 xl:p-8" style={{ background: 'rgba(255,255,255,0.07)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', border: '1px solid rgba(255,255,255,0.12)' }}>
                    <img
                        src="/images/sleep-logo.png"
                        alt="The Insomnia and Sleep Institute of Arizona"
                        className="w-[130px] h-auto xl:w-[160px] object-contain"
                        style={{ filter: 'brightness(0) invert(1) opacity(0.92)' }}
                    />
                </div>

                <h1 className="text-[1.85rem] xl:text-[2.25rem] font-bold text-white leading-[1.15] mb-3 tracking-tight text-center">
                    {title}
                </h1>

                <p className="text-[13px] xl:text-[15px] leading-relaxed max-w-[380px] text-center mb-0" style={{ color: 'rgba(255,255,255,0.75)' }}>
                    {description}
                </p>
            </div>

            <div className="relative z-10 px-10 xl:px-14 pb-5 pt-3 shrink-0">
                <div className="flex items-stretch justify-center gap-3 mb-4">
                    {[
                        { Icon: Shield, label: 'HIPAA Compliant', sub: 'Full compliance' },
                        { Icon: Lock, label: '256-bit Encryption', sub: 'End-to-end security' },
                        { Icon: Server, label: '99.9% Uptime', sub: 'Enterprise grade' },
                    ].map((feat) => (
                        <div
                            key={feat.label}
                            className="rounded-xl px-4 py-3 transition-all duration-300 flex-1 max-w-[170px]"
                            style={{
                                background: 'rgba(255,255,255,0.08)',
                                backdropFilter: 'blur(8px)',
                                WebkitBackdropFilter: 'blur(8px)',
                                border: '1px solid rgba(255,255,255,0.12)',
                            }}
                        >
                            <feat.Icon className="w-4 h-4 mb-2" style={{ color: '#D4A853' }} />
                            <p className="text-[12px] font-semibold leading-tight mb-0.5 text-white/90">{feat.label}</p>
                            <p className="text-[10px] text-white/50">{feat.sub}</p>
                        </div>
                    ))}
                </div>

                <p className="text-xs text-center" style={{ color: 'rgba(255,255,255,0.4)' }}>
                    &copy; 2026 The Insomnia and Sleep Institute of Arizona. All rights reserved.
                </p>
            </div>
        </div>
    )
}

export default function ForgotPasswordPage() {
    const [email, setEmail] = useState('')
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [isSubmitted, setIsSubmitted] = useState(false)
    const [message, setMessage] = useState('')
    const [error, setError] = useState('')

    const handleSubmit = async (event: FormEvent) => {
        event.preventDefault()
        setIsSubmitting(true)
        setError('')
        try {
            const response = await authAPI.forgotPassword(email.trim())
            setMessage(response.data?.message || "If an account exists with this email, you'll receive a reset link.")
            setIsSubmitted(true)
        } catch (err: any) {
            setError(err?.response?.data?.detail || 'Unable to send reset email right now.')
        } finally {
            setIsSubmitting(false)
        }
    }

    return (
        <div className="min-h-screen flex">
            <BrandPanel
                title="Reset your password"
                description="We’ll send a secure reset link to your inbox so you can regain access without calling support."
            />

            <div className="flex-1 flex items-center justify-center p-6 sm:p-10 bg-gray-50/80">
                <div className="w-full max-w-[440px] animate-fade-in">
                    <div className="mb-8">
                        <h2 className="text-[1.75rem] font-bold text-gray-900 mb-2 tracking-tight">Forgot your password?</h2>
                        <p className="text-gray-500 text-[15px]">Enter your email and we’ll send you a secure reset link.</p>
                    </div>

                    {isSubmitted ? (
                        <div className="rounded-3xl border border-emerald-200 bg-white p-8 shadow-sm">
                            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-600">
                                <CheckCircle2 size={28} />
                            </div>
                            <h3 className="mt-5 text-xl font-bold text-gray-900">Check your email</h3>
                            <p className="mt-2 text-sm leading-6 text-gray-500">{message}</p>
                            <p className="mt-5 text-xs text-gray-400">If you don’t see it within a minute, check your spam folder and try again.</p>
                            <div className="mt-6">
                                <BackToLogin />
                            </div>
                        </div>
                    ) : (
                        <form onSubmit={handleSubmit} className="rounded-3xl border border-gray-200 bg-white p-8 shadow-sm space-y-5">
                            {error ? (
                                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                                    {error}
                                </div>
                            ) : null}

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">Email address</label>
                                <input
                                    type="email"
                                    value={email}
                                    onChange={(event) => setEmail(event.target.value)}
                                    className="input-premium"
                                    placeholder="you@clinic.com"
                                    autoComplete="email"
                                    required
                                />
                            </div>

                            <button
                                type="submit"
                                disabled={isSubmitting || !email.trim()}
                                className="w-full h-12 rounded-xl font-semibold text-[15px] text-white transition-all duration-200 ease-out shadow-md hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2.5"
                                style={{
                                    background: 'linear-gradient(135deg, #243448 0%, #2C3E5A 50%, #3B5068 100%)',
                                }}
                            >
                                {isSubmitting ? 'Sending reset link...' : 'Send Reset Link'}
                            </button>

                            <BackToLogin />
                        </form>
                    )}
                </div>
            </div>
        </div>
    )
}
