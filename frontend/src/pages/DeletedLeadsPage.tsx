import { useEffect, useState, useMemo } from 'react'
import {
    Trash2, Search, Shield, RotateCcw, XCircle,
    RefreshCw, Inbox, AlertTriangle, Eye
} from 'lucide-react'
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
    is_referral?: boolean
    referring_provider_name?: string
}

function priorityBadge(p: string) {
    const m: Record<string, string> = {
        HOT: 'bg-red-50 text-red-700 ring-1 ring-red-200',
        MEDIUM: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
        LOW: 'bg-gray-50 text-gray-600 ring-1 ring-gray-200',
    }
    return m[p?.toUpperCase()] || m.LOW
}

function condLabel(l: DeletedLead) {
    if (l.conditions?.length) return l.conditions.map(c => c.replace(/_/g, ' ')).join(', ')
    if (l.condition) return l.condition.replace(/_/g, ' ')
    return '—'
}

function fmtDate(d?: string) {
    return d ? new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'
}

export default function DeletedLeadsPage() {
    const [leads, setLeads] = useState<DeletedLead[]>([])
    const [search, setSearch] = useState('')
    const [isLoading, setIsLoading] = useState(true)
    const [total, setTotal] = useState(0)
    const [restoringId, setRestoringId] = useState<string | null>(null)

    const fetchDeleted = () => {
        setIsLoading(true)
        api.get('/leads/deleted', { params: { page_size: 200 } })
            .then(r => {
                setLeads(r.data?.items || [])
                setTotal(r.data?.total || 0)
            })
            .catch(() => setLeads([]))
            .finally(() => setIsLoading(false))
    }

    useEffect(() => { fetchDeleted() }, [])

    const handleRestore = async (id: string) => {
        setRestoringId(id)
        try {
            await api.post(`/leads/${id}/restore`)
            setLeads(prev => prev.filter(l => l.id !== id))
            setTotal(prev => prev - 1)
        } catch { }
        setRestoringId(null)
    }

    const filtered = useMemo(() => {
        if (!search.trim()) return leads
        const s = search.toLowerCase()
        return leads.filter(l =>
            l.lead_number?.toLowerCase().includes(s) ||
            l.first_name?.toLowerCase().includes(s) ||
            l.last_name?.toLowerCase().includes(s) ||
            l.email?.toLowerCase().includes(s)
        )
    }, [leads, search])

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 tracking-tight flex items-center gap-2">
                        <Trash2 className="w-6 h-6 text-sleep-500" />
                        Deleted Leads
                    </h1>
                    <p className="text-gray-500 mt-1 text-[15px]">View and restore soft-deleted patient leads</p>
                </div>
                <div className="flex items-center gap-3">
                    <button
                        onClick={fetchDeleted}
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-gray-200 text-gray-600 text-sm font-medium hover:bg-gray-50 transition-colors"
                    >
                        <RefreshCw className="w-4 h-4" /> Refresh
                    </button>
                    <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-50 text-green-700 text-xs font-medium">
                        <Shield className="w-3.5 h-3.5" /> HIPAA Protected
                    </div>
                </div>
            </div>

            {/* Info Banner */}
            <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-600 mt-0.5 shrink-0" />
                <div>
                    <p className="text-sm font-medium text-amber-800">Deleted leads are retained for compliance</p>
                    <p className="text-sm text-amber-600 mt-0.5">Soft-deleted leads can be restored. Permanent deletion requires admin authorization and is logged for HIPAA audit trails.</p>
                </div>
            </div>

            {/* Search */}
            <div className="bg-white rounded-2xl border border-gray-100 shadow-premium p-4">
                <div className="relative max-w-md">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                        type="text"
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        placeholder="Search deleted leads..."
                        className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-sleep-500/20 focus:border-sleep-500"
                    />
                </div>
            </div>

            {/* Table */}
            <div className="bg-white rounded-2xl border border-gray-100 shadow-premium overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-gray-100">
                                <th className="text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-5 py-3.5 bg-gray-50/60">Lead ID</th>
                                <th className="text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-4 py-3.5 bg-gray-50/60">Patient</th>
                                <th className="text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-4 py-3.5 bg-gray-50/60">Condition</th>
                                <th className="text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-4 py-3.5 bg-gray-50/60">Priority</th>
                                <th className="text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-4 py-3.5 bg-gray-50/60">Original Status</th>
                                <th className="text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-4 py-3.5 bg-gray-50/60">Submitted</th>
                                <th className="text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-4 py-3.5 bg-gray-50/60">Deleted On</th>
                                <th className="text-right text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-5 py-3.5 bg-gray-50/60">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading ? (
                                <tr>
                                    <td colSpan={8} className="text-center py-16">
                                        <RefreshCw className="w-6 h-6 text-sleep-400 animate-spin mx-auto mb-3" />
                                        <p className="text-sm text-gray-400">Loading deleted leads...</p>
                                    </td>
                                </tr>
                            ) : filtered.length === 0 ? (
                                <tr>
                                    <td colSpan={8} className="text-center py-16">
                                        <div className="w-14 h-14 rounded-2xl bg-green-50 border border-green-100 flex items-center justify-center mx-auto mb-4">
                                            <Inbox className="w-7 h-7 text-green-400" />
                                        </div>
                                        <h3 className="text-base font-semibold text-gray-900 mb-1">No deleted leads</h3>
                                        <p className="text-sm text-gray-400 max-w-sm mx-auto">
                                            Great news! There are no deleted leads at this time. Leads that are soft-deleted will appear here for review.
                                        </p>
                                    </td>
                                </tr>
                            ) : filtered.map(lead => (
                                <tr key={lead.id} className="border-t border-gray-50 hover:bg-red-50/20 transition-colors duration-100 group">
                                    <td className="px-5 py-3.5">
                                        <span className="text-xs font-mono font-semibold text-gray-500">{lead.lead_number || '—'}</span>
                                    </td>
                                    <td className="px-4 py-3.5">
                                        <p className="text-sm font-medium text-gray-700">{lead.first_name} {lead.last_name || ''}</p>
                                        {lead.email && <p className="text-xs text-gray-400">{lead.email}</p>}
                                        {lead.is_referral && (
                                            <span className="text-[10px] text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded-full font-medium">
                                                Referral{lead.referring_provider_name ? ` — ${lead.referring_provider_name}` : ''}
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-4 py-3.5">
                                        <span className="text-sm text-gray-600 capitalize">{condLabel(lead)}</span>
                                    </td>
                                    <td className="px-4 py-3.5">
                                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold ${priorityBadge(lead.priority)}`}>
                                            {lead.priority}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3.5">
                                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-gray-100 text-gray-500">
                                            {lead.status?.replace(/_/g, ' ')}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3.5 text-sm text-gray-500">{fmtDate(lead.created_at)}</td>
                                    <td className="px-4 py-3.5 text-sm text-red-400">{fmtDate(lead.deleted_at)}</td>
                                    <td className="px-5 py-3.5 text-right">
                                        <div className="flex items-center justify-end gap-1.5">
                                            <button
                                                className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"
                                                title="View Details"
                                            >
                                                <Eye className="w-3.5 h-3.5" />
                                            </button>
                                            <button
                                                onClick={() => handleRestore(lead.id)}
                                                disabled={restoringId === lead.id}
                                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sleep-50 text-sleep-700 text-xs font-medium hover:bg-sleep-100 transition-colors disabled:opacity-50"
                                                title="Restore Lead"
                                            >
                                                <RotateCcw className={`w-3.5 h-3.5 ${restoringId === lead.id ? 'animate-spin' : ''}`} />
                                                Restore
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                <div className="px-5 py-3 border-t border-gray-100 flex items-center justify-between text-xs text-gray-400">
                    <span>{filtered.length} of {total} deleted leads</span>
                    <span className="flex items-center gap-1.5"><Shield className="w-3 h-3" /> HIPAA-compliant audit trail</span>
                </div>
            </div>
        </div>
    )
}
