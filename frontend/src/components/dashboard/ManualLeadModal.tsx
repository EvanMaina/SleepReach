import { type FormEvent, useMemo, useRef, useState } from 'react'
import { AlertCircle, CheckCircle2, Loader2, Paperclip, Plus, Trash2, Upload, UserPlus, X } from 'lucide-react'
import { leadsAPI } from '../../lib/api'
import { formatFileSize, notifyAttachmentsChanged, uploadAttachment } from '../../services/attachments'

interface ManualLeadModalProps {
    isOpen: boolean
    onClose: () => void
    onSuccess: (leadNumber: string) => void
}

const CONDITION_OPTIONS = [
    { value: '', label: 'Select condition...' },
    { value: 'INSOMNIA', label: 'Insomnia' },
    { value: 'SLEEP_APNEA', label: 'Sleep Apnea' },
    { value: 'RESTLESS_LEG', label: 'Restless Legs' },
    { value: 'NARCOLEPSY', label: 'Narcolepsy' },
    { value: 'OTHER', label: 'Other' },
]

const URGENCY_OPTIONS = [
    { value: '', label: 'Select urgency...' },
    { value: 'ASAP', label: 'Urgent - needs immediate attention' },
    { value: 'WITHIN_30_DAYS', label: 'Soon - within 30 days' },
    { value: 'EXPLORING', label: 'Exploring - just researching' },
]

const MAX_FILE_SIZE = 25 * 1024 * 1024
const ACCEPTED_TYPES = [
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'image/bmp',
    'image/tiff',
]

function fileTypeLabel(type: string): string {
    if (type.startsWith('image/')) return 'Image'
    if (type.includes('pdf')) return 'PDF'
    if (type.includes('excel') || type.includes('sheet')) return 'Spreadsheet'
    if (type.includes('word')) return 'Document'
    return 'File'
}

type ManualLeadField =
    | 'first_name'
    | 'email'
    | 'phone'
    | 'zip_code'
    | 'condition_other'
    | 'insurance_provider'
    | 'provider_name'

function validateEmail(value: string): string | null {
    if (!value.trim()) return null
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    return emailRegex.test(value.trim()) ? null : 'Please enter a valid email address'
}

function validatePhone(value: string): string | null {
    if (!value.trim()) return null
    const digits = value.replace(/\D/g, '')
    return digits.length >= 10 ? null : 'Please enter a valid phone number'
}

function validateZip(value: string): string | null {
    if (!value.trim()) return null
    return /^\d{5}$/.test(value.trim()) ? null : 'Please enter a valid 5-digit ZIP code'
}

function resolveServerFieldErrors(detail: unknown): Partial<Record<ManualLeadField, string>> {
    if (Array.isArray(detail)) {
        const next: Partial<Record<ManualLeadField, string>> = {}
        detail.forEach((item) => {
            const path = Array.isArray(item?.loc) ? item.loc.join('.') : ''
            const message = typeof item?.msg === 'string' ? item.msg : 'Invalid value'
            if (path.includes('first_name')) next.first_name = message
            if (path.includes('email')) next.email = message
            if (path.includes('phone')) next.phone = message
            if (path.includes('zip_code')) next.zip_code = message
            if (path.includes('condition_other')) next.condition_other = message
            if (path.includes('insurance_provider')) next.insurance_provider = message
            if (path.includes('referring_provider_name')) next.provider_name = message
        })
        return next
    }

    if (typeof detail === 'string') {
        const message = detail.trim()
        const lowered = message.toLowerCase()
        if (lowered.includes('email')) return { email: message }
        if (lowered.includes('phone')) return { phone: message }
        if (lowered.includes('zip')) return { zip_code: message }
        if (lowered.includes('provider')) return { provider_name: message }
    }

    return {}
}

export function ManualLeadModal({ isOpen, onClose, onSuccess }: ManualLeadModalProps) {
    const fileInputRef = useRef<HTMLInputElement>(null)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [isDragOver, setIsDragOver] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [success, setSuccess] = useState<string | null>(null)
    const [firstName, setFirstName] = useState('')
    const [lastName, setLastName] = useState('')
    const [email, setEmail] = useState('')
    const [phone, setPhone] = useState('')
    const [condition, setCondition] = useState('')
    const [conditionOther, setConditionOther] = useState('')
    const [urgency, setUrgency] = useState('')
    const [hasInsurance, setHasInsurance] = useState<boolean | undefined>(undefined)
    const [insuranceProvider, setInsuranceProvider] = useState('')
    const [zipCode, setZipCode] = useState('')
    const [notes, setNotes] = useState('')
    const [isReferral, setIsReferral] = useState(false)
    const [providerName, setProviderName] = useState('')
    const [providerContact, setProviderContact] = useState('')
    const [providerSpecialty, setProviderSpecialty] = useState('')
    const [files, setFiles] = useState<File[]>([])
    const [fieldErrors, setFieldErrors] = useState<Partial<Record<ManualLeadField, string>>>({})

    const canSubmit = useMemo(() => firstName.trim().length > 0 && !isSubmitting, [firstName, isSubmitting])

    const resetForm = () => {
        setError(null)
        setSuccess(null)
        setFirstName('')
        setLastName('')
        setEmail('')
        setPhone('')
        setCondition('')
        setConditionOther('')
        setUrgency('')
        setHasInsurance(undefined)
        setInsuranceProvider('')
        setZipCode('')
        setNotes('')
        setIsReferral(false)
        setProviderName('')
        setProviderContact('')
        setProviderSpecialty('')
        setFiles([])
        setFieldErrors({})
    }

    const handleClose = () => {
        if (isSubmitting) return
        resetForm()
        onClose()
    }

    const addFiles = (incoming: FileList | File[]) => {
        const next: File[] = []
        const errors: string[] = []

        Array.from(incoming).forEach((file) => {
            if (file.size > MAX_FILE_SIZE) {
                errors.push(`"${file.name}" exceeds 25MB (${formatFileSize(file.size)}).`)
                return
            }
            if (!ACCEPTED_TYPES.includes(file.type)) {
                errors.push(`"${file.name}" is not a supported file type.`)
                return
            }
            if (files.some((existing) => existing.name === file.name && existing.size === file.size)) {
                return
            }
            next.push(file)
        })

        if (errors.length > 0) setError(errors[0])
        if (next.length > 0) setFiles((prev) => [...prev, ...next])
    }

    const clearFieldError = (field: ManualLeadField) => {
        setFieldErrors((prev) => {
            if (!prev[field]) return prev
            const next = { ...prev }
            delete next[field]
            return next
        })
    }

    const handleSubmit = async (event: FormEvent) => {
        event.preventDefault()
        if (!canSubmit) return

        setIsSubmitting(true)
        setError(null)
        setFieldErrors({})

        const nextFieldErrors: Partial<Record<ManualLeadField, string>> = {}
        if (!firstName.trim()) nextFieldErrors.first_name = 'First name is required'
        const emailError = validateEmail(email)
        if (emailError) nextFieldErrors.email = emailError
        const phoneError = validatePhone(phone)
        if (phoneError) nextFieldErrors.phone = phoneError
        const zipError = validateZip(zipCode)
        if (zipError) nextFieldErrors.zip_code = zipError
        if (condition === 'OTHER' && !conditionOther.trim()) nextFieldErrors.condition_other = 'Please describe the condition'
        if (hasInsurance && !insuranceProvider.trim()) nextFieldErrors.insurance_provider = 'Insurance provider is required when insurance is selected'
        if (isReferral && !providerName.trim()) nextFieldErrors.provider_name = 'Provider name is required for referred leads'

        if (Object.keys(nextFieldErrors).length > 0) {
            setFieldErrors(nextFieldErrors)
            setIsSubmitting(false)
            return
        }

        try {
            const payload: Record<string, unknown> = {
                first_name: firstName.trim(),
            }

            if (lastName.trim()) payload.last_name = lastName.trim()
            if (email.trim()) payload.email = email.trim()
            if (phone.trim()) payload.phone = phone.trim()
            if (condition) payload.condition = condition
            if (condition === 'OTHER' && conditionOther.trim()) payload.condition_other = conditionOther.trim()
            if (urgency) payload.urgency = urgency
            if (hasInsurance !== undefined) payload.has_insurance = hasInsurance
            if (hasInsurance && insuranceProvider.trim()) payload.insurance_provider = insuranceProvider.trim()
            if (zipCode.trim()) payload.zip_code = zipCode.trim()
            if (notes.trim()) payload.notes = notes.trim()
            if (isReferral && providerName.trim()) {
                payload.is_referral = true
                payload.referring_provider_name = providerName.trim()
                if (providerContact.trim()) payload.referring_provider_contact = providerContact.trim()
                if (providerSpecialty.trim()) payload.referring_provider_specialty = providerSpecialty.trim()
            }

            const response = await leadsAPI.createManual(payload)
            const leadId = response.data?.lead_id
            const leadNumber = response.data?.lead_number || 'Lead'

            if (leadId && files.length > 0) {
                for (const file of files) {
                    await uploadAttachment(leadId, file)
                }
                notifyAttachmentsChanged(leadId)
            }

            setSuccess(leadNumber)
            window.setTimeout(() => {
                onSuccess(leadNumber)
                handleClose()
            }, 900)
        } catch (err: any) {
            const detail = err?.response?.data?.detail
            const nextFieldErrors = resolveServerFieldErrors(detail)
            if (Object.keys(nextFieldErrors).length > 0) setFieldErrors(nextFieldErrors)
            setError(typeof detail === 'string' && detail.trim() ? detail.trim() : 'Failed to create lead. Please try again.')
        } finally {
            setIsSubmitting(false)
        }
    }

    if (!isOpen) return null

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" onClick={handleClose}>
            <div className="w-full max-w-lg max-h-[92vh] overflow-hidden rounded-3xl bg-white shadow-2xl" onClick={(event) => event.stopPropagation()}>
                <div className="flex items-center justify-between border-b border-gray-200 bg-gradient-to-r from-emerald-50 via-white to-white px-6 py-4">
                    <div className="flex items-center gap-3">
                        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-100">
                            <UserPlus size={22} className="text-emerald-700" />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-gray-900">Add New Lead</h2>
                            <p className="text-sm text-gray-500">Manual entry - assigned HOT priority</p>
                        </div>
                    </div>
                    <button onClick={handleClose} className="rounded-xl p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600">
                        <X size={20} />
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="max-h-[calc(92vh-84px)] overflow-y-auto">
                    <div className="space-y-6 px-6 py-5">
                        {error ? (
                            <div className="flex items-start gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                                <AlertCircle size={18} className="mt-0.5 shrink-0" />
                                <span>{error}</span>
                            </div>
                        ) : null}
                        {success ? (
                            <div className="flex items-start gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                                <CheckCircle2 size={18} className="mt-0.5 shrink-0" />
                                <span>{success} created successfully.</span>
                            </div>
                        ) : null}

                        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                            <div>
                                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">First Name <span className="text-red-500">*</span></label>
                                <input value={firstName} onChange={(event) => { setFirstName(event.target.value); clearFieldError('first_name') }} placeholder="First name" className={`w-full rounded-xl border px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 ${fieldErrors.first_name ? 'border-red-300 bg-red-50 focus:border-red-500' : 'border-gray-300 focus:border-sleep-500'}`} />
                                {fieldErrors.first_name ? <p className="mt-1.5 text-xs font-medium text-red-600">{fieldErrors.first_name}</p> : null}
                            </div>
                            <div>
                                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Last Name</label>
                                <input value={lastName} onChange={(event) => setLastName(event.target.value)} placeholder="Last name" className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20" />
                            </div>
                            <div>
                                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Email</label>
                                <input value={email} onChange={(event) => { setEmail(event.target.value); clearFieldError('email') }} type="email" placeholder="Email address" className={`w-full rounded-xl border px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 ${fieldErrors.email ? 'border-red-300 bg-red-50 focus:border-red-500' : 'border-gray-300 focus:border-sleep-500'}`} />
                                {fieldErrors.email ? <p className="mt-1.5 text-xs font-medium text-red-600">{fieldErrors.email}</p> : null}
                            </div>
                            <div>
                                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Phone</label>
                                <input value={phone} onChange={(event) => { setPhone(event.target.value); clearFieldError('phone') }} type="tel" placeholder="Phone number" className={`w-full rounded-xl border px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 ${fieldErrors.phone ? 'border-red-300 bg-red-50 focus:border-red-500' : 'border-gray-300 focus:border-sleep-500'}`} />
                                {fieldErrors.phone ? <p className="mt-1.5 text-xs font-medium text-red-600">{fieldErrors.phone}</p> : null}
                            </div>
                            <div>
                                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Condition</label>
                                <select value={condition} onChange={(event) => setCondition(event.target.value)} className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20">
                                    {CONDITION_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Urgency</label>
                                <select value={urgency} onChange={(event) => setUrgency(event.target.value)} className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20">
                                    {URGENCY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                                </select>
                            </div>
                        </div>

                        {condition === 'OTHER' ? (
                            <div>
                                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Other Condition</label>
                                <input value={conditionOther} onChange={(event) => { setConditionOther(event.target.value); clearFieldError('condition_other') }} placeholder="Describe the condition" className={`w-full rounded-xl border px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 ${fieldErrors.condition_other ? 'border-red-300 bg-red-50 focus:border-red-500' : 'border-gray-300 focus:border-sleep-500'}`} />
                                {fieldErrors.condition_other ? <p className="mt-1.5 text-xs font-medium text-red-600">{fieldErrors.condition_other}</p> : null}
                            </div>
                        ) : null}

                        <div className="grid grid-cols-1 gap-4 md:grid-cols-[180px_minmax(0,1fr)_160px]">
                            <div>
                                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Insurance?</label>
                                <select value={hasInsurance === undefined ? '' : hasInsurance ? 'yes' : 'no'} onChange={(event) => setHasInsurance(event.target.value === '' ? undefined : event.target.value === 'yes')} className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20">
                                    <option value="">Unknown</option>
                                    <option value="yes">Yes</option>
                                    <option value="no">No</option>
                                </select>
                            </div>
                            <div>
                                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Insurance Provider</label>
                                <input value={insuranceProvider} onChange={(event) => { setInsuranceProvider(event.target.value); clearFieldError('insurance_provider') }} placeholder="Enter provider name" className={`w-full rounded-xl border px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 ${fieldErrors.insurance_provider ? 'border-red-300 bg-red-50 focus:border-red-500' : 'border-gray-300 focus:border-sleep-500'}`} />
                                {fieldErrors.insurance_provider ? <p className="mt-1.5 text-xs font-medium text-red-600">{fieldErrors.insurance_provider}</p> : null}
                            </div>
                            <div>
                                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">ZIP Code</label>
                                <input value={zipCode} onChange={(event) => { setZipCode(event.target.value.replace(/\D/g, '').slice(0, 5)); clearFieldError('zip_code') }} inputMode="numeric" placeholder="Enter ZIP" className={`w-full rounded-xl border px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 ${fieldErrors.zip_code ? 'border-red-300 bg-red-50 focus:border-red-500' : 'border-gray-300 focus:border-sleep-500'}`} />
                                {fieldErrors.zip_code ? <p className="mt-1.5 text-xs font-medium text-red-600">{fieldErrors.zip_code}</p> : null}
                            </div>
                        </div>

                        <div className="rounded-2xl border border-sleep-200 bg-sleep-50/40 px-4 py-4">
                            <div className="flex items-center justify-between gap-4">
                                <div>
                                    <p className="text-sm font-semibold text-gray-900">Was this lead referred?</p>
                                    <p className="text-sm text-gray-500">Tag the lead to the provider and send it to the Providers dashboard.</p>
                                </div>
                                <button
                                    type="button"
                                    onClick={() => setIsReferral((prev) => !prev)}
                                    className={`relative inline-flex h-8 w-16 items-center rounded-full transition-colors ${isReferral ? 'bg-emerald-500' : 'bg-gray-300'}`}
                                >
                                    <span className={`absolute left-1 inline-flex h-6 w-6 rounded-full bg-white shadow transition-transform ${isReferral ? 'translate-x-8' : 'translate-x-0'}`} />
                                    <span className={`w-full px-2 text-xs font-semibold ${isReferral ? 'text-white text-left' : 'text-gray-700 text-right'}`}>{isReferral ? 'Yes' : 'No'}</span>
                                </button>
                            </div>

                            {isReferral ? (
                                <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
                                    <div className="md:col-span-3">
                                        <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Provider Name <span className="text-red-500">*</span></label>
                                        <input value={providerName} onChange={(event) => { setProviderName(event.target.value); clearFieldError('provider_name') }} placeholder="Referring provider name" className={`w-full rounded-xl border px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 ${fieldErrors.provider_name ? 'border-red-300 bg-red-50 focus:border-red-500' : 'border-gray-300 focus:border-sleep-500'}`} />
                                        {fieldErrors.provider_name ? <p className="mt-1.5 text-xs font-medium text-red-600">{fieldErrors.provider_name}</p> : null}
                                    </div>
                                    <div>
                                        <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Contact</label>
                                        <input value={providerContact} onChange={(event) => setProviderContact(event.target.value)} placeholder="Email or phone" className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20" />
                                    </div>
                                    <div className="md:col-span-2">
                                        <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Specialty</label>
                                        <input value={providerSpecialty} onChange={(event) => setProviderSpecialty(event.target.value)} placeholder="Sleep medicine, pulmonology, neurology" className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20" />
                                    </div>
                                </div>
                            ) : null}
                        </div>

                        <div>
                            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-gray-800">
                                <Paperclip size={16} className="text-gray-500" />
                                Attachments
                            </div>
                            <div
                                onDragOver={(event) => { event.preventDefault(); setIsDragOver(true) }}
                                onDragLeave={(event) => { event.preventDefault(); setIsDragOver(false) }}
                                onDrop={(event) => {
                                    event.preventDefault()
                                    setIsDragOver(false)
                                    if (event.dataTransfer.files?.length) addFiles(event.dataTransfer.files)
                                }}
                                onClick={() => fileInputRef.current?.click()}
                                className={`rounded-2xl border border-dashed px-5 py-7 text-center transition-colors ${isDragOver ? 'border-sleep-500 bg-sleep-50' : 'border-gray-300 hover:border-sleep-400 hover:bg-gray-50'}`}
                            >
                                <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-2xl bg-gray-100">
                                    <Upload size={20} className="text-gray-500" />
                                </div>
                                <p className="text-sm font-medium text-gray-700">Browse files or drag and drop</p>
                                <p className="mt-1 text-xs text-gray-500">PDF, Word, Excel, Images - max 25MB each</p>
                                <input ref={fileInputRef} type="file" multiple accept={ACCEPTED_TYPES.join(',')} className="hidden" onChange={(event) => event.target.files && addFiles(event.target.files)} />
                            </div>

                            {files.length > 0 ? (
                                <div className="mt-3 space-y-2">
                                    {files.map((file, index) => (
                                        <div key={`${file.name}-${file.size}-${index}`} className="flex items-center justify-between rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3">
                                            <div className="min-w-0">
                                                <p className="truncate text-sm font-medium text-gray-900">{file.name}</p>
                                                <p className="text-xs text-gray-500">{fileTypeLabel(file.type)} - {formatFileSize(file.size)}</p>
                                            </div>
                                            <button type="button" onClick={() => setFiles((prev) => prev.filter((_, fileIndex) => fileIndex !== index))} className="rounded-lg p-2 text-gray-400 hover:bg-white hover:text-red-500">
                                                <Trash2 size={15} />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            ) : null}
                        </div>

                        <div>
                            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Notes</label>
                            <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={4} placeholder="Add coordinator notes" className="w-full rounded-2xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20" />
                        </div>
                    </div>

                    <div className="flex items-center justify-between border-t border-gray-200 bg-gray-50 px-6 py-4">
                        <p className="text-xs text-gray-500">Referred leads are tagged and linked to the Providers dashboard automatically.</p>
                        <div className="flex items-center gap-3">
                            <button type="button" onClick={handleClose} className="rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100">Cancel</button>
                            <button type="submit" disabled={!canSubmit} className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60">
                                {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
                                Add Lead
                            </button>
                        </div>
                    </div>
                </form>
            </div>
        </div>
    )
}
