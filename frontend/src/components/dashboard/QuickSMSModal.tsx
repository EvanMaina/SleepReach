import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, Loader2, MessageSquare, Send, X } from 'lucide-react'

interface QuickSMSModalProps {
    isOpen: boolean
    onClose: () => void
    onSend: (phone: string, message: string) => Promise<void>
    initialPhone?: string
}

const SEGMENT_LENGTH = 160
const MAX_SEGMENTS = 3
const MAX_LENGTH = SEGMENT_LENGTH * MAX_SEGMENTS

export function QuickSMSModal({ isOpen, onClose, onSend, initialPhone = '' }: QuickSMSModalProps) {
    const [recipientPhone, setRecipientPhone] = useState(initialPhone)
    const [message, setMessage] = useState('')
    const [isSending, setIsSending] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const phoneInputRef = useRef<HTMLInputElement>(null)

    useEffect(() => {
        if (!isOpen) return
        setRecipientPhone(initialPhone)
        setMessage('')
        setError(null)
        const timer = window.setTimeout(() => phoneInputRef.current?.focus(), 100)
        return () => window.clearTimeout(timer)
    }, [initialPhone, isOpen])

    useEffect(() => {
        if (!isOpen) return
        const handleKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') onClose()
        }
        window.addEventListener('keydown', handleKeyDown)
        return () => window.removeEventListener('keydown', handleKeyDown)
    }, [isOpen, onClose])

    const characterInfo = useMemo(() => {
        const current = message.length
        const segments = current === 0 ? 0 : Math.ceil(current / SEGMENT_LENGTH)
        return { current, segments }
    }, [message])

    const canSend = recipientPhone.trim().length > 0 && message.trim().length > 0 && message.length <= MAX_LENGTH && !isSending

    const handleSubmit = async (event: FormEvent) => {
        event.preventDefault()
        if (!recipientPhone.trim()) {
            setError('Please enter a recipient phone number.')
            return
        }
        if (!message.trim()) {
            setError('Please enter a message.')
            return
        }
        if (message.length > MAX_LENGTH) {
            setError(`Message too long. Maximum ${MAX_LENGTH} characters.`)
            return
        }

        setIsSending(true)
        setError(null)
        try {
            await onSend(recipientPhone.trim(), message.trim())
            onClose()
        } catch (err: any) {
            setError(err?.response?.data?.detail || err?.message || 'Failed to send SMS.')
        } finally {
            setIsSending(false)
        }
    }

    if (!isOpen) return null

    return (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
            <div
                className="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl"
                onClick={(event) => event.stopPropagation()}
            >
                <div className="flex items-center justify-between border-b border-gray-200 px-6 py-5">
                    <div className="flex items-start gap-3">
                        <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-2xl bg-emerald-100">
                            <MessageSquare size={20} className="text-emerald-700" />
                        </div>
                        <div>
                            <h3 className="text-2xl font-bold text-gray-900">Quick SMS</h3>
                            <p className="text-sm text-gray-500">Send a message to any number</p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="rounded-xl p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                    >
                        <X size={20} />
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="space-y-5 px-6 py-6">
                    {error ? (
                        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                            {error}
                        </div>
                    ) : null}

                    <div>
                        <label className="mb-2 block text-sm font-semibold text-gray-800">Recipient Phone Number</label>
                        <input
                            ref={phoneInputRef}
                            type="tel"
                            value={recipientPhone}
                            onChange={(event) => setRecipientPhone(event.target.value)}
                            placeholder="+1 (555) 123-4567"
                            autoComplete="tel"
                            className="w-full rounded-xl border border-gray-300 px-4 py-3 text-lg placeholder:text-gray-400 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-green-500"
                        />
                        <p className="mt-1.5 text-xs text-gray-500">You can edit this number before sending</p>
                    </div>

                    <div>
                        <div className="mb-2 flex items-center justify-between gap-4">
                            <label className="block text-sm font-semibold text-gray-800">Message</label>
                            <span className="text-xs text-gray-500">
                                {characterInfo.current}/{MAX_LENGTH} chars • {characterInfo.segments} segment{characterInfo.segments === 1 ? '' : 's'}
                            </span>
                        </div>
                        <textarea
                            value={message}
                            onChange={(event) => setMessage(event.target.value)}
                            rows={6}
                            placeholder="Type your message..."
                            className="w-full resize-none rounded-xl border border-gray-300 px-4 py-3 text-base placeholder:text-gray-400 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-green-500"
                        />
                        <div className="mt-3 h-1.5 w-full rounded-full bg-gray-100">
                            <div
                                className="h-1.5 rounded-full bg-emerald-500 transition-all"
                                style={{ width: `${Math.min((message.length / MAX_LENGTH) * 100, 100)}%` }}
                            />
                        </div>
                    </div>

                    <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                        <AlertTriangle size={18} className="mt-0.5 shrink-0" />
                        <p>Only send SMS to leads who have provided SMS consent. Ensure compliance with TCPA regulations.</p>
                    </div>

                    <div className="flex items-center justify-between border-t border-gray-100 pt-4">
                        <span className="text-sm font-medium text-gray-500">Quick SMS</span>
                        <div className="flex items-center gap-3">
                            <button
                                type="button"
                                onClick={onClose}
                                className="rounded-xl border border-gray-300 bg-white px-5 py-2.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
                            >
                                Cancel
                            </button>
                            <button
                                type="submit"
                                disabled={!canSend}
                                className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                                {isSending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                                Send SMS
                            </button>
                        </div>
                    </div>
                </form>
            </div>
        </div>
    )
}

export default QuickSMSModal
