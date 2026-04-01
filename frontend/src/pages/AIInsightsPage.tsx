import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
    AlertTriangle,
    ArrowDownRight,
    ArrowUpRight,
    Brain,
    Building2,
    ChevronRight,
    Clock3,
    Copy,
    LineChart as LineChartIcon,
    PhoneCall,
    RefreshCw,
    ShieldCheck,
    Sparkles,
    TrendingUp,
    Wallet,
} from 'lucide-react'
import {
    ResponsiveContainer,
    AreaChart,
    Area,
    CartesianGrid,
    XAxis,
    YAxis,
    Tooltip,
    LineChart,
    Line,
    BarChart,
    Bar,
} from 'recharts'
import toast from 'react-hot-toast'
import { aiInsightsAPI } from '../lib/api'

interface InsightRow {
    label: string
    count?: number
    converted?: number
    completed?: number
    conversion_rate?: number
    attempts?: number
    positive?: number
    positive_rate?: number
    success_rate?: number
    avg_days?: number
    percentage_of_total?: number
    dropoff_from_previous?: number | null
}

interface ActNowItem {
    lead_id: string
    lead_name?: string
    lead_number: string
    queue_hint: string
    condition: string
    priority: string
    status: string
    recommended_action: string
    reason: string
    script: string
    insurance_status: string
}

interface AIInsightsResponse {
    generated_at: string
    cached?: boolean
    insufficient_data: boolean
    llm_enabled?: boolean
    summary: {
        health_score: number
        health_state: string
        trend_delta: number
        headline: string
        detail: string
    }
    act_now: ActNowItem[]
    pipeline: {
        stages: InsightRow[]
        alerts: { label: string; count: number; detail: string }[]
        avg_first_contact_hours: number | null
        avg_schedule_days: number | null
        commentary: string
    }
    communication: {
        best_time_of_day: string
        best_contact_method: string
        timing_rows: InsightRow[]
        method_rows: InsightRow[]
        templates: { id: string; title: string; body: string }[]
        commentary: string
    }
    revenue_growth: {
        estimated_pipeline_value: number | null
        revenue_at_risk: number | null
        insured_open_leads: number
        conversion_by_source: InsightRow[]
        conversion_by_condition: InsightRow[]
        conversion_by_insurance: InsightRow[]
        commentary: string
        recommendations: string[]
    }
    provider_intelligence: {
        providers: { id: string; name: string; specialty: string; referrals: number; conversion_rate: number; practice_name?: string | null }[]
        commentary: string
        recommendations: string[]
    }
    trends: {
        weekly: { label: string; leads: number; scheduled: number; conversion_rate: number }[]
        monthly: { label: string; leads: number; completed: number; conversion_rate: number }[]
        forecast: { projected_monthly_leads: number; projected_scheduled: number; summary: string }
        commentary: string
    }
    operational: {
        team_performance: { name: string; assigned: number; scheduled: number; completed: number; scheduled_rate: number }[]
    }
}

function currency(value: number | null | undefined) {
    if (value == null) return 'Not configured'
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
}

function scoreTone(score: number) {
    if (score >= 71) return 'from-emerald-500 to-teal-500'
    if (score >= 41) return 'from-amber-500 to-orange-500'
    return 'from-rose-500 to-red-500'
}

export default function AIInsightsPage() {
    const navigate = useNavigate()
    const [data, setData] = useState<AIInsightsResponse | null>(null)
    const [isLoading, setIsLoading] = useState(true)
    const [isRefreshing, setIsRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const fetchInsights = async (force = false) => {
        try {
            force ? setIsRefreshing(true) : setIsLoading(true)
            setError(null)
            const res = await aiInsightsAPI.get(force ? { force_refresh: true } : undefined)
            setData(res.data)
        } catch (err: any) {
            setError(err?.response?.data?.message || 'Unable to load AI insights right now.')
        } finally {
            setIsLoading(false)
            setIsRefreshing(false)
        }
    }

    useEffect(() => {
        void fetchInsights()
    }, [])

    const lastUpdatedLabel = useMemo(() => {
        if (!data?.generated_at) return '—'
        return new Date(data.generated_at).toLocaleString()
    }, [data?.generated_at])

    const openLead = (item: ActNowItem) => {
        sessionStorage.setItem('sleepreach_focus_lead', JSON.stringify({ leadId: item.lead_id, queueHint: item.queue_hint || 'new' }))
        navigate(item.queue_hint === 'all' ? '/leads' : `/coordinator/${item.queue_hint || 'new'}`)
    }

    const copyText = async (text: string, success: string) => {
        await navigator.clipboard.writeText(text)
        toast.success(success)
    }

    if (isLoading) {
        return (
            <div className="space-y-6">
                <div className="rounded-3xl border border-sleep-100 bg-white p-10 shadow-sm">
                    <div className="flex items-center gap-4">
                        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-sleep-100">
                            <Brain className="h-7 w-7 animate-pulse text-sleep-700" />
                        </div>
                        <div>
                            <h1 className="text-3xl font-bold tracking-tight text-gray-900">AI Insights</h1>
                            <p className="mt-1 text-sm text-gray-500">Analyzing your pipeline...</p>
                        </div>
                    </div>
                </div>
            </div>
        )
    }

    if (error || !data) {
        return (
            <div className="rounded-3xl border border-red-200 bg-red-50 p-8 text-red-700">
                <p className="text-lg font-semibold">AI Insights unavailable</p>
                <p className="mt-2 text-sm">{error || 'No data returned.'}</p>
            </div>
        )
    }

    return (
        <div className="space-y-6">
            <div className="rounded-[28px] border border-sleep-100 bg-white p-6 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="flex items-start gap-4">
                        <div className={`flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br ${scoreTone(data.summary.health_score)} text-white shadow-lg`}>
                            <Brain className="h-7 w-7" />
                        </div>
                        <div>
                            <div className="flex items-center gap-3">
                                <h1 className="text-3xl font-bold tracking-tight text-gray-900">AI Insights</h1>
                                <span className="rounded-full bg-sleep-50 px-3 py-1 text-xs font-semibold text-sleep-700">{data.cached ? 'Cached' : 'Fresh'}</span>
                            </div>
                            <p className="mt-1 text-sm text-gray-500">Organization-wide conversion intelligence for SleepReach.</p>
                            <p className="mt-3 max-w-4xl text-sm text-gray-700">{data.summary.headline}</p>
                            <p className="mt-1 text-sm text-gray-500">{data.summary.detail}</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        <div className="rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3 text-right">
                            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Last updated</div>
                            <div className="mt-1 text-sm font-medium text-gray-900">{lastUpdatedLabel}</div>
                        </div>
                        <button onClick={() => void fetchInsights(true)} className="inline-flex items-center gap-2 rounded-2xl bg-sleep-600 px-4 py-3 text-sm font-semibold text-white hover:bg-sleep-700">
                            <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                            Refresh Insights
                        </button>
                    </div>
                </div>
                <div className="mt-6 grid gap-4 md:grid-cols-4">
                    <div className="rounded-3xl bg-gray-950 p-5 text-white"><div className="text-xs uppercase tracking-wide text-white/60">Conversion Health Score</div><div className="mt-2 text-4xl font-bold">{data.summary.health_score}</div></div>
                    <div className="rounded-3xl border border-gray-200 bg-gray-50 p-5"><div className="text-xs uppercase tracking-wide text-gray-500">Trend vs prior period</div><div className="mt-2 flex items-center gap-2 text-2xl font-bold text-gray-900">{data.summary.trend_delta >= 0 ? <ArrowUpRight className="h-5 w-5 text-emerald-600" /> : <ArrowDownRight className="h-5 w-5 text-rose-600" />}{Math.abs(data.summary.trend_delta)}%</div></div>
                    <div className="rounded-3xl border border-gray-200 bg-gray-50 p-5"><div className="text-xs uppercase tracking-wide text-gray-500">Best contact window</div><div className="mt-2 text-2xl font-bold text-gray-900">{data.communication.best_time_of_day}</div></div>
                    <div className="rounded-3xl border border-gray-200 bg-gray-50 p-5"><div className="text-xs uppercase tracking-wide text-gray-500">Best contact method</div><div className="mt-2 text-2xl font-bold text-gray-900">{data.communication.best_contact_method}</div></div>
                </div>
            </div>

            <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
                <section className="rounded-[28px] border border-gray-200 bg-white p-6 shadow-sm">
                    <div className="flex items-center gap-3"><Sparkles className="h-5 w-5 text-sleep-600" /><h2 className="text-xl font-bold text-gray-900">Act Now</h2></div>
                    <p className="mt-1 text-sm text-gray-500">Top coordinator actions to move the pipeline right now.</p>
                    <div className="mt-5 space-y-3">
                        {data.act_now.map((item) => (
                            <div key={item.lead_id} className="rounded-3xl border border-gray-200 p-4">
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                    <div>
                                        <button onClick={() => openLead(item)} className="group inline-flex items-center gap-2 text-left text-lg font-semibold text-sleep-800 hover:text-sleep-600">
                                            {item.lead_name || item.lead_number}
                                            <ChevronRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                                        </button>
                                        <p className="mt-1 text-sm text-gray-500">{item.lead_number} · {item.condition} · {item.insurance_status}</p>
                                    </div>
                                    <span className="rounded-full bg-sleep-50 px-3 py-1 text-xs font-semibold text-sleep-700">{item.priority} priority</span>
                                </div>
                                <p className="mt-3 text-sm font-semibold text-gray-900">{item.recommended_action}</p>
                                <p className="mt-1 text-sm text-gray-600">{item.reason}</p>
                                <div className="mt-3 rounded-2xl bg-gray-50 p-3 text-sm text-gray-700">{item.script}</div>
                                <div className="mt-3 flex flex-wrap gap-2">
                                    <button onClick={() => openLead(item)} className="inline-flex items-center gap-2 rounded-xl border border-sleep-200 px-3 py-2 text-sm font-medium text-sleep-700 hover:bg-sleep-50"><PhoneCall className="h-4 w-4" />Open lead</button>
                                    <button onClick={() => void copyText(item.script, 'Script copied')} className="inline-flex items-center gap-2 rounded-xl border border-gray-200 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"><Copy className="h-4 w-4" />Copy script</button>
                                </div>
                            </div>
                        ))}
                    </div>
                </section>

                <section className="rounded-[28px] border border-gray-200 bg-white p-6 shadow-sm">
                    <div className="flex items-center gap-3"><AlertTriangle className="h-5 w-5 text-amber-500" /><h2 className="text-xl font-bold text-gray-900">Pipeline Intelligence</h2></div>
                    <p className="mt-1 text-sm text-gray-500">{data.pipeline.commentary}</p>
                    <div className="mt-5 grid gap-3">
                        {data.pipeline.stages.map((stage) => (
                            <div key={stage.label} className="rounded-2xl border border-gray-200 p-4">
                                <div className="flex items-center justify-between text-sm font-semibold text-gray-900"><span>{stage.label}</span><span>{stage.count}</span></div>
                                <div className="mt-3 h-2 rounded-full bg-gray-100"><div className="h-2 rounded-full bg-sleep-500" style={{ width: `${Math.min(stage.percentage_of_total || 0, 100)}%` }} /></div>
                                <div className="mt-2 flex items-center justify-between text-xs text-gray-500"><span>{stage.percentage_of_total}% of pipeline</span><span>{stage.dropoff_from_previous == null ? '—' : `${stage.dropoff_from_previous}% drop-off`}</span></div>
                            </div>
                        ))}
                    </div>
                    <div className="mt-5 grid gap-3 md:grid-cols-3">
                        {data.pipeline.alerts.map((alert) => (
                            <div key={alert.label} className="rounded-2xl bg-amber-50 p-4">
                                <div className="text-sm font-semibold text-amber-900">{alert.label}</div>
                                <div className="mt-2 text-2xl font-bold text-amber-700">{alert.count}</div>
                                <div className="mt-1 text-xs text-amber-800">{alert.detail}</div>
                            </div>
                        ))}
                    </div>
                </section>
            </div>

            <div className="grid gap-6 xl:grid-cols-2">
                <section className="rounded-[28px] border border-gray-200 bg-white p-6 shadow-sm">
                    <div className="flex items-center gap-3"><PhoneCall className="h-5 w-5 text-sleep-600" /><h2 className="text-xl font-bold text-gray-900">Communication Intelligence</h2></div>
                    <p className="mt-1 text-sm text-gray-500">{data.communication.commentary}</p>
                    <div className="mt-5 grid gap-4 md:grid-cols-2">
                        <div className="h-64 rounded-3xl bg-gray-50 p-3">
                            <ResponsiveContainer width="100%" height="100%"><BarChart data={data.communication.timing_rows}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" tickLine={false} axisLine={false} /><YAxis tickLine={false} axisLine={false} /><Tooltip /><Bar dataKey="positive_rate" fill="#4a6fa5" radius={[8,8,0,0]} /></BarChart></ResponsiveContainer>
                        </div>
                        <div className="h-64 rounded-3xl bg-gray-50 p-3">
                            <ResponsiveContainer width="100%" height="100%"><BarChart data={data.communication.method_rows}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" tickLine={false} axisLine={false} /><YAxis tickLine={false} axisLine={false} /><Tooltip /><Bar dataKey="success_rate" fill="#26a9b5" radius={[8,8,0,0]} /></BarChart></ResponsiveContainer>
                        </div>
                    </div>
                    <div className="mt-5 space-y-3">
                        {data.communication.templates.map((template) => (
                            <div key={template.id} className="rounded-2xl border border-gray-200 p-4">
                                <div className="flex items-center justify-between gap-3"><div className="text-sm font-semibold text-gray-900">{template.title}</div><button onClick={() => void copyText(template.body, `${template.title} copied`)} className="text-sleep-600 hover:text-sleep-700"><Copy className="h-4 w-4" /></button></div>
                                <p className="mt-2 text-sm text-gray-600">{template.body}</p>
                            </div>
                        ))}
                    </div>
                </section>

                <section className="rounded-[28px] border border-gray-200 bg-white p-6 shadow-sm">
                    <div className="flex items-center gap-3"><Wallet className="h-5 w-5 text-emerald-600" /><h2 className="text-xl font-bold text-gray-900">Revenue & Growth Intelligence</h2></div>
                    <p className="mt-1 text-sm text-gray-500">{data.revenue_growth.commentary}</p>
                    <div className="mt-5 grid gap-4 md:grid-cols-3">
                        <div className="rounded-3xl bg-gray-950 p-5 text-white"><div className="text-xs uppercase tracking-wide text-white/60">Pipeline value</div><div className="mt-2 text-2xl font-bold">{currency(data.revenue_growth.estimated_pipeline_value)}</div></div>
                        <div className="rounded-3xl border border-gray-200 bg-gray-50 p-5"><div className="text-xs uppercase tracking-wide text-gray-500">Revenue at risk</div><div className="mt-2 text-2xl font-bold text-gray-900">{currency(data.revenue_growth.revenue_at_risk)}</div></div>
                        <div className="rounded-3xl border border-gray-200 bg-gray-50 p-5"><div className="text-xs uppercase tracking-wide text-gray-500">Insured open leads</div><div className="mt-2 text-2xl font-bold text-gray-900">{data.revenue_growth.insured_open_leads}</div></div>
                    </div>
                    <div className="mt-5 grid gap-4 md:grid-cols-3">
                        {[['By Source', data.revenue_growth.conversion_by_source], ['By Condition', data.revenue_growth.conversion_by_condition], ['By Insurance', data.revenue_growth.conversion_by_insurance]].map(([title, rows]) => (
                            <div key={title as string} className="rounded-2xl border border-gray-200 p-4">
                                <h3 className="text-sm font-semibold text-gray-900">{title as string}</h3>
                                <div className="mt-3 space-y-3">
                                    {(rows as InsightRow[]).slice(0, 5).map((row) => (
                                        <div key={row.label}>
                                            <div className="flex items-center justify-between text-xs text-gray-600"><span>{row.label}</span><span>{row.conversion_rate}%</span></div>
                                            <div className="mt-1 h-2 rounded-full bg-gray-100"><div className="h-2 rounded-full bg-emerald-500" style={{ width: `${Math.min(row.conversion_rate || 0, 100)}%` }} /></div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                    <div className="mt-5 space-y-2">
                        {data.revenue_growth.recommendations.map((item) => <div key={item} className="rounded-2xl bg-sleep-50 px-4 py-3 text-sm text-sleep-900">{item}</div>)}
                    </div>
                </section>
            </div>

            <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
                <section className="rounded-[28px] border border-gray-200 bg-white p-6 shadow-sm">
                    <div className="flex items-center gap-3"><Building2 className="h-5 w-5 text-sleep-600" /><h2 className="text-xl font-bold text-gray-900">Provider Intelligence</h2></div>
                    <p className="mt-1 text-sm text-gray-500">{data.provider_intelligence.commentary}</p>
                    <div className="mt-5 space-y-3">
                        {data.provider_intelligence.providers.slice(0, 6).map((provider) => (
                            <div key={provider.id} className="rounded-2xl border border-gray-200 p-4">
                                <div className="flex items-center justify-between gap-3"><div><div className="font-semibold text-gray-900">{provider.name}</div><div className="text-xs text-gray-500">{provider.practice_name || provider.specialty}</div></div><div className="text-right"><div className="text-lg font-bold text-gray-900">{provider.conversion_rate}%</div><div className="text-xs text-gray-500">{provider.referrals} referrals</div></div></div>
                            </div>
                        ))}
                    </div>
                    <div className="mt-5 space-y-2">
                        {data.provider_intelligence.recommendations.map((item) => <div key={item} className="rounded-2xl bg-gray-50 px-4 py-3 text-sm text-gray-700">{item}</div>)}
                    </div>
                </section>

                <section className="rounded-[28px] border border-gray-200 bg-white p-6 shadow-sm">
                    <div className="flex items-center gap-3"><LineChartIcon className="h-5 w-5 text-sleep-600" /><h2 className="text-xl font-bold text-gray-900">Trends & Forecasting</h2></div>
                    <p className="mt-1 text-sm text-gray-500">{data.trends.commentary}</p>
                    <div className="mt-5 grid gap-4 lg:grid-cols-2">
                        <div className="h-72 rounded-3xl bg-gray-50 p-3">
                            <ResponsiveContainer width="100%" height="100%"><AreaChart data={data.trends.weekly}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" tickLine={false} axisLine={false} /><YAxis tickLine={false} axisLine={false} /><Tooltip /><Area dataKey="leads" stroke="#4a6fa5" fill="#4a6fa5" fillOpacity={0.18} /><Area dataKey="scheduled" stroke="#26a9b5" fill="#26a9b5" fillOpacity={0.14} /></AreaChart></ResponsiveContainer>
                        </div>
                        <div className="h-72 rounded-3xl bg-gray-50 p-3">
                            <ResponsiveContainer width="100%" height="100%"><LineChart data={data.trends.monthly}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" tickLine={false} axisLine={false} /><YAxis tickLine={false} axisLine={false} /><Tooltip /><Line type="monotone" dataKey="leads" stroke="#4a6fa5" strokeWidth={3} /><Line type="monotone" dataKey="completed" stroke="#ee9a1d" strokeWidth={3} /></LineChart></ResponsiveContainer>
                        </div>
                    </div>
                    <div className="mt-5 rounded-3xl bg-gray-950 p-5 text-white">
                        <div className="flex items-center gap-2 text-sm font-semibold text-white/80"><TrendingUp className="h-4 w-4" />Forecast</div>
                        <p className="mt-2 text-xl font-bold">{data.trends.forecast.summary}</p>
                    </div>
                    {data.operational.team_performance?.length ? (
                        <div className="mt-5 rounded-2xl border border-gray-200 p-4">
                            <div className="flex items-center gap-2 text-sm font-semibold text-gray-900"><ShieldCheck className="h-4 w-4 text-sleep-600" />Team Performance</div>
                            <div className="mt-3 space-y-3">
                                {data.operational.team_performance.slice(0, 5).map((user) => (
                                    <div key={user.name} className="flex items-center justify-between text-sm">
                                        <span className="font-medium text-gray-900">{user.name}</span>
                                        <span className="text-gray-500">{user.scheduled_rate}% scheduled · {user.assigned} assigned</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ) : null}
                </section>
            </div>

            {data.insufficient_data ? (
                <div className="rounded-[28px] border border-dashed border-sleep-200 bg-sleep-50/70 p-6 text-sm text-sleep-900">
                    There is not much historical data yet, so the recommendations are directional. As more leads move through the funnel, AI Insights will become more precise.
                </div>
            ) : null}
        </div>
    )
}
