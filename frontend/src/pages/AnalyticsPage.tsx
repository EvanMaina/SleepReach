import { useEffect, useState } from 'react'
import {
    BarChart3, Shield, TrendingUp, Users, Flame, CalendarCheck,
    Trophy, ArrowUpRight, ArrowDownRight, Globe, FileText, UserPlus,
    RefreshCw, Zap
} from 'lucide-react'
import api from '../lib/api'

interface PlatformData {
    platform: string
    total_leads: number
    hot_leads: number
    converted_leads: number
    conversion_rate: number
    scheduled_leads: number
    avg_score: number
    color: string
    icon: string
    trend: number
    has_data: boolean
}

interface SourceOverview {
    platforms: PlatformData[]
    totals: {
        total_leads: number
        hot_leads: number
        converted_leads: number
        scheduled_leads: number
        overall_conversion_rate: number
    }
    top_performing: string
}

const platformIcons: Record<string, any> = {
    widget: Globe,
    jotform: FileText,
    referral: UserPlus,
}

const platformColors: Record<string, { bg: string; text: string; border: string; gradient: string; bar: string }> = {
    widget: { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200', gradient: 'from-[#4A6FA5] to-[#6593be]', bar: 'bg-blue-500' },
    jotform: { bg: 'bg-purple-50', text: 'text-purple-700', border: 'border-purple-200', gradient: 'from-[#7c3aed] to-[#a78bfa]', bar: 'bg-purple-500' },
    referral: { bg: 'bg-teal-50', text: 'text-teal-700', border: 'border-teal-200', gradient: 'from-[#26a9b5] to-[#41c5cf]', bar: 'bg-teal-500' },
}

const daysOptions = [7, 14, 30, 60, 90]

export default function AnalyticsPage() {
    const [data, setData] = useState<SourceOverview | null>(null)
    const [hotLeads, setHotLeads] = useState<any>(null)
    const [daysBack, setDaysBack] = useState(30)
    const [isLoading, setIsLoading] = useState(true)

    useEffect(() => {
        setIsLoading(true)
        Promise.all([
            api.get('/analytics/sources/overview', { params: { days_back: daysBack } }),
            api.get('/analytics/sources/hot-leads', { params: { days_back: daysBack } }),
        ])
            .then(([overviewRes, hotRes]) => {
                setData(overviewRes.data)
                setHotLeads(hotRes.data)
            })
            .catch(() => { })
            .finally(() => setIsLoading(false))
    }, [daysBack])

    const platforms = data?.platforms?.filter(p =>
        ['widget', 'jotform', 'referral'].includes(p.platform?.toLowerCase())
    ) || []

    const totals = data?.totals
    const topPerforming = data?.top_performing

    const kpis = [
        { label: 'Total Leads', value: totals?.total_leads ?? 0, icon: Users, gradient: 'from-[#4A6FA5] to-[#6593be]' },
        { label: 'Hot Leads', value: totals?.hot_leads ?? 0, icon: Flame, gradient: 'from-[#dc2626] to-[#f87171]' },
        { label: 'Converted', value: totals?.converted_leads ?? 0, icon: CalendarCheck, gradient: 'from-[#26a9b5] to-[#41c5cf]' },
        { label: 'Conversion Rate', value: totals?.overall_conversion_rate ? `${totals.overall_conversion_rate.toFixed(1)}%` : '—', icon: TrendingUp, gradient: 'from-[#EE9A1D] to-[#f2b034]' },
        { label: 'Scheduled', value: totals?.scheduled_leads ?? 0, icon: CalendarCheck, gradient: 'from-[#344d72] to-[#4A6FA5]' },
    ]

    const maxLeads = Math.max(...platforms.map(p => p.total_leads), 1)

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 tracking-tight flex items-center gap-2">
                        <BarChart3 className="w-6 h-6 text-sleep-500" />
                        Source Analytics
                    </h1>
                    <p className="text-gray-500 mt-1 text-[15px]">Lead performance by intake source — Widget, Jotform, and Referral</p>
                </div>
                <div className="flex items-center gap-3">
                    {/* Days selector */}
                    <div className="flex items-center gap-1 p-1 rounded-lg bg-gray-100">
                        {daysOptions.map(d => (
                            <button
                                key={d}
                                onClick={() => setDaysBack(d)}
                                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${daysBack === d ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
                            >
                                {d}d
                            </button>
                        ))}
                    </div>
                    <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-50 text-green-700 text-xs font-medium">
                        <Shield className="w-3.5 h-3.5" /> HIPAA Protected
                    </div>
                </div>
            </div>

            {isLoading ? (
                <div className="flex items-center justify-center py-24">
                    <div className="text-center">
                        <RefreshCw className="w-8 h-8 text-sleep-400 animate-spin mx-auto mb-3" />
                        <p className="text-sm text-gray-400">Loading analytics...</p>
                    </div>
                </div>
            ) : (
                <>
                    {/* KPI Cards */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-4">
                        {kpis.map(c => (
                            <div key={c.label} className={`relative overflow-hidden rounded-2xl p-4 bg-gradient-to-br ${c.gradient} text-white shadow-md hover:shadow-lg transition-all duration-300 hover:-translate-y-0.5`}>
                                <div className="absolute top-0 right-0 w-16 h-16 rounded-full bg-white/10 -translate-y-4 translate-x-4" />
                                <div className="relative z-10">
                                    <c.icon className="w-5 h-5 text-white/80 mb-2" />
                                    <p className="text-white/70 text-[10px] font-medium uppercase tracking-wider mb-0.5">{c.label}</p>
                                    <p className="text-xl font-bold">{c.value}</p>
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* Leads by Platform */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                        {platforms.map(p => {
                            const colors = platformColors[p.platform?.toLowerCase()] || platformColors.widget
                            const Icon = platformIcons[p.platform?.toLowerCase()] || Globe
                            const isTop = p.platform?.toLowerCase() === topPerforming?.toLowerCase()
                            return (
                                <div key={p.platform} className={`bg-white rounded-2xl border shadow-premium p-5 transition-all duration-200 hover:shadow-premium-lg ${isTop ? 'border-warm-300 ring-1 ring-warm-200' : 'border-gray-100'}`}>
                                    {isTop && (
                                        <div className="flex items-center gap-1.5 mb-3">
                                            <Trophy className="w-4 h-4 text-warm-500" />
                                            <span className="text-xs font-semibold text-warm-600 uppercase tracking-wider">Top Performer</span>
                                        </div>
                                    )}
                                    <div className="flex items-center gap-3 mb-4">
                                        <div className={`w-10 h-10 rounded-xl ${colors.bg} flex items-center justify-center`}>
                                            <Icon className={`w-5 h-5 ${colors.text}`} />
                                        </div>
                                        <div>
                                            <h3 className="text-base font-semibold text-gray-900 capitalize">{p.platform}</h3>
                                            {p.trend != null && p.trend !== 0 && (
                                                <div className={`flex items-center gap-0.5 text-xs font-medium ${p.trend > 0 ? 'text-green-600' : 'text-red-500'}`}>
                                                    {p.trend > 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                                                    {Math.abs(p.trend).toFixed(0)}% vs prev period
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                    <div className="space-y-3">
                                        <div className="flex items-center justify-between">
                                            <span className="text-sm text-gray-500">Total Leads</span>
                                            <span className="text-lg font-bold text-gray-900">{p.total_leads}</span>
                                        </div>
                                        <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                                            <div className={`h-full ${colors.bar} rounded-full transition-all duration-500`} style={{ width: `${(p.total_leads / maxLeads) * 100}%` }} />
                                        </div>
                                        <div className="grid grid-cols-3 gap-2 pt-2">
                                            <div className="text-center p-2 rounded-lg bg-gray-50">
                                                <p className="text-xs text-gray-400 mb-0.5">Hot</p>
                                                <p className="text-sm font-bold text-red-600">{p.hot_leads}</p>
                                            </div>
                                            <div className="text-center p-2 rounded-lg bg-gray-50">
                                                <p className="text-xs text-gray-400 mb-0.5">Converted</p>
                                                <p className="text-sm font-bold text-green-600">{p.converted_leads}</p>
                                            </div>
                                            <div className="text-center p-2 rounded-lg bg-gray-50">
                                                <p className="text-xs text-gray-400 mb-0.5">Conv %</p>
                                                <p className="text-sm font-bold text-sleep-600">{p.conversion_rate?.toFixed(1)}%</p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )
                        })}
                        {platforms.length === 0 && (
                            <div className="col-span-3 bg-white rounded-2xl border border-gray-100 shadow-premium p-12 text-center">
                                <BarChart3 className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                                <h3 className="text-base font-semibold text-gray-900 mb-1">No source data yet</h3>
                                <p className="text-sm text-gray-400">Analytics will populate as leads come in through Widget, Jotform, and Referral sources.</p>
                            </div>
                        )}
                    </div>

                    {/* Hot Leads by Platform + Source Performance Ranking */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {/* Hot Leads by Platform */}
                        <div className="bg-white rounded-2xl border border-gray-100 shadow-premium p-5">
                            <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2 mb-4">
                                <Flame className="w-4 h-4 text-red-500" /> Hot Leads by Platform
                            </h3>
                            {platforms.length > 0 ? (
                                <div className="space-y-3">
                                    {platforms.map(p => {
                                        const colors = platformColors[p.platform?.toLowerCase()] || platformColors.widget
                                        const Icon = platformIcons[p.platform?.toLowerCase()] || Globe
                                        const maxHot = Math.max(...platforms.map(pp => pp.hot_leads), 1)
                                        return (
                                            <div key={p.platform} className="flex items-center gap-3">
                                                <div className={`w-8 h-8 rounded-lg ${colors.bg} flex items-center justify-center shrink-0`}>
                                                    <Icon className={`w-4 h-4 ${colors.text}`} />
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center justify-between mb-1">
                                                        <span className="text-sm font-medium text-gray-900 capitalize">{p.platform}</span>
                                                        <span className="text-sm font-bold text-red-600">{p.hot_leads}</span>
                                                    </div>
                                                    <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                                        <div className="h-full bg-red-400 rounded-full transition-all duration-500" style={{ width: `${(p.hot_leads / maxHot) * 100}%` }} />
                                                    </div>
                                                </div>
                                            </div>
                                        )
                                    })}
                                </div>
                            ) : (
                                <p className="text-sm text-gray-400 text-center py-8">No hot lead data available</p>
                            )}
                        </div>

                        {/* Source Performance Ranking */}
                        <div className="bg-white rounded-2xl border border-gray-100 shadow-premium p-5">
                            <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2 mb-4">
                                <Zap className="w-4 h-4 text-warm-500" /> Source Performance Ranking
                            </h3>
                            {platforms.length > 0 ? (
                                <div className="space-y-2">
                                    {[...platforms]
                                        .sort((a, b) => b.conversion_rate - a.conversion_rate)
                                        .map((p, i) => {
                                            const colors = platformColors[p.platform?.toLowerCase()] || platformColors.widget
                                            const Icon = platformIcons[p.platform?.toLowerCase()] || Globe
                                            return (
                                                <div key={p.platform} className={`flex items-center gap-3 p-3 rounded-xl ${i === 0 ? 'bg-warm-50 border border-warm-200' : 'bg-gray-50 border border-gray-100'}`}>
                                                    <div className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold ${i === 0 ? 'bg-warm-200 text-warm-800' : 'bg-gray-200 text-gray-600'}`}>
                                                        #{i + 1}
                                                    </div>
                                                    <div className={`w-8 h-8 rounded-lg ${colors.bg} flex items-center justify-center`}>
                                                        <Icon className={`w-4 h-4 ${colors.text}`} />
                                                    </div>
                                                    <div className="flex-1 min-w-0">
                                                        <p className="text-sm font-medium text-gray-900 capitalize">{p.platform}</p>
                                                        <p className="text-xs text-gray-500">{p.total_leads} leads · {p.scheduled_leads} scheduled</p>
                                                    </div>
                                                    <div className="text-right">
                                                        <p className="text-base font-bold text-gray-900">{p.conversion_rate?.toFixed(1)}%</p>
                                                        <p className="text-[10px] text-gray-400 uppercase">conv. rate</p>
                                                    </div>
                                                </div>
                                            )
                                        })}
                                </div>
                            ) : (
                                <p className="text-sm text-gray-400 text-center py-8">No performance data available</p>
                            )}
                        </div>
                    </div>

                    {/* Footer */}
                    <div className="flex items-center justify-between text-xs text-gray-400 pt-2">
                        <span>Showing data for the last {daysBack} days</span>
                        <span className="flex items-center gap-1.5"><Shield className="w-3 h-3" /> HIPAA-compliant analytics</span>
                    </div>
                </>
            )}
        </div>
    )
}
