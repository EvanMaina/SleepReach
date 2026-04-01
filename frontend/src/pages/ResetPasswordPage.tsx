import { FormEvent, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ArrowLeft, Check, CheckCircle2, Eye, EyeOff, Lock, Server, Shield, X } from 'lucide-react'
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

function extractResetToken() {
    const hash = window.location.hash || ''
    const query = hash.split('?')[1] || ''
    const params = new URLSearchParams(query)
    return params.get('token') || ''
}

export default function ResetPasswordPage() {
    const [token, setToken] = useState('')
    const [isValidating, setIsValidating] = useState(true)
    const [isTokenValid, setIsTokenValid] = useState<boolean | null>(null)
    const [tokenMessage, setTokenMessage] = useState('')
    const [newPassword, setNewPassword] = useState('')
    const [confirmPassword, setConfirmPassword] = useState('')
    const [showNewPassword, setShowNewPassword] = useState(false)
    const [showConfirmPassword, setShowConfirmPassword] = useState(false)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [error, setError] = useState('')
    const [successMessage, setSuccessMessage] = useState('')

    useEffect(() => {
        const currentToken = extractResetToken()
        setToken(currentToken)
        if (!currentToken) {
            setIsTokenValid(false)
            setTokenMessage('No reset token was found in this link.')
            setIsValidating(false)
            return
        }

        authAPI
            .validateResetToken(currentToken)
            .then((response) => {
                setIsTokenValid(Boolean(response.data?.valid))
                setTokenMessage(response.data?.message || '')
            })
            .catch((err: any) => {
                setIsTokenValid(false)
                setTokenMessage(err?.response?.data?.detail || 'Unable to validate this reset link.')
            })
            .finally(() => {
                setIsValidating(false)
            })
    }, [])

    const rules = useMemo(
        () => ({
            minLength: newPassword.length >= 8,
            uppercase: /[A-Z]/.test(newPassword),
            lowercase: /[a-z]/.test(newPassword),
            number: /\d/.test(newPassword),
            special: /[^A-Za-z0-9]/.test(newPassword),
            matches: newPassword.length > 0 && newPassword === confirmPassword,
        }),
        [confirmPassword, newPassword],
    )

    const canSubmit =
        Boolean(isTokenValid) &&
        rules.minLength &&
        rules.uppercase &&
        rules.lowercase &&
        rules.number &&
        rules.special &&
        rules.matches &&
        !isSubmitting

    const handleSubmit = async (event: FormEvent) => {
        event.preventDefault()
        if (!canSubmit) return
        setIsSubmitting(true)
        setError('')
        try {
            const response = await authAPI.resetPassword(token, newPassword)
            setSuccessMessage(response.data?.message || 'Your password has been reset successfully.')
        } catch (err: any) {
            setError(err?.response?.data?.detail || 'Unable to reset your password.')
        } finally {
            setIsSubmitting(false)
        }
    }

    if (isValidating) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gray-50">
                <div className="text-center">
                    <div className="mx-auto mb-4 h-12 w-12 rounded-2xl border-4 border-sleep-300 border-t-sleep-700 animate-spin" />
                    <p className="text-sm text-gray-500">Validating your reset link...</p>
                </div>
            </div>
        )
    }

    return (
        <div className="min-h-screen flex">
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
                        Set a new password
                    </h1>

                    <p className="text-[13px] xl:text-[15px] leading-relaxed max-w-[380px] text-center mb-0" style={{ color: 'rgba(255,255,255,0.75)' }}>
                        Choose a strong password to secure your SleepReach account.
                    </p>
                </div>

                <div className="relative z-10 px-10 xl:px-14 pb-5 pt-3 shrink-0">
                    <div className="flex items-stretch justify-center gap-3 mb-4">
                        {[
                            { Icon: Shield, label: 'HIPAA Compliant', sub: 'Protected workflows' },
                            { Icon: Lock, label: 'Strong Passwords', sub: 'Secure by default' },
                            { Icon: Server, label: 'Trusted Platform', sub: 'Enterprise grade' },
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

            <div className="flex-1 flex items-center justify-center p-6 sm:p-10 bg-gray-50/80">
                <div className="w-full max-w-[460px] animate-fade-in">
                    {!isTokenValid ? (
                        <div className="rounded-3xl border border-red-200 bg-white p-8 shadow-sm">
                            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-red-50 text-red-600">
                                <AlertTriangle size={28} />
                            </div>
                            <h2 className="mt-5 text-[1.75rem] font-bold text-gray-900 tracking-tight">Invalid reset link</h2>
                            <p className="mt-2 text-sm leading-6 text-gray-500">{tokenMessage || 'This reset link is invalid or has expired.'}</p>
                            <div className="mt-6 flex flex-wrap gap-3">
                                <button
                                    type="button"
                                    onClick={() => {
                                        window.location.hash = 'forgot-password'
                                    }}
                                    className="rounded-xl bg-sleep-700 px-4 py-2.5 text-sm font-semibold text-white"
                                >
                                    Request New Link
                                </button>
                                <BackToLogin />
                            </div>
                        </div>
                    ) : successMessage ? (
                        <div className="rounded-3xl border border-emerald-200 bg-white p-8 shadow-sm">
                            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-600">
                                <CheckCircle2 size={28} />
                            </div>
                            <h2 className="mt-5 text-[1.75rem] font-bold text-gray-900 tracking-tight">Password reset complete</h2>
                            <p className="mt-2 text-sm leading-6 text-gray-500">{successMessage}</p>
                            <div className="mt-6">
                                <BackToLogin />
                            </div>
                        </div>
                    ) : (
                        <form onSubmit={handleSubmit} className="rounded-3xl border border-gray-200 bg-white p-8 shadow-sm space-y-5">
                            <div>
                                <h2 className="text-[1.75rem] font-bold text-gray-900 tracking-tight">Set your new password</h2>
                                <p className="mt-2 text-sm text-gray-500">{tokenMessage}</p>
                            </div>

                            {error ? (
                                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                                    {error}
                                </div>
                            ) : null}

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">New password</label>
                                <div className="relative">
                                    <input
                                        type={showNewPassword ? 'text' : 'password'}
                                        value={newPassword}
                                        onChange={(event) => setNewPassword(event.target.value)}
                                        className="input-premium pr-12"
                                        placeholder="At least 8 characters"
                                        required
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowNewPassword((prev) => !prev)}
                                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 transition-colors hover:text-gray-600"
                                    >
                                        {showNewPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                                    </button>
                                </div>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">Confirm password</label>
                                <div className="relative">
                                    <input
                                        type={showConfirmPassword ? 'text' : 'password'}
                                        value={confirmPassword}
                                        onChange={(event) => setConfirmPassword(event.target.value)}
                                        className="input-premium pr-12"
                                        placeholder="Re-enter your password"
                                        required
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowConfirmPassword((prev) => !prev)}
                                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 transition-colors hover:text-gray-600"
                                    >
                                        {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                                    </button>
                                </div>
                            </div>

                            <div className="rounded-2xl border border-gray-200 bg-gray-50 px-4 py-4">
                                <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">Password requirements</p>
                                <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2">
                                    {[
                                        { met: rules.minLength, label: '8+ characters' },
                                        { met: rules.uppercase, label: 'Uppercase letter' },
                                        { met: rules.lowercase, label: 'Lowercase letter' },
                                        { met: rules.number, label: 'Number' },
                                        { met: rules.special, label: 'Special character' },
                                        { met: rules.matches, label: 'Passwords match' },
                                    ].map((rule) => (
                                        <div key={rule.label} className="flex items-center gap-2 text-xs">
                                            {rule.met ? <Check size={14} className="text-emerald-600" /> : <X size={14} className="text-gray-300" />}
                                            <span className={rule.met ? 'font-medium text-emerald-700' : 'text-gray-400'}>{rule.label}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <button
                                type="submit"
                                disabled={!canSubmit}
                                className="w-full h-12 rounded-xl font-semibold text-[15px] text-white transition-all duration-200 ease-out shadow-md hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2.5"
                                style={{
                                    background: 'linear-gradient(135deg, #243448 0%, #2C3E5A 50%, #3B5068 100%)',
                                }}
                            >
                                {isSubmitting ? 'Resetting password...' : 'Reset Password'}
                            </button>

                            <BackToLogin />
                        </form>
                    )}
                </div>
            </div>
        </div>
    )
}
