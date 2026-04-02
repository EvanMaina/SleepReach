import { useState } from 'react'
import { Eye, EyeOff, Lock, Shield, Server, ChevronRight } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'

export default function LoginPage() {
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [showPassword, setShowPassword] = useState(false)
    const [isLoading, setIsLoading] = useState(false)
    const { login } = useAuth()

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!email.trim()) {
            toast.error('Please enter your email address')
            return
        }
        if (!password) {
            toast.error('Please enter your password')
            return
        }

        setIsLoading(true)
        try {
            await login(email, password)
            toast.success('Welcome back!')
        } catch (err: any) {
            const msg = err.response?.data?.detail || 'Invalid credentials'
            toast.error(msg)
        } finally {
            setIsLoading(false)
        }
    }

    return (
        <div className="min-h-screen flex">
            {/* ─── Left Panel: Rich Slate-Blue, Calming & Premium ─── */}
            <div
                className="hidden lg:flex lg:w-1/2 relative overflow-hidden flex-col"
                style={{
                    background: 'radial-gradient(ellipse at 50% 35%, #3B5068 0%, #2C3E5A 40%, #1E2D3D 100%)',
                }}
            >
                {/* Soft atmospheric glow — adds depth without patterns */}
                <div className="absolute top-[20%] left-[50%] -translate-x-1/2 w-[600px] h-[400px] rounded-full pointer-events-none" style={{ background: 'radial-gradient(circle, rgba(100,150,190,0.12) 0%, transparent 70%)' }} />
                <div className="absolute bottom-[10%] left-[30%] w-[300px] h-[300px] rounded-full pointer-events-none" style={{ background: 'radial-gradient(circle, rgba(80,120,160,0.08) 0%, transparent 70%)' }} />

                {/* SR Badge — warm gold accent */}
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

                {/* ─── Centered Content: Logo + Text ─── */}
                <div className="relative z-10 flex-1 flex flex-col items-center justify-center px-10 xl:px-14 min-h-0 pb-4 -mt-2">
                    {/* Logo in frosted-glass card for contrast */}
                    <div className="mb-6 shrink-0 rounded-2xl p-6 xl:p-8" style={{ background: 'rgba(255,255,255,0.07)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', border: '1px solid rgba(255,255,255,0.12)' }}>
                        <img
                            src="/images/sleep-logo.png"
                            alt="The Insomnia and Sleep Institute of Arizona"
                            className="w-[130px] h-auto xl:w-[160px] object-contain"
                            style={{ filter: 'brightness(0) invert(1) opacity(0.92)' }}
                        />
                    </div>

                    {/* Headline — pure white */}
                    <h1 className="text-[1.85rem] xl:text-[2.25rem] font-bold text-white leading-[1.15] mb-3 tracking-tight text-center">
                        Transform your<br />
                        clinic&apos;s patient<br />
                        outreach
                    </h1>

                    {/* Subtext — light white */}
                    <p className="text-[13px] xl:text-[15px] leading-relaxed max-w-[380px] text-center mb-0" style={{ color: 'rgba(255,255,255,0.75)' }}>
                        Streamline lead capture, automated scoring, and patient engagement &mdash; all in one HIPAA-compliant platform built for sleep therapy clinics.
                    </p>
                </div>

                {/* ─── Bottom Section: Frosted Glass Feature Cards + Copyright ─── */}
                <div className="relative z-10 px-10 xl:px-14 pb-5 pt-3 shrink-0">
                    {/* Feature Cards — frosted glass */}
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

                    {/* Copyright */}
                    <p className="text-xs text-center" style={{ color: 'rgba(255,255,255,0.4)' }}>
                        &copy; 2026 The Insomnia and Sleep Institute of Arizona. All rights reserved.
                    </p>
                </div>
            </div>

            {/* ─── Right Panel: Login Form ─── */}
            <div className="flex-1 flex items-center justify-center p-6 sm:p-10 bg-gray-50/80">
                <div className="w-full max-w-[440px] animate-fade-in">
                    {/* Mobile brand header */}
                    <div className="flex items-center gap-3 mb-10 lg:hidden">
                        <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: '#2C3E5A' }}>
                            <span className="text-white font-bold text-sm">SR</span>
                        </div>
                        <div>
                            <span className="text-lg font-bold text-gray-900 tracking-tight">SleepReach</span>
                            <span className="block text-xs text-gray-400 uppercase tracking-wider">AI Platform</span>
                        </div>
                    </div>

                    {/* Form header */}
                    <div className="mb-8">
                        <h2 className="text-[1.75rem] font-bold text-gray-900 mb-2 tracking-tight">Welcome back</h2>
                        <p className="text-gray-500 text-[15px]">Sign in to your clinic dashboard</p>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-5">
                        {/* Email */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Email address
                            </label>
                            <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="input-premium"
                                placeholder="you@clinic.com"
                                autoComplete="email"
                                required
                            />
                        </div>

                        {/* Password */}
                        <div>
                            <div className="flex items-center justify-between mb-2">
                                <label className="block text-sm font-medium text-gray-700">
                                    Password
                                </label>
                                <button
                                    type="button"
                                    onClick={() => {
                                        window.location.hash = 'forgot-password'
                                    }}
                                    className="text-xs font-medium transition-colors"
                                    style={{ color: '#2C3E5A' }}
                                >
                                    Forgot password?
                                </button>
                            </div>
                            <div className="relative">
                                <input
                                    type={showPassword ? 'text' : 'password'}
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="input-premium pr-12"
                                    placeholder="Enter your password"
                                    autoComplete="current-password"
                                    required
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPassword(!showPassword)}
                                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors p-0.5"
                                >
                                    {showPassword ? <EyeOff className="w-[18px] h-[18px]" /> : <Eye className="w-[18px] h-[18px]" />}
                                </button>
                            </div>
                        </div>

                        {/* Submit — slate-blue matching left panel */}
                        <button
                            type="submit"
                            disabled={isLoading}
                            className="w-full h-12 rounded-xl font-semibold text-[15px] text-white transition-all duration-200 ease-out shadow-md hover:shadow-lg hover:brightness-110 active:scale-[0.99] disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2.5"
                            style={{
                                background: 'linear-gradient(135deg, #243448 0%, #2C3E5A 50%, #3B5068 100%)',
                            }}
                        >
                            {isLoading ? (
                                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            ) : (
                                <>
                                    <Lock className="w-4 h-4" />
                                    Sign In Securely
                                    <ChevronRight className="w-4 h-4 ml-0.5" />
                                </>
                            )}
                        </button>
                    </form>

                    {/* Footer */}
                    <p className="mt-8 text-center text-sm text-gray-400">
                        Need access?{' '}
                        <button
                            type="button"
                            onClick={() => {
                                window.location.hash = 'request-invitation'
                            }}
                            className="font-semibold transition-colors"
                            style={{ color: '#2C3E5A' }}
                        >
                            Request an invitation
                        </button>
                    </p>

                    {/* Trust indicators */}
                    <div className="mt-10 pt-6 border-t border-gray-200/60">
                        <div className="flex items-center justify-center gap-6" style={{ color: '#6B7280' }}>
                            <div className="flex items-center gap-1.5 text-xs">
                                <Shield className="w-3.5 h-3.5" />
                                <span>HIPAA</span>
                            </div>
                            <div className="w-1 h-1 rounded-full bg-gray-300" />
                            <div className="flex items-center gap-1.5 text-xs">
                                <Lock className="w-3.5 h-3.5" />
                                <span>256-bit SSL</span>
                            </div>
                            <div className="w-1 h-1 rounded-full bg-gray-300" />
                            <div className="flex items-center gap-1.5 text-xs">
                                <Server className="w-3.5 h-3.5" />
                                <span>SOC 2</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}
