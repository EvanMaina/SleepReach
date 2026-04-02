import { useEffect, useMemo, useState } from 'react'
import {
    AlertTriangle,
    Inbox,
    Loader2,
    RefreshCw,
    RotateCcw,
    Search,
    Shield,
    Trash2,
    X,
} from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../lib/api'

interface DeletedLead {
    id: string
    lead_number: string
    first_name: string
    last_name?: string
    email?: string
    phone?: string
    condition?: string
    conditions?: string[]
    priority: string
    status: string
    created_at: string
    deleted_at?: string
    deleted_by?: string
    is_referral?: boolean
    referring_provider_name?: string
}

const PRIORITY_OPTIONS = ['all', 'HOT', 'MEDIUM', 'LOW']
const STATUS_OPTIONS = ['all', 'NEW', 'CONTACTED', 'SCHEDULED', 'CONSULTATION_COMPLETE', 'TREATMENT_STARTED', 'LOST', 'DISQUALIFIED']

function priorityBadge(priority: string) {
    const tone: Record<string, string> = {
        HOT: 'bg-red-50 text-red-700 ring-1 ring-red-200',
        MEDIUM: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
        LOW: 'bg-gray-50 text-gray-600 ring-1 ring-gray-200',
    }
    return tone[priority?.toUpperCase()] || tone.LOW
}

function conditionLabel(lead: DeletedLead) {
    if (lead.conditions?.length) {
        return lead.conditions.map((value) => value.replace(/_/g, ' ')).join(', ')
    }
    if (lead.condition) return lead.condition.replace(/_/g, ' ')
    return '—'
}

function formatDateTime(value?: string) {
    if (!value) return '—'
    return new Date(value).toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
    })
}

function labelize(value?: string) {
    if (!value) return '—'
    return value.replace(/_/g, ' ')
}

export default function DeletedLeadsPage() {
    const [leads, setLeads] = useState<DeletedLead[]>([])
    const [search, setSearch] = useState('')
    const [priorityFilter, setPriorityFilter] = useState('all')
    const [statusFilter, setStatusFilter] = useState('all')
    const [isLoading, setIsLoading] = useState(true)
    const [serverError, setServerError] = useState<string | null>(null)
    const [total, setTotal] = useState(0)
    const [restoringId, setRestoringId] = useState<string | null>(null)
    const [deletingId, setDeletingId] = useState<string | null>(null)
    const [confirmDeleteLead, setConfirmDeleteLead] = useState<DeletedLead | null>(null)

    const fetchDeleted = async () => {
        setIsLoading(true)
        setServerError(null)
        try {
            const response = await api.get('/leads/deleted', { params: { page_size: 200 } })
            setLeads(response.data?.items || [])
            setTotal(response.data?.total || 0)
        } catch (error: any) {
            setLeads([])
            setServerError(error?.response?.data?.detail || 'Unable to load deleted leads right now.')
        } finally {
            setIsLoading(false)
        }
    }

    useEffect(() => {
        void fetchDeleted()
    }, [])

    const filteredLeads = useMemo(() => {
        const query = search.trim().toLowerCase()
        return leads.filter((lead) => {
            const matchesSearch = !query || [
                lead.lead_number,
                lead.first_name,
                lead.last_name,
                lead.email,
                lead.phone,
                lead.deleted_by,
                lead.referring_provider_name,
                conditionLabel(lead),
            ]
                .filter(Boolean)
                .some((value) => String(value).toLowerCase().includes(query))

            const matchesPriority =
                priorityFilter === 'all' || lead.priority?.toUpperCase() === priorityFilter
            const matchesStatus =
                statusFilter === 'all' || lead.status?.toUpperCase() === statusFilter

            return matchesSearch && matchesPriority && matchesStatus
        })
    }, [leads, priorityFilter, search, statusFilter])

    const removeLeadFromState = (leadId: string) => {
        setLeads((current) => current.filter((lead) => lead.id !== leadId))
        setTotal((current) => Math.max(0, current - 1))
    }

    const handleRestore = async (leadId: string) => {
        setRestoringId(leadId)
        try {
            await api.post(`/leads/${leadId}/restore`)
            removeLeadFromState(leadId)
            toast.success('Lead restored')
        } catch (error: any) {
            toast.error(error?.response?.data?.detail || 'Failed to restore lead')
        } finally {
            setRestoringId(null)
        }
    }

    const handlePermanentDelete = async () => {
        if (!confirmDeleteLead) return
        setDeletingId(confirmDeleteLead.id)
        try {
            await api.delete(`/leads/${confirmDeleteLead.id}/permanent`)
            removeLeadFromState(confirmDeleteLead.id)
            toast.success('Lead permanently deleted')
            setConfirmDeleteLead(null)
        } catch (error: any) {
            toast.error(error?.response?.data?.detail || 'Failed to permanently delete lead')
        } finally {
            setDeletingId(null)
        }
    }

    return (
        <div className="flex h-full min-h-0 flex-col gap-5 overflow-hidden animate-fade-in">
            <div className="shrink-0 space-y-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-gray-900">
                            <Trash2 className="h-6 w-6 text-sleep-500" />
                            Deleted Leads
                        </h1>
                        <p className="mt-1 text-[15px] text-gray-500">
                            Recover soft-deleted leads or permanently remove them with a full audit trail.
                        </p>
                    </div>
                    <div className="flex items-center gap-3">
                        <button
                            onClick={() => void fetchDeleted()}
                            className="inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
                        >
                            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                            Refresh
                        </button>
                        <div className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700">
                            <Shield className="h-3.5 w-3.5" />
                            HIPAA Protected
                        </div>
                    </div>
                </div>

                <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-4">
                    <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
                    <div className="space-y-1">
                        <p className="text-sm font-semibold text-amber-900">
                            Deleted leads stay recoverable until you permanently remove them.
                        </p>
                        <p className="text-sm text-amber-800">
                            Restore returns the lead to its original workflow state. Permanent deletion cannot be undone and is logged for audit review.
                        </p>
                    </div>
                </div>

                <div className="rounded-2xl border border-gray-100 bg-white p-4 shadow-sm">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="flex flex-wrap items-center gap-3">
                            <div className="relative min-w-[280px] flex-1">
                                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                                <input
                                    type="text"
                                    value={search}
                                    onChange={(event) => setSearch(event.target.value)}
                                    placeholder="Search lead number, patient, email, phone, or deleted by..."
                                    className="w-full rounded-xl border border-gray-300 bg-white py-2.5 pl-10 pr-4 text-sm text-gray-700 focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                                />
                            </div>
                            <select
                                value={priorityFilter}
                                onChange={(event) => setPriorityFilter(event.target.value)}
                                className="rounded-xl border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-700 focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                            >
                                {PRIORITY_OPTIONS.map((option) => (
                                    <option key={option} value={option}>
                                        {option === 'all' ? 'All Priorities' : option}
                                    </option>
                                ))}
                            </select>
                            <select
                                value={statusFilter}
                                onChange={(event) => setStatusFilter(event.target.value)}
                                className="rounded-xl border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-700 focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                            >
                                {STATUS_OPTIONS.map((option) => (
                                    <option key={option} value={option}>
                                        {option === 'all' ? 'All Statuses' : labelize(option)}
                                    </option>
                                ))}
                            </select>
                        </div>

                        <div className="rounded-full bg-gray-100 px-3 py-1.5 text-sm text-gray-600">
                            {filteredLeads.length} of {total} deleted leads
                        </div>
                    </div>
                    {serverError ? (
                        <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                            {serverError}
                        </div>
                    ) : null}
                </div>
            </div>

            <div className="min-h-0 flex-1 overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
                {isLoading ? (
                    <div className="flex h-full items-center justify-center">
                        <div className="text-center">
                            <RefreshCw className="mx-auto mb-3 h-6 w-6 animate-spin text-sleep-400" />
                            <p className="text-sm text-gray-400">Loading deleted leads...</p>
                        </div>
                    </div>
                ) : filteredLeads.length === 0 ? (
                    <div className="flex h-full items-center justify-center px-6">
                        <div className="max-w-md text-center">
                            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-green-100 bg-green-50">
                                <Inbox className="h-7 w-7 text-green-400" />
                            </div>
                            <h3 className="text-base font-semibold text-gray-900">No deleted leads</h3>
                            <p className="mt-1 text-sm text-gray-400">
                                Soft-deleted leads will appear here with restore and permanent delete controls.
                            </p>
                        </div>
                    </div>
                ) : (
                    <>
                        <div className="min-h-0 flex-1 overflow-auto" style={{ scrollbarGutter: 'stable both-edges' }}>
                            <table className="min-w-[1180px] w-full">
                                <thead className="sticky top-0 z-10 bg-gray-50/95 backdrop-blur">
                                    <tr className="border-b border-gray-200">
                                        <th className="px-5 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Lead ID</th>
                                        <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Patient</th>
                                        <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Condition</th>
                                        <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Priority</th>
                                        <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Previous Status</th>
                                        <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Deleted On</th>
                                        <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Deleted By</th>
                                        <th className="px-5 py-3 text-right text-[11px] font-semibold uppercase tracking-wider text-gray-500">Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredLeads.map((lead) => (
                                        <tr key={lead.id} className="border-b border-gray-100 transition-colors hover:bg-red-50/20">
                                            <td className="px-5 py-3.5">
                                                <span className="text-xs font-semibold text-gray-500">{lead.lead_number || '—'}</span>
                                            </td>
                                            <td className="px-4 py-3.5">
                                                <div className="space-y-1">
                                                    <p className="text-sm font-semibold text-gray-900">
                                                        {lead.first_name} {lead.last_name || ''}
                                                    </p>
                                                    <div className="space-y-0.5 text-xs text-gray-500">
                                                        {lead.email ? <p>{lead.email}</p> : null}
                                                        {lead.phone ? <p>{lead.phone}</p> : null}
                                                        {lead.is_referral ? (
                                                            <span className="inline-flex items-center rounded-full bg-indigo-50 px-2 py-0.5 font-medium text-indigo-700">
                                                                Ref: {lead.referring_provider_name || 'Provider'}
                                                            </span>
                                                        ) : null}
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="px-4 py-3.5 text-sm text-gray-700">
                                                {conditionLabel(lead)}
                                            </td>
                                            <td className="px-4 py-3.5">
                                                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${priorityBadge(lead.priority)}`}>
                                                    {lead.priority}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3.5">
                                                <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600">
                                                    {labelize(lead.status)}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3.5 text-sm text-gray-600">
                                                {formatDateTime(lead.deleted_at)}
                                            </td>
                                            <td className="px-4 py-3.5 text-sm text-gray-600">
                                                {lead.deleted_by || 'Administrator'}
                                            </td>
                                            <td className="px-5 py-3.5">
                                                <div className="flex items-center justify-end gap-2">
                                                    <button
                                                        onClick={() => void handleRestore(lead.id)}
                                                        disabled={restoringId === lead.id}
                                                        className="inline-flex items-center gap-2 rounded-xl border border-sleep-200 bg-sleep-50 px-3 py-2 text-xs font-semibold text-sleep-700 transition-colors hover:bg-sleep-100 disabled:cursor-not-allowed disabled:opacity-60"
                                                    >
                                                        {restoringId === lead.id ? (
                                                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                                        ) : (
                                                            <RotateCcw className="h-3.5 w-3.5" />
                                                        )}
                                                        Restore
                                                    </button>
                                                    <button
                                                        onClick={() => setConfirmDeleteLead(lead)}
                                                        className="inline-flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 transition-colors hover:bg-red-100"
                                                    >
                                                        <Trash2 className="h-3.5 w-3.5" />
                                                        Permanently Delete
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        <div className="shrink-0 border-t border-gray-100 px-5 py-3 text-xs text-gray-500">
                            Deleted leads are recoverable until permanently removed. Every action is logged for audit review.
                        </div>
                    </>
                )}
            </div>

            {confirmDeleteLead ? (
                <div
                    className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-4"
                    onClick={() => setConfirmDeleteLead(null)}
                >
                    <div
                        className="w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-2xl"
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="flex items-start justify-between border-b border-gray-200 px-6 py-5">
                            <div className="space-y-1">
                                <h2 className="text-lg font-bold text-gray-900">Permanently delete lead?</h2>
                                <p className="text-sm text-gray-500">
                                    {confirmDeleteLead.first_name} {confirmDeleteLead.last_name || ''} ({confirmDeleteLead.lead_number})
                                </p>
                            </div>
                            <button
                                onClick={() => setConfirmDeleteLead(null)}
                                className="rounded-xl p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                            >
                                <X className="h-5 w-5" />
                            </button>
                        </div>
                        <div className="space-y-4 px-6 py-5">
                            <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-4 text-sm text-red-700">
                                This action cannot be undone. The lead, related notes, and attachment records will be permanently removed.
                            </div>
                            <div className="flex items-center justify-end gap-3">
                                <button
                                    onClick={() => setConfirmDeleteLead(null)}
                                    className="rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={() => void handlePermanentDelete()}
                                    disabled={deletingId === confirmDeleteLead.id}
                                    className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
                                >
                                    {deletingId === confirmDeleteLead.id ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                        <Trash2 className="h-4 w-4" />
                                    )}
                                    Permanently Delete
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            ) : null}
        </div>
    )
}
