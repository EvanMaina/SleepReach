import { useEffect, useMemo, useState } from 'react'
import {
    AlertCircle,
    CheckCircle2,
    Clock,
    Loader2,
    Mail,
    MapPin,
    Moon,
    Phone,
    Save,
    Shield,
    Tag,
    User,
    X,
} from 'lucide-react'
import { leadsAPI } from '../../lib/api'

interface EditableLead {
    id: string
    lead_number?: string
    updated_at?: string
    first_name: string
    last_name?: string
    email?: string
    phone?: string
    condition?: string
    conditions?: string[]
    other_condition_text?: string
    condition_other?: string
    urgency?: string
    symptom_duration?: string
    sleep_treatment_interest?: string
    has_insurance?: boolean
    insurance_provider?: string
    zip_code?: string
    notes?: string
    priority: string
    status: string
    last_updated_at?: string
}

interface LeadEditModalProps {
    isOpen: boolean
    lead: EditableLead | null
    onClose: () => void
    onSave: (updatedLead: EditableLead) => void
}

const CONDITION_OPTIONS = [
    { value: '', label: 'Select condition' },
    { value: 'INSOMNIA', label: 'Insomnia' },
    { value: 'SLEEP_APNEA', label: 'Sleep Apnea' },
    { value: 'RESTLESS_LEG', label: 'Restless Legs Syndrome' },
    { value: 'NARCOLEPSY', label: 'Narcolepsy' },
    { value: 'OTHER', label: 'Other' },
]

const URGENCY_OPTIONS = [
    { value: '', label: 'Select urgency' },
    { value: 'ASAP', label: 'Urgent - needs immediate attention' },
    { value: 'WITHIN_30_DAYS', label: 'Soon - within 30 days' },
    { value: 'EXPLORING', label: 'Exploring - researching options' },
]

const DURATION_OPTIONS = [
    { value: '', label: 'Select symptom duration' },
    { value: 'LESS_THAN_6_MONTHS', label: 'Less than 6 months' },
    { value: 'SIX_TO_TWELVE_MONTHS', label: '6 to 12 months' },
    { value: 'MORE_THAN_12_MONTHS', label: 'More than 12 months' },
]

const TREATMENT_INTEREST_OPTIONS = [
    { value: '', label: 'Select treatment interest' },
    { value: 'cpap_bipap', label: 'CPAP Therapy' },
    { value: 'inspire', label: 'Inspire Therapy' },
    { value: 'therapy_cbt', label: 'CBT-I Therapy' },
    { value: 'sleep_study', label: 'Testing / Sleep Study' },
    { value: 'medication', label: 'Medication Review' },
    { value: 'not_sure', label: "Not sure - I'd like to learn more" },
]

const PRIORITY_OPTIONS = [
    { value: 'HOT', label: 'Hot' },
    { value: 'MEDIUM', label: 'Medium' },
    { value: 'LOW', label: 'Low' },
    { value: 'DISQUALIFIED', label: 'Disqualified' },
]

const STATUS_OPTIONS = [
    { value: 'NEW', label: 'New' },
    { value: 'CONTACTED', label: 'Contacted' },
    { value: 'SCHEDULED', label: 'Scheduled' },
    { value: 'CONSULTATION_COMPLETE', label: 'Consultation Complete' },
    { value: 'TREATMENT_STARTED', label: 'Treatment Started' },
    { value: 'LOST', label: 'Lost' },
    { value: 'DISQUALIFIED', label: 'Disqualified' },
]

function cleanString(value: unknown): string {
    if (value === null || value === undefined) return ''
    const normalized = String(value).trim()
    if (!normalized) return ''
    if (['null', 'undefined', 'none', 'NULL', 'UNDEFINED', 'NONE'].includes(normalized)) return ''
    return normalized
}

function normalizeCondition(lead: EditableLead): string {
    const primary = cleanString(lead.condition).toUpperCase()
    if (primary && CONDITION_OPTIONS.some((option) => option.value === primary)) return primary
    const conditions = Array.isArray(lead.conditions) ? lead.conditions : []
    const first = cleanString(conditions[0]).toUpperCase()
    if (first && CONDITION_OPTIONS.some((option) => option.value === first)) return first
    const otherText = cleanString(lead.other_condition_text || lead.condition_other)
    return otherText ? 'OTHER' : ''
}

function normalizeUrgency(value?: string): string {
    const urgency = cleanString(value).toUpperCase().replace(/ /g, '_')
    return URGENCY_OPTIONS.some((option) => option.value === urgency) ? urgency : ''
}

function normalizeDuration(value?: string): string {
    const duration = cleanString(value).toUpperCase().replace(/ /g, '_')
    return DURATION_OPTIONS.some((option) => option.value === duration) ? duration : ''
}

function normalizeTreatmentInterest(value?: string): string {
    const interest = cleanString(value).toLowerCase()
    return TREATMENT_INTEREST_OPTIONS.some((option) => option.value === interest) ? interest : ''
}

function normalizeStatus(value?: string): string {
    const status = cleanString(value).toUpperCase().replace(/ /g, '_')
    return STATUS_OPTIONS.some((option) => option.value === status) ? status : 'NEW'
}

function normalizePriority(value?: string): string {
    const priority = cleanString(value).toUpperCase()
    return PRIORITY_OPTIONS.some((option) => option.value === priority) ? priority : 'LOW'
}

type LeadEditField = 'first_name' | 'email' | 'phone' | 'zip_code' | 'condition_other' | 'insurance_provider'

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

function resolveFieldErrors(detail: unknown): Partial<Record<LeadEditField, string>> {
    if (Array.isArray(detail)) {
        const next: Partial<Record<LeadEditField, string>> = {}
        detail.forEach((item) => {
            const path = Array.isArray(item?.loc) ? item.loc.join('.') : ''
            const message = typeof item?.msg === 'string' ? item.msg : 'Invalid value'
            if (path.includes('first_name')) next.first_name = message
            if (path.includes('email')) next.email = message
            if (path.includes('phone')) next.phone = message
            if (path.includes('zip_code')) next.zip_code = message
            if (path.includes('condition_other')) next.condition_other = message
            if (path.includes('insurance_provider')) next.insurance_provider = message
        })
        return next
    }

    if (typeof detail === 'string') {
        const message = detail.trim()
        const lowered = message.toLowerCase()
        if (lowered.includes('email')) return { email: message }
        if (lowered.includes('phone')) return { phone: message }
        if (lowered.includes('zip')) return { zip_code: message }
    }

    return {}
}

export function LeadEditModal({ isOpen, lead, onClose, onSave }: LeadEditModalProps) {
    const [formData, setFormData] = useState({
        first_name: '',
        last_name: '',
        email: '',
        phone: '',
        zip_code: '',
        condition: '',
        condition_other: '',
        urgency: '',
        symptom_duration: '',
        sleep_treatment_interest: '',
        has_insurance: false,
        insurance_provider: '',
        status: 'NEW',
        priority: 'LOW',
        notes: '',
    })
    const [isSaving, setIsSaving] = useState(false)
    const [saveSuccess, setSaveSuccess] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [fieldErrors, setFieldErrors] = useState<Partial<Record<LeadEditField, string>>>({})

    useEffect(() => {
        if (!lead || !isOpen) return
        setFormData({
            first_name: cleanString(lead.first_name),
            last_name: cleanString(lead.last_name),
            email: cleanString(lead.email),
            phone: cleanString(lead.phone),
            zip_code: cleanString(lead.zip_code),
            condition: normalizeCondition(lead),
            condition_other: cleanString(lead.other_condition_text || lead.condition_other),
            urgency: normalizeUrgency(lead.urgency),
            symptom_duration: normalizeDuration(lead.symptom_duration),
            sleep_treatment_interest: normalizeTreatmentInterest(lead.sleep_treatment_interest),
            has_insurance: Boolean(lead.has_insurance),
            insurance_provider: cleanString(lead.insurance_provider),
            status: normalizeStatus(lead.status),
            priority: normalizePriority(lead.priority),
            notes: cleanString(lead.notes),
        })
        setError(null)
        setSaveSuccess(false)
        setFieldErrors({})
    }, [isOpen, lead])

    const hasConditionOther = formData.condition === 'OTHER'

    const handleChange = (
        event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
    ) => {
        const { name, value, type } = event.target
        if (type === 'checkbox') {
            const fieldName = name as LeadEditField
            if (fieldErrors[fieldName]) {
                setFieldErrors((prev) => {
                    const next = { ...prev }
                    delete next[fieldName]
                    return next
                })
            }
            setFormData((prev) => ({ ...prev, [name]: (event.target as HTMLInputElement).checked }))
            return
        }
        const fieldName = name as LeadEditField
        if (fieldErrors[fieldName]) {
            setFieldErrors((prev) => {
                const next = { ...prev }
                delete next[fieldName]
                return next
            })
        }
        setFormData((prev) => ({ ...prev, [name]: value }))
    }

    const canSubmit = useMemo(() => {
        return !isSaving
    }, [isSaving])

    const handleSave = async () => {
        if (!lead || !canSubmit) return
        setIsSaving(true)
        setError(null)
        setFieldErrors({})

        const nextFieldErrors: Partial<Record<LeadEditField, string>> = {}
        if (!formData.first_name.trim()) nextFieldErrors.first_name = 'First name is required'
        const emailError = validateEmail(formData.email)
        if (emailError) nextFieldErrors.email = emailError
        const phoneError = validatePhone(formData.phone)
        if (phoneError) nextFieldErrors.phone = phoneError
        const zipError = validateZip(formData.zip_code)
        if (zipError) nextFieldErrors.zip_code = zipError
        if (hasConditionOther && !formData.condition_other.trim()) nextFieldErrors.condition_other = 'Please describe the condition'
        if (formData.has_insurance && !formData.insurance_provider.trim()) nextFieldErrors.insurance_provider = 'Insurance provider is required when insurance is selected'

        if (Object.keys(nextFieldErrors).length > 0) {
            setFieldErrors(nextFieldErrors)
            setIsSaving(false)
            return
        }

        const payload: Record<string, unknown> = {}
        const assignIfChanged = (key: keyof typeof formData, nextValue: unknown, currentValue: unknown) => {
            if (nextValue !== currentValue) payload[key] = nextValue
        }

        const currentCondition = normalizeCondition(lead)
        const currentConditionOther = cleanString(lead.other_condition_text || lead.condition_other)
        const currentUrgency = normalizeUrgency(lead.urgency)
        const currentDuration = normalizeDuration(lead.symptom_duration)
        const currentInterest = normalizeTreatmentInterest(lead.sleep_treatment_interest)
        const currentStatus = normalizeStatus(lead.status)
        const currentPriority = normalizePriority(lead.priority)

        assignIfChanged('first_name', formData.first_name.trim(), cleanString(lead.first_name))
        assignIfChanged('last_name', formData.last_name.trim(), cleanString(lead.last_name))
        assignIfChanged('email', formData.email.trim(), cleanString(lead.email))
        assignIfChanged('phone', formData.phone.trim(), cleanString(lead.phone))
        assignIfChanged('zip_code', formData.zip_code.trim(), cleanString(lead.zip_code))
        assignIfChanged('condition', formData.condition || null, currentCondition || null)
        assignIfChanged(
            'condition_other',
            hasConditionOther ? formData.condition_other.trim() : '',
            currentConditionOther,
        )
        assignIfChanged('urgency', formData.urgency || null, currentUrgency || null)
        assignIfChanged('symptom_duration', formData.symptom_duration || null, currentDuration || null)
        assignIfChanged(
            'sleep_treatment_interest',
            formData.sleep_treatment_interest || '',
            currentInterest,
        )
        assignIfChanged('has_insurance', formData.has_insurance, Boolean(lead.has_insurance))
        assignIfChanged(
            'insurance_provider',
            formData.has_insurance ? formData.insurance_provider.trim() : '',
            cleanString(lead.insurance_provider),
        )
        assignIfChanged('status', formData.status, currentStatus)
        assignIfChanged('priority', formData.priority, currentPriority)
        assignIfChanged('notes', formData.notes.trim(), cleanString(lead.notes))

        if (lead.updated_at || lead.last_updated_at) {
            payload.expected_updated_at = lead.updated_at || lead.last_updated_at
        }

        if (Object.keys(payload).length === 0 || (Object.keys(payload).length === 1 && payload.expected_updated_at)) {
            onClose()
            setIsSaving(false)
            return
        }

        try {
            const response = await leadsAPI.update(lead.id, payload)
            setSaveSuccess(true)
            window.setTimeout(() => {
                setSaveSuccess(false)
                onSave(response.data)
            }, 700)
        } catch (err: any) {
            const detail = err?.response?.data?.detail
            const nextFieldErrors = resolveFieldErrors(detail)
            if (Object.keys(nextFieldErrors).length > 0) setFieldErrors(nextFieldErrors)
            setError(detail || err?.message || 'Failed to save changes.')
        } finally {
            setIsSaving(false)
        }
    }

    if (!isOpen || !lead) return null

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/45 p-4" onClick={onClose}>
            <div
                className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-3xl bg-white shadow-2xl"
                onClick={(event) => event.stopPropagation()}
            >
                <div className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-5">
                    <div>
                        <h3 className="text-2xl font-bold text-gray-900">Edit Lead</h3>
                        <p className="mt-1 text-sm font-mono text-gray-500">{lead.lead_number || lead.id}</p>
                    </div>
                    <button
                        onClick={onClose}
                        className="rounded-xl p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                    >
                        <X size={22} />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto px-6 py-5">
                    <div className="space-y-6">
                        {saveSuccess ? (
                            <div className="flex items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                                <CheckCircle2 size={18} className="shrink-0" />
                                <span>Lead updated successfully.</span>
                            </div>
                        ) : null}

                        {error ? (
                            <div className="flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                                <AlertCircle size={18} className="shrink-0" />
                                <span>{error}</span>
                            </div>
                        ) : null}

                        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                            <div className="md:col-span-2 flex items-center justify-between rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3">
                                <div className="text-sm text-gray-500">Current lead number</div>
                                <div className="flex items-center gap-2">
                                    <span className="rounded-full bg-white px-3 py-1 text-xs font-mono font-semibold text-sleep-700 shadow-sm">
                                        {lead.lead_number || lead.id}
                                    </span>
                                    <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-gray-700 shadow-sm">
                                        {normalizePriority(lead.priority)}
                                    </span>
                                </div>
                            </div>
                        </div>

                        <section className="space-y-4">
                            <h4 className="flex items-center gap-2 text-base font-semibold text-gray-900">
                                <User size={16} className="text-gray-500" />
                                Contact Information
                            </h4>
                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <div>
                                    <label className="mb-1.5 block text-sm font-medium text-gray-700">First Name *</label>
                                    <input
                                        name="first_name"
                                        value={formData.first_name}
                                        onChange={handleChange}
                                        className={`w-full rounded-xl border px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 ${fieldErrors.first_name ? 'border-red-300 bg-red-50 focus:border-red-500' : 'border-gray-300 focus:border-sleep-500'}`}
                                    />
                                    {fieldErrors.first_name ? <p className="mt-1.5 text-xs font-medium text-red-600">{fieldErrors.first_name}</p> : null}
                                </div>
                                <div>
                                    <label className="mb-1.5 block text-sm font-medium text-gray-700">Last Name</label>
                                    <input
                                        name="last_name"
                                        value={formData.last_name}
                                        onChange={handleChange}
                                        className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                                    />
                                </div>
                                <div>
                                    <label className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-gray-700">
                                        <Mail size={14} className="text-gray-500" />
                                        Email
                                    </label>
                                    <input
                                        name="email"
                                        type="email"
                                        value={formData.email}
                                        onChange={handleChange}
                                        className={`w-full rounded-xl border px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 ${fieldErrors.email ? 'border-red-300 bg-red-50 focus:border-red-500' : 'border-gray-300 focus:border-sleep-500'}`}
                                    />
                                    {fieldErrors.email ? <p className="mt-1.5 text-xs font-medium text-red-600">{fieldErrors.email}</p> : null}
                                </div>
                                <div>
                                    <label className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-gray-700">
                                        <Phone size={14} className="text-gray-500" />
                                        Phone
                                    </label>
                                    <input
                                        name="phone"
                                        type="tel"
                                        value={formData.phone}
                                        onChange={handleChange}
                                        className={`w-full rounded-xl border px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 ${fieldErrors.phone ? 'border-red-300 bg-red-50 focus:border-red-500' : 'border-gray-300 focus:border-sleep-500'}`}
                                    />
                                    {fieldErrors.phone ? <p className="mt-1.5 text-xs font-medium text-red-600">{fieldErrors.phone}</p> : null}
                                </div>
                                <div className="md:col-span-2">
                                    <label className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-gray-700">
                                        <MapPin size={14} className="text-gray-500" />
                                        ZIP Code
                                    </label>
                                    <input
                                        name="zip_code"
                                        value={formData.zip_code}
                                        onChange={handleChange}
                                        maxLength={10}
                                        className={`w-full rounded-xl border px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 ${fieldErrors.zip_code ? 'border-red-300 bg-red-50 focus:border-red-500' : 'border-gray-300 focus:border-sleep-500'}`}
                                    />
                                    {fieldErrors.zip_code ? <p className="mt-1.5 text-xs font-medium text-red-600">{fieldErrors.zip_code}</p> : null}
                                </div>
                            </div>
                        </section>

                        <section className="space-y-4">
                            <h4 className="flex items-center gap-2 text-base font-semibold text-gray-900">
                                <Moon size={16} className="text-gray-500" />
                                Clinical Information
                            </h4>
                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <div>
                                    <label className="mb-1.5 block text-sm font-medium text-gray-700">Condition</label>
                                    <select
                                        name="condition"
                                        value={formData.condition}
                                        onChange={handleChange}
                                        className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                                    >
                                        {CONDITION_OPTIONS.map((option) => (
                                            <option key={option.value} value={option.value}>{option.label}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-gray-700">
                                        <Clock size={14} className="text-gray-500" />
                                        Urgency
                                    </label>
                                    <select
                                        name="urgency"
                                        value={formData.urgency}
                                        onChange={handleChange}
                                        className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                                    >
                                        {URGENCY_OPTIONS.map((option) => (
                                            <option key={option.value} value={option.value}>{option.label}</option>
                                        ))}
                                    </select>
                                </div>
                                {hasConditionOther ? (
                                    <div className="md:col-span-2">
                                        <label className="mb-1.5 block text-sm font-medium text-gray-700">Other Condition *</label>
                                        <input
                                            name="condition_other"
                                            value={formData.condition_other}
                                            onChange={handleChange}
                                            placeholder="Describe the sleep condition"
                                            className={`w-full rounded-xl border px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 ${fieldErrors.condition_other ? 'border-red-300 bg-red-50 focus:border-red-500' : 'border-gray-300 focus:border-sleep-500'}`}
                                        />
                                        {fieldErrors.condition_other ? <p className="mt-1.5 text-xs font-medium text-red-600">{fieldErrors.condition_other}</p> : null}
                                    </div>
                                ) : null}
                                <div>
                                    <label className="mb-1.5 block text-sm font-medium text-gray-700">Symptom Duration</label>
                                    <select
                                        name="symptom_duration"
                                        value={formData.symptom_duration}
                                        onChange={handleChange}
                                        className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                                    >
                                        {DURATION_OPTIONS.map((option) => (
                                            <option key={option.value} value={option.value}>{option.label}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-gray-700">
                                        <Tag size={14} className="text-gray-500" />
                                        Treatment Interest
                                    </label>
                                    <select
                                        name="sleep_treatment_interest"
                                        value={formData.sleep_treatment_interest}
                                        onChange={handleChange}
                                        className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                                    >
                                        {TREATMENT_INTEREST_OPTIONS.map((option) => (
                                            <option key={option.value} value={option.value}>{option.label}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>
                        </section>

                        <section className="space-y-4">
                            <h4 className="flex items-center gap-2 text-base font-semibold text-gray-900">
                                <Shield size={16} className="text-gray-500" />
                                Insurance & Lead Management
                            </h4>
                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <div className="rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3 md:col-span-2">
                                    <label className="flex items-center gap-3 text-sm font-medium text-gray-700">
                                        <input
                                            type="checkbox"
                                            name="has_insurance"
                                            checked={formData.has_insurance}
                                            onChange={handleChange}
                                            className="h-4 w-4 rounded border-gray-300 text-sleep-600 focus:ring-sleep-500"
                                        />
                                        Has Insurance
                                    </label>
                                </div>
                                {formData.has_insurance ? (
                                    <div className="md:col-span-2">
                                        <label className="mb-1.5 block text-sm font-medium text-gray-700">Insurance Provider</label>
                                        <input
                                            name="insurance_provider"
                                            value={formData.insurance_provider}
                                            onChange={handleChange}
                                            placeholder="Enter provider name"
                                            className={`w-full rounded-xl border px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 ${fieldErrors.insurance_provider ? 'border-red-300 bg-red-50 focus:border-red-500' : 'border-gray-300 focus:border-sleep-500'}`}
                                        />
                                        {fieldErrors.insurance_provider ? <p className="mt-1.5 text-xs font-medium text-red-600">{fieldErrors.insurance_provider}</p> : null}
                                    </div>
                                ) : null}
                                <div>
                                    <label className="mb-1.5 block text-sm font-medium text-gray-700">Status</label>
                                    <select
                                        name="status"
                                        value={formData.status}
                                        onChange={handleChange}
                                        className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                                    >
                                        {STATUS_OPTIONS.map((option) => (
                                            <option key={option.value} value={option.value}>{option.label}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="mb-1.5 block text-sm font-medium text-gray-700">Priority</label>
                                    <select
                                        name="priority"
                                        value={formData.priority}
                                        onChange={handleChange}
                                        className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                                    >
                                        {PRIORITY_OPTIONS.map((option) => (
                                            <option key={option.value} value={option.value}>{option.label}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="md:col-span-2">
                                    <label className="mb-1.5 block text-sm font-medium text-gray-700">Notes</label>
                                    <textarea
                                        name="notes"
                                        rows={4}
                                        value={formData.notes}
                                        onChange={handleChange}
                                        placeholder="Add coordinator notes"
                                        className="w-full rounded-2xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                                    />
                                </div>
                            </div>
                        </section>
                    </div>
                </div>

                <div className="flex items-center justify-end gap-3 border-t border-gray-200 bg-gray-50 px-6 py-4">
                    <button
                        onClick={onClose}
                        className="rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={!canSubmit}
                        className="inline-flex items-center gap-2 rounded-xl bg-sleep-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-sleep-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                        {isSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                        Save Changes
                    </button>
                </div>
            </div>
        </div>
    )
}

export default LeadEditModal
