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
        HOT: 'bg-red-100 text-red-700 border border-red-200',
        MEDIUM: 'bg-amber-100 text-amber-700 border border-amber-200',
        LOW: 'bg-gray-100 text-gray-600 border border-gray-200',
    }
    return tone[priority?.toUpperCase()] || tone.LOW
}

function statusBadge(status: string) {
    const tone: Record<string, string> = {
        NEW: 'bg-blue-50 text-blue-700 border border-blue-200',
        CONTACTED: 'bg-indigo-50 text-indigo-700 border border-indigo-200',
        SCHEDULED: 'bg-emerald-50 text-emerald-700 border border-emerald-200',
        CONSULTATION_COMPLETE: 'bg-teal-50 text-teal-700 border border-teal-200',
        TREATMENT_STARTED: 'bg-green-50 text-green-700 border border-green-200',
        LOST: 'bg-gray-50 text-gray-600 border border-gray-200',
        DISQUALIFIED: 'bg-gray-50 text-gray-500 border border-gray-200',
    }
    return tone[status?.toUpperCase()] || 'bg-gray-50 text-gray-600 border border-gray-200'
}

function conditionLabel(lead: DeletedLead) {
    if (lead.conditions?.length) return lead.conditions.map((v) => v.replace(/_/g, ' ')).join(', ')
    if (lead.condition) return lead.condition.replace(/_/g, ' ')
    return '—'
}

function formatDateTime(value?: string) {
    if (!value) return '—'
    return new Date(value).toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })
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

    useEffect(() => { void fetchDeleted() }, [])

    const filteredLeads = useMemo(() => {
        const query = search.trim().toLowerCase()
        return leads.filter((lead) => {
            const matchesSearch = !query || [
                lead.lead_number, lead.first_name, lead.last_name, lead.email, lead.phone,
                lead.deleted_by, lead.referring_provider_name, conditionLabel(lead),
            ].filter(Boolean).some((v) => String(v).toLowerCase().includes(query))
            const matchesPriority = priorityFilter === 'all' || lead.priority?.toUpperCase() === priorityFilter
            const matchesStatus = statusFilter === 'all' || lead.status?.toUpperCase() === statusFilter
            return matchesSearch && matchesPriority && matchesStatus
        })
    }, [leads, priorityFilter, search, statusFilter])

    const removeLeadFromState = (leadId: string) => {
        setLeads((c) => c.filter((l) => l.id !== leadId))
        setTotal((c) => Math.max(0, c - 1))
    }

    const handleRestore = async (leadId: string) => {
        setRestoringId(leadId)
        try {
            await api.post(`/leads/${leadId}/restore`)
            removeLeadFromState(leadId)
            toast.success('Lead restored successfully')
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
            {/* Header */}
            <div className="shrink-0 space-y-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                        <h1 className="flex items-center gap-2.5 text-2xl font-bold tracking-tight text-gray-900">
                            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-red-50 border border-red-100">
                                <Trash2 className="h-[18px] w-[18px] text-red-500" />
                            </div>
                            Deleted Leads
                        </h1>
                        <p className="mt-1.5 ml-[46px] text-sm text-gray-500">
                            {total} deleted lead{total !== 1 ? 's' : ''} — Restore or permanently remove
                        </p>
                    </div>
                    <div className="flex items-center gap-2.5">
                        <button
                            onClick={() => void fetchDeleted()}
                            className="inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-sm font-medium text-gray-600 transition-all hover:bg-gray-50 hover:border-gray-300"
                        >
                            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                            Refresh
                        </button>
                    </div>
                </div>

                {/* Search + Filters bar */}
                <div className="rounded-2xl border border-gray-200 bg-white shadow-sm">
                    <div className="flex flex-wrap items-center gap-3 px-5 py-4">
                        <div className="relative flex-1 min-w-[240px]">
                            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                            <input
                                type="text"
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder="Search deleted leads..."
                                className="w-full rounded-xl border border-gray-200 bg-gray-50 py-2.5 pl-10 pr-4 text-sm text-gray-700 placeholder:text-gray-400 focus:border-sleep-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                            />
                            {search && (
                                <button onClick={() => setSearch('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                                    <X className="h-3.5 w-3.5" />
                                </button>
                            )}
                        </div>
                        <select
                            value={priorityFilter}
                            onChange={(e) => setPriorityFilter(e.target.value)}
                            className="rounded-xl border border-gray-200 bg-gray-50 px-3.5 py-2.5 text-sm text-gray-600 focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                        >
                            {PRIORITY_OPTIONS.map((o) => <option key={o} value={o}>{o === 'all' ? 'All Priorities' : o}</option>)}
                        </select>
                        <select
                            value={statusFilter}
                            onChange={(e) => setStatusFilter(e.target.value)}
                            className="rounded-xl border border-gray-200 bg-gray-50 px-3.5 py-2.5 text-sm text-gray-600 focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                        >
                            {STATUS_OPTIONS.map((o) => <option key={o} value={o}>{o === 'all' ? 'All Statuses' : labelize(o)}</option>)}
                        </select>
                        <div className="ml-auto flex items-center gap-2">
                            <span className="rounded-full bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-500">
                                {filteredLeads.length} of {total} leads
                            </span>
                            <div className="flex items-center gap-1.5 rounded-lg bg-emerald-50 border border-emerald-200 px-2.5 py-1.5">
                                <Shield className="h-3.5 w-3.5 text-emerald-600" />
                                <span className="text-[11px] font-semibold text-emerald-700">HIPAA</span>
                            </div>
                        </div>
                    </div>
                    {serverError && (
                        <div className="mx-5 mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                            {serverError}
                        </div>
                    )}
                </div>
            </div>

            {/* Table */}
            <div className="min-h-0 flex-1 overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
                {isLoading ? (
                    <div className="flex h-full items-center justify-center">
                        <div className="text-center">
                            <RefreshCw className="mx-auto mb-3 h-6 w-6 animate-spin text-gray-300" />
                            <p className="text-sm text-gray-400">Loading deleted leads...</p>
                        </div>
                    </div>
                ) : filteredLeads.length === 0 ? (
                    <div className="flex h-full items-center justify-center px-6">
                        <div className="max-w-sm text-center">
                            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-gray-100 bg-gray-50">
                                <Inbox className="h-7 w-7 text-gray-300" />
                            </div>
                            <h3 className="text-base font-semibold text-gray-900">No deleted leads</h3>
                            <p className="mt-1.5 text-sm text-gray-400">
                                {search || priorityFilter !== 'all' || statusFilter !== 'all'
                                    ? 'No deleted leads match your current filters.'
                                    : 'Soft-deleted leads will appear here with restore and permanent delete options.'}
                            </p>
                        </div>
                    </div>
                ) : (
                    <div className="flex h-full flex-col">
                        <div className="min-h-0 flex-1 overflow-auto" style={{ scrollbarGutter: 'stable both-edges' }}>
                            <table className="min-w-[1100px] w-full">
                                <thead className="sticky top-0 z-10 bg-gray-50/95 backdrop-blur">
                                    <tr className="border-b border-gray-200">
                                        <th className="w-[130px] px-5 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Lead #</th>
                                        <th className="px-4 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Patient</th>
                                        <th className="w-[140px] px-4 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Condition</th>
                                        <th className="w-[90px] px-4 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Priority</th>
                                        <th className="w-[120px] px-4 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Status</th>
                                        <th className="w-[140px] px-4 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Created</th>
                                        <th className="w-[160px] px-4 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Deleted</th>
                                        <th className="w-[240px] px-5 py-3.5 text-right text-[11px] font-semibold uppercase tracking-wider text-gray-500">Actions</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100">
                                    {filteredLeads.map((lead) => (
                                        <tr key={lead.id} className="transition-colors hover:bg-gray-50/60">
                                            <td className="px-5 py-4">
                                                <span className="text-xs font-mono font-semibold text-gray-500">{lead.lead_number || '—'}</span>
                                            </td>
                                            <td className="px-4 py-4">
                                                <div className="flex items-center gap-3">
                                                    <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-gray-100">
                                                        <span className="text-xs font-semibold text-gray-500">
                                                            {(lead.first_name || '?').charAt(0)}{(lead.last_name || '').charAt(0)}
                                                        </span>
                                                    </div>
                                                    <div className="min-w-0">
                                                        <p className="text-sm font-semibold text-gray-900 truncate">
                                                            {lead.first_name} {lead.last_name || ''}
                                                        </p>
                                                        {lead.email && (
                                                            <p className="text-xs text-gray-400 truncate">{lead.email}</p>
                                                        )}
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="px-4 py-4">
                                                <span className="text-sm text-gray-600 capitalize">{conditionLabel(lead)}</span>
                                            </td>
                                            <td className="px-4 py-4">
                                                <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold ${priorityBadge(lead.priority)}`}>
                                                    {lead.priority}
                                                </span>
                                            </td>
                                            <td className="px-4 py-4">
                                                <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium ${statusBadge(lead.status)}`}>
                                                    {labelize(lead.status)}
                                                </span>
                                            </td>
                                            <td className="px-4 py-4">
                                                <span className="text-xs text-gray-500">{formatDateTime(lead.created_at)}</span>
                                            </td>
                                            <td className="px-4 py-4">
                                                <div>
                                                    <span className="text-xs text-gray-500">{formatDateTime(lead.deleted_at)}</span>
                                                    <p className="text-[11px] text-gray-400 mt-0.5">{lead.deleted_by || 'Administrator'}</p>
                                                </div>
                                            </td>
                                            <td className="px-5 py-4">
                                                <div className="flex items-center justify-end gap-2">
                                                    <button
                                                        onClick={() => void handleRestore(lead.id)}
                                                        disabled={restoringId === lead.id}
                                                        className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-all hover:border-sleep-300 hover:bg-sleep-50 hover:text-sleep-700 disabled:cursor-not-allowed disabled:opacity-50"
                                                    >
                                                        {restoringId === lead.id
                                                            ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                                            : <RotateCcw className="h-3.5 w-3.5" />}
                                                        Restore
                                                    </button>
                                                    <button
                                                        onClick={() => setConfirmDeleteLead(lead)}
                                                        className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-600 transition-all hover:bg-red-50 hover:border-red-300"
                                                    >
                                                        <Trash2 className="h-3.5 w-3.5" />
                                                        Delete Forever
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        <div className="shrink-0 flex items-center justify-between border-t border-gray-100 px-5 py-3">
                            <span className="text-xs text-gray-400">
                                Deleted leads are recoverable until permanently removed. All actions are audit-logged.
                            </span>
                        </div>
                    </div>
                )}
            </div>

            {/* Permanent Delete Confirmation Modal */}
            {confirmDeleteLead && (
                <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4" onClick={() => setConfirmDeleteLead(null)}>
                    <div className="w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
                        <div className="px-6 pt-6 pb-2">
                            <div className="flex items-center gap-3 mb-4">
                                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-100">
                                    <AlertTriangle className="h-5 w-5 text-red-600" />
                                </div>
                                <div>
                                    <h2 className="text-lg font-bold text-gray-900">Permanently delete?</h2>
                                    <p className="text-sm text-gray-500">
                                        {confirmDeleteLead.first_name} {confirmDeleteLead.last_name || ''} ({confirmDeleteLead.lead_number})
                                    </p>
                                </div>
                            </div>
                            <div className="rounded-xl bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-700">
                                This cannot be undone. The lead, notes, and attachments will be permanently erased.
                            </div>
                        </div>
                        <div className="flex items-center justify-end gap-3 px-6 py-5">
                            <button
                                onClick={() => setConfirmDeleteLead(null)}
                                className="rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-sm font-medium text-gray-600 hover:bg-gray-50"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={() => void handlePermanentDelete()}
                                disabled={deletingId === confirmDeleteLead.id}
                                className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60"
                            >
                                {deletingId === confirmDeleteLead.id
                                    ? <Loader2 className="h-4 w-4 animate-spin" />
                                    : <Trash2 className="h-4 w-4" />}
                                Delete Forever
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
