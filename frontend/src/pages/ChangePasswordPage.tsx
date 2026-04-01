import { useState } from 'react'
import { Moon, Lock, ArrowRight } from 'lucide-react'
import { authAPI } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'

export default function ChangePasswordPage() {
    const [newPassword, setNewPassword] = useState('')
    const [confirmPassword, setConfirmPassword] = useState('')
    const [isLoading, setIsLoading] = useState(false)
    const { refreshUser } = useAuth()

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        if (newPassword !== confirmPassword) {
            toast.error('Passwords do not match')
            return
        }
        if (newPassword.length < 8) {
            toast.error('Password must be at least 8 characters')
            return
        }

        setIsLoading(true)
        try {
            await authAPI.changePassword(null, newPassword)
            toast.success('Password updated successfully!')
            await refreshUser()
            // AuthGate handles navigation automatically via must_change_password state change
        } catch (err: any) {
            const msg = err.response?.data?.detail || 'Failed to change password'
            toast.error(msg)
        } finally {
            setIsLoading(false)
        }
    }

    return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
            <div className="w-full max-w-[420px]">
                <div className="flex items-center gap-3 mb-8">
                    <div className="w-10 h-10 rounded-xl bg-sleep-900 flex items-center justify-center">
                        <Moon className="w-5 h-5 text-sleep-200" />
                    </div>
                    <span className="text-lg font-bold text-gray-900">SleepReach</span>
                </div>

                <div className="card-premium p-8">
                    <div className="flex items-center gap-3 mb-6">
                        <div className="w-10 h-10 rounded-xl bg-amber-50 border border-amber-100 flex items-center justify-center">
                            <Lock className="w-5 h-5 text-amber-600" />
                        </div>
                        <div>
                            <h2 className="text-lg font-semibold text-gray-900">Set New Password</h2>
                            <p className="text-sm text-gray-500">You must change your password before continuing.</p>
                        </div>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1.5">New Password</label>
                            <input
                                type="password"
                                value={newPassword}
                                onChange={(e) => setNewPassword(e.target.value)}
                                className="input-premium"
                                placeholder="Min 8 characters, upper + lower + number + symbol"
                                required
                                minLength={8}
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1.5">Confirm Password</label>
                            <input
                                type="password"
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                className="input-premium"
                                placeholder="Re-enter your new password"
                                required
                            />
                        </div>
                        <button
                            type="submit"
                            disabled={isLoading || !newPassword || !confirmPassword}
                            className="w-full btn-primary h-11 disabled:opacity-50"
                        >
                            {isLoading ? (
                                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            ) : (
                                <>
                                    Update Password
                                    <ArrowRight className="w-4 h-4" />
                                </>
                            )}
                        </button>
                    </form>
                </div>
            </div>
        </div>
    )
}
