import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { Phone, PhoneCall, X } from 'lucide-react'

interface PhoneDialModalProps {
    isOpen: boolean
    onClose: () => void
    onCall: (phone: string) => void
}

export function PhoneDialModal({ isOpen, onClose, onCall }: PhoneDialModalProps) {
    const [phoneNumber, setPhoneNumber] = useState('')
    const inputRef = useRef<HTMLInputElement>(null)

    useEffect(() => {
        if (!isOpen) return
        setPhoneNumber('')
        const timer = window.setTimeout(() => inputRef.current?.focus(), 100)
        return () => window.clearTimeout(timer)
    }, [isOpen])

    useEffect(() => {
        if (!isOpen) return
        const handleKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') onClose()
        }
        window.addEventListener('keydown', handleKeyDown)
        return () => window.removeEventListener('keydown', handleKeyDown)
    }, [isOpen, onClose])

    const handleSubmit = useCallback((event: FormEvent) => {
        event.preventDefault()
        const trimmed = phoneNumber.trim()
        if (!trimmed) return
        onCall(trimmed)
        onClose()
    }, [onCall, onClose, phoneNumber])

    if (!isOpen) return null

    return (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
            <div
                className="w-full max-w-sm overflow-hidden rounded-2xl bg-white shadow-2xl"
                onClick={(event) => event.stopPropagation()}
            >
                <div className="flex items-center justify-between border-b border-green-100 bg-gradient-to-r from-green-50 to-emerald-50 px-6 py-4">
                    <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-green-100">
                            <PhoneCall size={20} className="text-green-600" />
                        </div>
                        <div>
                            <h3 className="font-semibold text-gray-900">Quick Call via 3CX</h3>
                            <p className="text-xs text-gray-500">Enter a phone number to dial</p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                    >
                        <X size={18} />
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="px-6 py-5">
                    <div className="relative">
                        <Phone size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                        <input
                            ref={inputRef}
                            type="tel"
                            value={phoneNumber}
                            onChange={(event) => setPhoneNumber(event.target.value)}
                            placeholder="+1 (555) 000-0000"
                            autoComplete="tel"
                            className="w-full rounded-xl border border-gray-300 py-3 pl-10 pr-4 text-lg placeholder:text-gray-400 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-green-500"
                        />
                    </div>

                    <p className="mt-2 text-xs text-gray-400">
                        3CX Chrome extension will handle the call automatically.
                    </p>

                    <div className="mt-5 flex items-center gap-3">
                        <button
                            type="button"
                            onClick={onClose}
                            className="flex-1 rounded-xl bg-gray-100 px-4 py-2.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-200"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={!phoneNumber.trim()}
                            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-green-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            <PhoneCall size={16} />
                            Call Now
                        </button>
                    </div>
                </form>
            </div>
        </div>
    )
}

export default PhoneDialModal
