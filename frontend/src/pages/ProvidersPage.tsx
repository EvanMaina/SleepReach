import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import {
    AlertCircle,
    Building2,
    ChevronLeft,
    ChevronRight,
    Edit3,
    Eye,
    Loader2,
    Mail,
    MapPin,
    Phone,
    Plus,
    RefreshCw,
    Search,
    Shield,
    UserPlus,
    X,
} from 'lucide-react'
import { providersAPI } from '../lib/api'

interface ProviderRecord {
    id: string
    name: string
    email?: string | null
    phone?: string | null
    practice_name?: string | null
    practice_address?: string | null
    practice_city?: string | null
    practice_state?: string | null
    practice_zip?: string | null
    specialty?: string | null
    status: string
    total_referrals?: number
    converted_referrals?: number
    conversion_rate?: number
    last_referral_at?: string | null
    notes?: string | null
    created_at?: string
    updated_at?: string
}

interface ProviderStats {
    total_providers: number
    active_providers: number
    pending_providers: number
    total_referrals: number
    overall_conversion_rate: number
    referrals_this_month: number
}

interface ProviderReferralLead {
    id: string
    lead_number: string
    condition: string
    priority: string
    status: string
    created_at: string
    is_converted: boolean
}

interface ProviderFormState {
    name: string
    practice_name: string
    email: string
    phone: string
    specialty: string
    status: string
    notes: string
}

type ProviderField = 'name' | 'email' | 'phone' | 'specialty'

const PAGE_SIZE = 20
const SPECIALTY_OPTIONS = [
    'All Specialties',
    'Sleep Medicine',
    'Pulmonology',
    'Neurology',
    'Primary Care',
    'ENT',
    'Psychiatrist',
    'Nurse Practitioner',
    'Other',
]

const EMPTY_FORM: ProviderFormState = {
    name: '',
    practice_name: '',
    email: '',
    phone: '',
    specialty: '',
    status: 'pending',
    notes: '',
}

function statusBadge(status: string) {
    const map: Record<string, string> = {
        active: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
        pending: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
        inactive: 'bg-gray-100 text-gray-600 ring-1 ring-gray-200',
        archived: 'bg-slate-100 text-slate-600 ring-1 ring-slate-200',
    }
    return map[status?.toLowerCase()] || map.pending
}

function formatDate(value?: string | null) {
    if (!value) return '—'
    return new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

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

function ProviderFormModal({
    isOpen,
    mode,
    form,
    fieldErrors,
    isSaving,
    serverError,
    onClose,
    onChange,
    onSubmit,
}: {
    isOpen: boolean
    mode: 'create' | 'edit'
    form: ProviderFormState
    fieldErrors: Partial<Record<ProviderField, string>>
    isSaving: boolean
    serverError: string | null
    onClose: () => void
    onChange: (key: keyof ProviderFormState, value: string) => void
    onSubmit: (event: FormEvent) => void
}) {
    if (!isOpen) return null

    return (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-4" onClick={onClose}>
            <div className="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl" onClick={(event) => event.stopPropagation()}>
                <div className="flex items-center justify-between border-b border-gray-200 bg-gradient-to-r from-sleep-50 via-white to-white px-6 py-5">
                    <div className="flex items-center gap-3">
                        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-sleep-100">
                            {mode === 'create' ? <UserPlus size={22} className="text-sleep-700" /> : <Edit3 size={22} className="text-sleep-700" />}
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-gray-900">{mode === 'create' ? 'Add Provider' : 'Edit Provider'}</h2>
                            <p className="text-sm text-gray-500">Manage referral partners with the same workflow as SleepReach.</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="rounded-xl p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600">
                        <X size={20} />
                    </button>
                </div>

                <form onSubmit={onSubmit} className="space-y-5 px-6 py-6">
                    {serverError ? (
                        <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                            <AlertCircle size={16} className="mt-0.5 shrink-0" />
                            <span>{serverError}</span>
                        </div>
                    ) : null}

                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                        <div className="md:col-span-2">
                            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Provider Name <span className="text-red-500">*</span></label>
                            <input
                                value={form.name}
                                onChange={(event) => onChange('name', event.target.value)}
                                placeholder="Dr. Sarah Johnson"
                                className={`w-full rounded-xl border px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 ${fieldErrors.name ? 'border-red-300 bg-red-50 focus:border-red-500' : 'border-gray-300 focus:border-sleep-500'}`}
                            />
                            {fieldErrors.name ? <p className="mt-1.5 text-xs font-medium text-red-600">{fieldErrors.name}</p> : null}
                        </div>
                        <div className="md:col-span-2">
                            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Practice / Organization</label>
                            <input
                                value={form.practice_name}
                                onChange={(event) => onChange('practice_name', event.target.value)}
                                placeholder="The Insomnia and Sleep Institute of Arizona"
                                className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                            />
                        </div>
                        <div>
                            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Email</label>
                            <input
                                type="email"
                                value={form.email}
                                onChange={(event) => onChange('email', event.target.value)}
                                placeholder="provider@clinic.com"
                                className={`w-full rounded-xl border px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 ${fieldErrors.email ? 'border-red-300 bg-red-50 focus:border-red-500' : 'border-gray-300 focus:border-sleep-500'}`}
                            />
                            {fieldErrors.email ? <p className="mt-1.5 text-xs font-medium text-red-600">{fieldErrors.email}</p> : null}
                        </div>
                        <div>
                            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Phone</label>
                            <input
                                type="tel"
                                value={form.phone}
                                onChange={(event) => onChange('phone', event.target.value)}
                                placeholder="+1 (480) 555-0100"
                                className={`w-full rounded-xl border px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 ${fieldErrors.phone ? 'border-red-300 bg-red-50 focus:border-red-500' : 'border-gray-300 focus:border-sleep-500'}`}
                            />
                            {fieldErrors.phone ? <p className="mt-1.5 text-xs font-medium text-red-600">{fieldErrors.phone}</p> : null}
                        </div>
                        <div>
                            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Specialty <span className="text-red-500">*</span></label>
                            <input
                                value={form.specialty}
                                onChange={(event) => onChange('specialty', event.target.value)}
                                placeholder="Sleep Medicine"
                                className={`w-full rounded-xl border px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 ${fieldErrors.specialty ? 'border-red-300 bg-red-50 focus:border-red-500' : 'border-gray-300 focus:border-sleep-500'}`}
                            />
                            {fieldErrors.specialty ? <p className="mt-1.5 text-xs font-medium text-red-600">{fieldErrors.specialty}</p> : null}
                        </div>
                        <div>
                            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Status</label>
                            <select
                                value={form.status}
                                onChange={(event) => onChange('status', event.target.value)}
                                className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                            >
                                <option value="active">Active</option>
                                <option value="pending">Pending Verification</option>
                                <option value="inactive">Inactive</option>
                                <option value="archived">Archived</option>
                            </select>
                        </div>
                        <div className="md:col-span-2">
                            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">Notes</label>
                            <textarea
                                rows={4}
                                value={form.notes}
                                onChange={(event) => onChange('notes', event.target.value)}
                                placeholder="Optional context about this provider relationship"
                                className="w-full rounded-2xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                            />
                        </div>
                    </div>

                    <div className="flex items-center justify-end gap-3 border-t border-gray-200 pt-4">
                        <button type="button" onClick={onClose} className="rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50">
                            Cancel
                        </button>
                        <button type="submit" disabled={isSaving} className="inline-flex items-center gap-2 rounded-xl bg-sleep-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-sleep-700 disabled:opacity-60">
                            {isSaving ? <Loader2 size={16} className="animate-spin" /> : mode === 'create' ? <Plus size={16} /> : <Edit3 size={16} />}
                            {mode === 'create' ? 'Save Provider' : 'Save Changes'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    )
}

function ProviderDetailModal({
    provider,
    referrals,
    isLoading,
    onClose,
    onEdit,
}: {
    provider: ProviderRecord | null
    referrals: ProviderReferralLead[]
    isLoading: boolean
    onClose: () => void
    onEdit: () => void
}) {
    if (!provider) return null

    return (
        <div className="fixed inset-0 z-[65] flex items-center justify-center bg-black/45 p-4" onClick={onClose}>
            <div className="w-full max-w-3xl overflow-hidden rounded-3xl bg-white shadow-2xl" onClick={(event) => event.stopPropagation()}>
                <div className="flex items-center justify-between border-b border-gray-200 px-6 py-5">
                    <div>
                        <h2 className="text-2xl font-bold text-gray-900">{provider.name}</h2>
                        <p className="mt-1 text-sm text-gray-500">{provider.practice_name || 'Independent provider'} · {provider.specialty || 'Specialty not provided'}</p>
                    </div>
                    <div className="flex items-center gap-2">
                        <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${statusBadge(provider.status)}`}>
                            {provider.status}
                        </span>
                        <button onClick={onClose} className="rounded-xl p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600">
                            <X size={20} />
                        </button>
                    </div>
                </div>

                <div className="max-h-[82vh] overflow-y-auto px-6 py-5">
                    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                        <div className="rounded-2xl border border-gray-200 bg-gray-50 p-4">
                            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Total Referrals</p>
                            <p className="mt-2 text-2xl font-bold text-gray-900">{provider.total_referrals ?? 0}</p>
                        </div>
                        <div className="rounded-2xl border border-gray-200 bg-gray-50 p-4">
                            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Conversion Rate</p>
                            <p className="mt-2 text-2xl font-bold text-gray-900">{provider.conversion_rate?.toFixed(1) ?? '0.0'}%</p>
                        </div>
                        <div className="rounded-2xl border border-gray-200 bg-gray-50 p-4">
                            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Last Referral</p>
                            <p className="mt-2 text-sm font-semibold text-gray-900">{formatDate(provider.last_referral_at)}</p>
                        </div>
                    </div>

                    <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
                        <div className="rounded-2xl border border-gray-200 p-4">
                            <h3 className="text-sm font-semibold text-gray-900">Provider Information</h3>
                            <div className="mt-4 space-y-3 text-sm text-gray-600">
                                <div className="flex items-start gap-2">
                                    <Building2 size={15} className="mt-0.5 text-gray-400" />
                                    <span>{provider.practice_name || 'Practice not provided'}</span>
                                </div>
                                <div className="flex items-start gap-2">
                                    <Mail size={15} className="mt-0.5 text-gray-400" />
                                    <span>{provider.email || 'No email on file'}</span>
                                </div>
                                <div className="flex items-start gap-2">
                                    <Phone size={15} className="mt-0.5 text-gray-400" />
                                    <span>{provider.phone || 'No phone on file'}</span>
                                </div>
                                <div className="flex items-start gap-2">
                                    <MapPin size={15} className="mt-0.5 text-gray-400" />
                                    <span>{[provider.practice_address, provider.practice_city, provider.practice_state, provider.practice_zip].filter(Boolean).join(', ') || 'Address not provided'}</span>
                                </div>
                            </div>
                            {provider.notes ? (
                                <div className="mt-4 rounded-2xl border border-sleep-100 bg-sleep-50/60 p-3 text-sm text-gray-700">
                                    {provider.notes}
                                </div>
                            ) : null}
                        </div>

                        <div className="rounded-2xl border border-gray-200 p-4">
                            <div className="flex items-center justify-between gap-3">
                                <h3 className="text-sm font-semibold text-gray-900">Referred Leads</h3>
                                <span className="text-xs font-medium text-gray-400">{referrals.length} shown</span>
                            </div>
                            <div className="mt-4 space-y-2">
                                {isLoading ? (
                                    <div className="flex items-center justify-center py-8 text-sm text-gray-400">
                                        <Loader2 size={16} className="mr-2 animate-spin" />
                                        Loading referred leads...
                                    </div>
                                ) : referrals.length === 0 ? (
                                    <p className="rounded-2xl border border-dashed border-gray-200 bg-gray-50 px-4 py-6 text-sm text-gray-400">No referred leads yet.</p>
                                ) : (
                                    referrals.map((lead) => (
                                        <div key={lead.id} className="rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3">
                                            <div className="flex items-center justify-between gap-3">
                                                <div>
                                                    <p className="text-sm font-semibold text-gray-900">{lead.lead_number}</p>
                                                    <p className="text-xs text-gray-500">{lead.condition.replace(/_/g, ' ')} · {formatDate(lead.created_at)}</p>
                                                </div>
                                                <div className="text-right">
                                                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{lead.status.replace(/_/g, ' ')}</p>
                                                    <p className={`text-xs font-medium ${lead.is_converted ? 'text-emerald-600' : 'text-gray-400'}`}>{lead.is_converted ? 'Converted' : 'Open'}</p>
                                                </div>
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>
                        </div>
                    </div>
                </div>

                <div className="flex items-center justify-end gap-3 border-t border-gray-200 bg-gray-50 px-6 py-4">
                    <button onClick={onClose} className="rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50">
                        Close
                    </button>
                    <button onClick={onEdit} className="inline-flex items-center gap-2 rounded-xl bg-sleep-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-sleep-700">
                        <Edit3 size={16} />
                        Edit Provider
                    </button>
                </div>
            </div>
        </div>
    )
}

function ProviderEmailModal({
    provider,
    isOpen,
    isSending,
    error,
    onClose,
    onSend,
}: {
    provider: ProviderRecord | null
    isOpen: boolean
    isSending: boolean
    error: string | null
    onClose: () => void
    onSend: (subject: string, message: string) => Promise<void>
}) {
    const [subject, setSubject] = useState('')
    const [message, setMessage] = useState('')

    useEffect(() => {
        if (!isOpen) return
        setSubject('')
        setMessage('')
    }, [isOpen, provider?.id])

    if (!isOpen || !provider) return null

    return (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-4" onClick={onClose}>
            <div className="w-full max-w-lg overflow-hidden rounded-3xl bg-white shadow-2xl" onClick={(event) => event.stopPropagation()}>
                <div className="flex items-center justify-between border-b border-gray-200 bg-gradient-to-r from-blue-50 via-white to-white px-6 py-5">
                    <div className="flex items-center gap-3">
                        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-100">
                            <Mail size={22} className="text-blue-700" />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-gray-900">Email Provider</h2>
                            <p className="text-sm text-gray-500">
                                {provider.name} {provider.email ? `· ${provider.email}` : ''}
                            </p>
                        </div>
                    </div>
                    <button onClick={onClose} className="rounded-xl p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600">
                        <X size={20} />
                    </button>
                </div>

                <div className="space-y-4 px-6 py-6">
                    {error ? (
                        <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                            <AlertCircle size={16} className="mt-0.5 shrink-0" />
                            <span>{error}</span>
                        </div>
                    ) : null}

                    {!provider.email ? (
                        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
                            This provider does not have an email address on file yet.
                        </div>
                    ) : null}

                    <div>
                        <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">
                            Subject <span className="text-red-500">*</span>
                        </label>
                        <input
                            value={subject}
                            onChange={(event) => setSubject(event.target.value)}
                            placeholder="e.g. Patient Referral Update"
                            disabled={!provider.email || isSending}
                            className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20 disabled:bg-gray-50"
                        />
                    </div>

                    <div>
                        <div className="mb-1.5 flex items-center justify-between gap-3">
                            <label className="block text-xs font-semibold uppercase tracking-wide text-gray-500">
                                Message <span className="text-red-500">*</span>
                            </label>
                            <span className="text-xs text-gray-400">{message.length} characters</span>
                        </div>
                        <textarea
                            rows={7}
                            value={message}
                            onChange={(event) => setMessage(event.target.value)}
                            placeholder="Write your message here..."
                            disabled={!provider.email || isSending}
                            className="w-full rounded-2xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20 disabled:bg-gray-50"
                        />
                    </div>

                    <div className="flex items-center justify-end gap-3 border-t border-gray-200 pt-4">
                        <button type="button" onClick={onClose} className="rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50">
                            Cancel
                        </button>
                        <button
                            type="button"
                            disabled={isSending || !provider.email || !subject.trim() || !message.trim()}
                            onClick={() => onSend(subject.trim(), message.trim())}
                            className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
                        >
                            {isSending ? <Loader2 size={16} className="animate-spin" /> : <Mail size={16} />}
                            Send Email
                        </button>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default function ProvidersPage() {
    const [providers, setProviders] = useState<ProviderRecord[]>([])
    const [stats, setStats] = useState<ProviderStats | null>(null)
    const [totalProviders, setTotalProviders] = useState(0)
    const [page, setPage] = useState(1)
    const [search, setSearch] = useState('')
    const [statusFilter, setStatusFilter] = useState('all')
    const [specialtyFilter, setSpecialtyFilter] = useState('all')
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [modalMode, setModalMode] = useState<'create' | 'edit'>('create')
    const [editingProviderId, setEditingProviderId] = useState<string | null>(null)
    const [formOpen, setFormOpen] = useState(false)
    const [form, setForm] = useState<ProviderFormState>(EMPTY_FORM)
    const [fieldErrors, setFieldErrors] = useState<Partial<Record<ProviderField, string>>>({})
    const [formError, setFormError] = useState<string | null>(null)
    const [isSaving, setIsSaving] = useState(false)
    const [detailProvider, setDetailProvider] = useState<ProviderRecord | null>(null)
    const [detailReferrals, setDetailReferrals] = useState<ProviderReferralLead[]>([])
    const [detailLoading, setDetailLoading] = useState(false)
    const [emailProvider, setEmailProvider] = useState<ProviderRecord | null>(null)
    const [emailError, setEmailError] = useState<string | null>(null)
    const [isEmailSending, setIsEmailSending] = useState(false)

    const totalPages = Math.max(1, Math.ceil(totalProviders / PAGE_SIZE))

    const fetchProviders = useCallback(async () => {
        setIsLoading(true)
        setError(null)
        try {
            const params: Record<string, unknown> = { page, page_size: PAGE_SIZE }
            if (search.trim()) params.search = search.trim()
            if (statusFilter !== 'all') params.status = statusFilter
            if (specialtyFilter !== 'all') params.specialty = specialtyFilter
            const [providersRes, statsRes] = await Promise.all([
                providersAPI.list(params),
                providersAPI.stats(),
            ])
            setProviders(providersRes.data?.items || [])
            setTotalProviders(providersRes.data?.total || 0)
            setStats(statsRes.data || null)
        } catch (err: any) {
            setError(err?.response?.data?.detail || 'Failed to load providers')
            setProviders([])
            setTotalProviders(0)
        } finally {
            setIsLoading(false)
        }
    }, [page, search, specialtyFilter, statusFilter])

    useEffect(() => {
        fetchProviders()
    }, [fetchProviders])

    useEffect(() => {
        setPage(1)
    }, [search, specialtyFilter, statusFilter])

    const openCreate = () => {
        setModalMode('create')
        setEditingProviderId(null)
        setForm(EMPTY_FORM)
        setFieldErrors({})
        setFormError(null)
        setFormOpen(true)
    }

    const openEdit = async (providerId: string) => {
        setModalMode('edit')
        setEditingProviderId(providerId)
        setFieldErrors({})
        setFormError(null)
        try {
            const response = await providersAPI.get(providerId)
            const provider = response.data as ProviderRecord
            setForm({
                name: provider.name || '',
                practice_name: provider.practice_name || '',
                email: provider.email || '',
                phone: provider.phone || '',
                specialty: provider.specialty || '',
                status: provider.status || 'pending',
                notes: provider.notes || '',
            })
            setFormOpen(true)
        } catch (err: any) {
            setError(err?.response?.data?.detail || 'Failed to load provider')
        }
    }

    const openDetails = async (providerId: string) => {
        setDetailLoading(true)
        try {
            const [providerRes, referralsRes] = await Promise.all([
                providersAPI.get(providerId),
                providersAPI.referrals(providerId, { limit: 50 }),
            ])
            setDetailProvider(providerRes.data)
            setDetailReferrals(referralsRes.data || [])
        } catch (err: any) {
            setError(err?.response?.data?.detail || 'Failed to load provider details')
        } finally {
            setDetailLoading(false)
        }
    }

    const handleFormChange = (key: keyof ProviderFormState, value: string) => {
        setForm((prev) => ({ ...prev, [key]: value }))
        const field = key as ProviderField
        if (fieldErrors[field]) {
            setFieldErrors((prev) => {
                const next = { ...prev }
                delete next[field]
                return next
            })
        }
        setFormError(null)
    }

    const validateForm = () => {
        const nextErrors: Partial<Record<ProviderField, string>> = {}
        if (!form.name.trim()) nextErrors.name = 'Provider name is required'
        const emailError = validateEmail(form.email)
        if (emailError) nextErrors.email = emailError
        const phoneError = validatePhone(form.phone)
        if (phoneError) nextErrors.phone = phoneError
        if (!form.specialty.trim()) nextErrors.specialty = 'Specialty is required'
        setFieldErrors(nextErrors)
        return Object.keys(nextErrors).length === 0
    }

    const handleSubmit = async (event: FormEvent) => {
        event.preventDefault()
        if (!validateForm()) return

        setIsSaving(true)
        setFormError(null)
        try {
            const payload = {
                name: form.name.trim(),
                practice_name: form.practice_name.trim() || undefined,
                email: form.email.trim() || undefined,
                phone: form.phone.trim() || undefined,
                specialty: form.specialty.trim(),
                status: form.status,
                notes: form.notes.trim() || undefined,
            }

            if (modalMode === 'create') {
                // Create returns the new ProviderResponse — prepend to current
                // page and refresh aggregate stats only. Do NOT refetch the full
                // table (that causes the whole list to flash a loading state
                // for a single-row change, which is a jarring UX regression).
                const response = await providersAPI.create(payload)
                const created = response?.data as ProviderRecord | undefined
                if (created?.id) {
                    setProviders((prev) => [created, ...prev.filter((p) => p.id !== created.id)])
                    setTotalProviders((prev) => prev + 1)
                }
                // Stats (counts, conversion rate) may have shifted — refresh quietly
                providersAPI.stats().then((res) => setStats(res.data || null)).catch(() => { })
            } else if (editingProviderId) {
                // Update returns the patched ProviderResponse — replace just
                // that one row in state. No full-table refetch.
                const response = await providersAPI.update(editingProviderId, payload)
                const updated = response?.data as ProviderRecord | undefined
                if (updated?.id) {
                    setProviders((prev) => prev.map((p) => (p.id === updated.id ? { ...p, ...updated } : p)))
                    // If the detail modal is showing this provider, update it in place too
                    if (detailProvider?.id === updated.id) {
                        setDetailProvider((prev) => (prev ? { ...prev, ...updated } : prev))
                    }
                }
                // Status changes can move the provider between active/pending/inactive
                // buckets — refresh stats in the background (non-blocking).
                providersAPI.stats().then((res) => setStats(res.data || null)).catch(() => { })
            }

            setFormOpen(false)
            setEditingProviderId(null)
        } catch (err: any) {
            const detail = err?.response?.data?.detail
            const message = typeof detail === 'string' ? detail : 'Failed to save provider'
            setFormError(message)
            if (message.toLowerCase().includes('email')) {
                setFieldErrors((prev) => ({ ...prev, email: message }))
            }
        } finally {
            setIsSaving(false)
        }
    }

    const handleSendProviderEmail = async (subject: string, message: string) => {
        if (!emailProvider) return
        setIsEmailSending(true)
        setEmailError(null)
        try {
            await providersAPI.sendEmail(emailProvider.id, { subject, message })
            setEmailProvider(null)
        } catch (err: any) {
            setEmailError(err?.response?.data?.detail || 'Failed to send provider email')
        } finally {
            setIsEmailSending(false)
        }
    }

    const kpis = [
        { label: 'Total Providers', value: stats?.total_providers ?? 0 },
        { label: 'Active Providers', value: stats?.active_providers ?? 0 },
        { label: 'Pending Verification', value: stats?.pending_providers ?? 0 },
        { label: 'Total Referrals', value: stats?.total_referrals ?? 0 },
        { label: 'Conversion Rate', value: `${stats?.overall_conversion_rate ?? 0}%` },
        { label: 'This Month', value: stats?.referrals_this_month ?? 0 },
    ]

    const visibleRange = useMemo(() => {
        if (totalProviders === 0) return 'Showing 0 providers'
        const start = (page - 1) * PAGE_SIZE + 1
        const end = Math.min(page * PAGE_SIZE, totalProviders)
        return `Showing ${start}-${end} of ${totalProviders} providers`
    }, [page, totalProviders])

    return (
        <div className="space-y-6 animate-fade-in">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-gray-900">
                        <Building2 className="h-6 w-6 text-sleep-500" />
                        Providers
                    </h1>
                    <p className="mt-1 text-[15px] text-gray-500">Manage referring providers, referral performance, and partner relationships.</p>
                </div>
                <div className="flex items-center gap-2">
                    <button onClick={fetchProviders} className="inline-flex items-center gap-2 rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50">
                        <RefreshCw size={16} />
                        Refresh
                    </button>
                    <div className="inline-flex items-center gap-1.5 rounded-lg bg-green-50 px-3 py-1.5 text-xs font-medium text-green-700">
                        <Shield className="h-3.5 w-3.5" />
                        HIPAA Protected
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-2 gap-4 xl:grid-cols-6">
                {kpis.map((card) => (
                    <div key={card.label} className="rounded-2xl border border-gray-100 bg-white p-4 shadow-sm">
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">{card.label}</p>
                        <p className="mt-2 text-2xl font-bold text-gray-900">{card.value}</p>
                    </div>
                ))}
            </div>

            <div className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-4 border-b border-gray-100 px-5 py-4">
                    <div>
                        <h2 className="text-base font-bold text-gray-900">Provider Directory</h2>
                        <p className="text-xs text-gray-500">Search, filter, review, and manage provider relationships.</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <div className="relative min-w-[250px]">
                            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                            <input
                                value={search}
                                onChange={(event) => setSearch(event.target.value)}
                                placeholder="Search providers"
                                className="w-full rounded-xl border border-gray-300 py-2.5 pl-10 pr-4 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                            />
                        </div>
                        <select
                            value={statusFilter}
                            onChange={(event) => setStatusFilter(event.target.value)}
                            className="rounded-xl border border-gray-300 px-4 py-2.5 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                        >
                            <option value="all">All Statuses</option>
                            <option value="active">Active</option>
                            <option value="pending">Pending Verification</option>
                            <option value="inactive">Inactive</option>
                            <option value="archived">Archived</option>
                        </select>
                        <select
                            value={specialtyFilter}
                            onChange={(event) => setSpecialtyFilter(event.target.value)}
                            className="rounded-xl border border-gray-300 px-4 py-2.5 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                        >
                            {SPECIALTY_OPTIONS.map((specialty) => (
                                <option key={specialty} value={specialty === 'All Specialties' ? 'all' : specialty}>
                                    {specialty}
                                </option>
                            ))}
                        </select>
                        <button onClick={openCreate} className="inline-flex items-center gap-2 rounded-xl bg-sleep-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-sleep-700">
                            <Plus size={16} />
                            Add Provider
                        </button>
                    </div>
                </div>

                {error ? (
                    <div className="mx-5 mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
                ) : null}

                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-gray-100 bg-gray-50/70">
                                <th className="px-5 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Provider</th>
                                <th className="px-4 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Practice</th>
                                <th className="px-4 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Specialty</th>
                                <th className="px-4 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Status</th>
                                <th className="px-4 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Referrals</th>
                                <th className="px-4 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Conversion</th>
                                <th className="px-4 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Last Referral</th>
                                <th className="px-5 py-3.5 text-right text-[11px] font-semibold uppercase tracking-wider text-gray-500">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading ? (
                                <tr>
                                    <td colSpan={8} className="px-5 py-16 text-center text-sm text-gray-400">
                                        <Loader2 size={18} className="mx-auto mb-3 animate-spin text-sleep-400" />
                                        Loading providers...
                                    </td>
                                </tr>
                            ) : providers.length === 0 ? (
                                <tr>
                                    <td colSpan={8} className="px-5 py-16 text-center">
                                        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-sleep-100 bg-sleep-50">
                                            <Building2 size={26} className="text-sleep-400" />
                                        </div>
                                        <h3 className="text-base font-semibold text-gray-900">No providers found</h3>
                                        <p className="mt-1 text-sm text-gray-400">Add a provider to start tracking referrals and conversions.</p>
                                    </td>
                                </tr>
                            ) : (
                                providers.map((provider) => (
                                    <tr key={provider.id} className="border-t border-gray-50 hover:bg-sleep-50/20">
                                        <td className="px-5 py-3.5">
                                            <div className="flex items-center gap-3">
                                                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sleep-50 font-semibold text-sleep-700">
                                                    {provider.name?.charAt(0)?.toUpperCase() || 'P'}
                                                </div>
                                                <div>
                                                    <p className="text-sm font-semibold text-gray-900">{provider.name}</p>
                                                    <p className="text-xs text-gray-500">{provider.email || provider.phone || 'No contact info'}</p>
                                                </div>
                                            </div>
                                        </td>
                                        <td className="px-4 py-3.5 text-sm text-gray-600">{provider.practice_name || '—'}</td>
                                        <td className="px-4 py-3.5 text-sm text-gray-600">{provider.specialty || '—'}</td>
                                        <td className="px-4 py-3.5">
                                            <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold capitalize ${statusBadge(provider.status)}`}>
                                                {provider.status}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3.5 text-sm font-semibold text-gray-900">{provider.total_referrals ?? 0}</td>
                                        <td className="px-4 py-3.5 text-sm text-gray-600">{provider.conversion_rate?.toFixed(1) ?? '0.0'}%</td>
                                        <td className="px-4 py-3.5 text-sm text-gray-500">{formatDate(provider.last_referral_at)}</td>
                                        <td className="px-5 py-3.5">
                                            <div className="flex items-center justify-end gap-1">
                                                <button onClick={() => openDetails(provider.id)} className="rounded-lg p-2 text-gray-400 transition-colors hover:bg-indigo-50 hover:text-indigo-600" title="View provider">
                                                    <Eye size={15} />
                                                </button>
                                                {provider.email ? (
                                                    <button onClick={() => { setEmailError(null); setEmailProvider(provider) }} className="rounded-lg p-2 text-gray-400 transition-colors hover:bg-blue-50 hover:text-blue-600" title="Email provider">
                                                        <Mail size={15} />
                                                    </button>
                                                ) : null}
                                                <button onClick={() => openEdit(provider.id)} className="rounded-lg p-2 text-gray-400 transition-colors hover:bg-sleep-50 hover:text-sleep-700" title="Edit provider">
                                                    <Edit3 size={15} />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-gray-100 px-5 py-3 text-xs text-gray-500">
                    <span>{visibleRange}</span>
                    <div className="flex items-center gap-2">
                        <button onClick={() => setPage((prev) => Math.max(1, prev - 1))} disabled={page <= 1} className="rounded-lg border border-gray-300 bg-white p-1.5 text-gray-500 transition-colors hover:bg-gray-50 disabled:opacity-40">
                            <ChevronLeft size={14} />
                        </button>
                        <span className="px-2 font-medium text-gray-700">Page {page} of {totalPages}</span>
                        <button onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))} disabled={page >= totalPages} className="rounded-lg border border-gray-300 bg-white p-1.5 text-gray-500 transition-colors hover:bg-gray-50 disabled:opacity-40">
                            <ChevronRight size={14} />
                        </button>
                    </div>
                </div>
            </div>

            <ProviderFormModal
                isOpen={formOpen}
                mode={modalMode}
                form={form}
                fieldErrors={fieldErrors}
                isSaving={isSaving}
                serverError={formError}
                onClose={() => setFormOpen(false)}
                onChange={handleFormChange}
                onSubmit={handleSubmit}
            />

            <ProviderDetailModal
                provider={detailProvider}
                referrals={detailReferrals}
                isLoading={detailLoading}
                onClose={() => setDetailProvider(null)}
                onEdit={() => {
                    if (!detailProvider) return
                    const providerId = detailProvider.id
                    setDetailProvider(null)
                    openEdit(providerId)
                }}
            />

            <ProviderEmailModal
                provider={emailProvider}
                isOpen={Boolean(emailProvider)}
                isSending={isEmailSending}
                error={emailError}
                onClose={() => {
                    setEmailProvider(null)
                    setEmailError(null)
                }}
                onSend={handleSendProviderEmail}
            />
        </div>
    )
}
