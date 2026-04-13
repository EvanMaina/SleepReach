import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
    Activity,
    ArrowDownRight,
    ArrowRight,
    ArrowUpRight,
    BarChart3,
    Brain,
    Building2,
    Calendar,
    ChevronRight,
    Clock,
    Copy,
    Heart,
    LineChart as LineChartIcon,
    MessageSquare,
    PhoneCall,
    RefreshCw,
    ShieldCheck,
    Sparkles,
    Target,
    TrendingUp,
    Users,
    Zap,
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

/* ─────────── Types ─────────── */
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
    contact_outcome: string
    urgency: string
    days_waiting: number
    stale_days: number
    recommended_action: string
    reason: string
    script: string
    insurance_status: string
    treatment_interest?: string
    preferred_contact_method?: string
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
        metrics: {
            active_leads: number
            insured_open_leads: number
            avg_first_contact_hours: number | null
            best_source: string
            best_condition: string
            best_insurer: string
            best_provider: string
        }
    }
    act_now: ActNowItem[]
    pipeline: {
        stages: InsightRow[]
        alerts: { label: string; count: number; detail: string }[]
        avg_first_contact_hours: number | null
        avg_schedule_days: number | null
        commentary: string
        conversion_drivers: {
            source: InsightRow[]
            condition: InsightRow[]
            insurance: InsightRow[]
        }
    }
    communication: {
        best_time_of_day: string
        best_contact_method: string
        timing_rows: InsightRow[]
        method_rows: InsightRow[]
        templates: { id: string; title: string; body: string }[]
        commentary: string
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
        team_performance: { name: string; assigned: number; scheduled: number; completed: number; scheduled_rate: number; completion_rate?: number }[]
        commentary?: string
    }
    geographic?: {
        top_zip_codes: { zip: string; count: number; converted: number; rate: number }[]
        top_locations: { location: string; count: number }[]
        total_unique_zips: number
        total_with_location: number
        commentary?: string
    }
}

/* ─────────── Helpers ─────────── */
function scoreTone(score: number) {
    if (score >= 71) return { gradient: 'from-emerald-500 to-teal-500', text: 'text-emerald-400', bg: 'bg-emerald-500', label: 'Healthy' }
    if (score >= 41) return { gradient: 'from-amber-500 to-orange-500', text: 'text-amber-400', bg: 'bg-amber-500', label: 'Needs Attention' }
    return { gradient: 'from-rose-500 to-red-500', text: 'text-rose-400', bg: 'bg-rose-500', label: 'Critical' }
}

function funnelBarWidth(pct: number) {
    return `${Math.max(pct, 5)}%`
}

/* ─────────── Section Card ─────────── */
function Section({ icon: Icon, title, subtitle, children, className = '' }: {
    icon: typeof Brain
    title: string
    subtitle?: string
    children: React.ReactNode
    className?: string
}) {
    return (
        <section className={`rounded-[20px] border border-gray-200 bg-white p-6 shadow-sm ${className}`}>
            <div className="flex items-center gap-3 mb-1">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sleep-50">
                    <Icon className="h-[18px] w-[18px] text-sleep-600" />
                </div>
                <h2 className="text-lg font-bold text-gray-900">{title}</h2>
            </div>
            {subtitle && <p className="ml-12 text-sm text-gray-500 mb-5">{subtitle}</p>}
            {!subtitle && <div className="mb-5" />}
            {children}
        </section>
    )
}

/* ─────────── Metric Card ─────────── */
function MetricCard({ label, value, sub, icon: Icon, accent = 'sleep' }: {
    label: string
    value: string | number
    sub?: string
    icon: typeof Brain
    accent?: string
}) {
    const accentMap: Record<string, string> = {
        sleep: 'border-sleep-200 bg-sleep-50/50',
        emerald: 'border-emerald-200 bg-emerald-50/50',
        amber: 'border-amber-200 bg-amber-50/50',
        rose: 'border-rose-200 bg-rose-50/50',
        blue: 'border-blue-200 bg-blue-50/50',
        violet: 'border-violet-200 bg-violet-50/50',
    }
    const iconMap: Record<string, string> = {
        sleep: 'text-sleep-600',
        emerald: 'text-emerald-600',
        amber: 'text-amber-600',
        rose: 'text-rose-600',
        blue: 'text-blue-600',
        violet: 'text-violet-600',
    }
    return (
        <div className={`rounded-2xl border p-4 ${accentMap[accent] || accentMap.sleep}`}>
            <div className="flex items-center gap-2 mb-2">
                <Icon className={`h-4 w-4 ${iconMap[accent] || iconMap.sleep}`} />
                <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</span>
            </div>
            <div className="text-2xl font-bold text-gray-900">{value}</div>
            {sub && <div className="mt-1 text-xs text-gray-500">{sub}</div>}
        </div>
    )
}

/* ─────────── Main Component ─────────── */
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

    useEffect(() => { void fetchInsights() }, [])

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

    /* ── Loading ── */
    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-32">
                <div className="text-center space-y-4">
                    <div className="relative flex h-20 w-20 mx-auto items-center justify-center">
                        <div className="absolute inset-0 rounded-2xl bg-sleep-100 animate-pulse" />
                        <Brain className="relative h-9 w-9 text-sleep-700" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">AI Insights</h1>
                        <p className="mt-1.5 text-sm text-gray-400">Analyzing your pipeline data...</p>
                    </div>
                    <div className="flex items-center justify-center gap-1.5 pt-2">
                        <div className="h-1.5 w-1.5 rounded-full bg-sleep-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                        <div className="h-1.5 w-1.5 rounded-full bg-sleep-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                        <div className="h-1.5 w-1.5 rounded-full bg-sleep-400 animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                </div>
            </div>
        )
    }

    /* ── Error ── */
    if (error || !data) {
        return (
            <div className="flex items-center justify-center py-32">
                <div className="max-w-md text-center">
                    <div className="flex h-14 w-14 mx-auto items-center justify-center rounded-2xl bg-red-50 border border-red-100 mb-4">
                        <Brain className="h-7 w-7 text-red-400" />
                    </div>
                    <h2 className="text-lg font-bold text-gray-900">AI Insights unavailable</h2>
                    <p className="mt-2 text-sm text-gray-500">{error || 'No data returned. Try refreshing in a moment.'}</p>
                    <button
                        onClick={() => void fetchInsights(true)}
                        className="mt-4 inline-flex items-center gap-2 rounded-xl bg-sleep-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-sleep-700"
                    >
                        <RefreshCw className="h-4 w-4" /> Try Again
                    </button>
                </div>
            </div>
        )
    }

    const tone = scoreTone(data.summary.health_score)

    /* ── Funnel data ── */
    const funnelTotal = data.pipeline.stages.reduce((s, r) => s + (r.count || 0), 0) || 1
    const funnelStages = data.pipeline.stages.map((stage, i) => ({
        ...stage,
        pct: Math.round(((stage.count || 0) / funnelTotal) * 100),
        colors: ['bg-blue-500', 'bg-indigo-500', 'bg-emerald-500', 'bg-teal-500'][i] || 'bg-gray-500',
        lightColors: ['bg-blue-50 text-blue-700', 'bg-indigo-50 text-indigo-700', 'bg-emerald-50 text-emerald-700', 'bg-teal-50 text-teal-700'][i] || 'bg-gray-50 text-gray-700',
    }))

    return (
        <div className="space-y-6 pb-8">
            {/* ═══════════════════════════════════════════════════════════ */}
            {/* TOP — CONVERSION HEALTH SCORE                             */}
            {/* ═══════════════════════════════════════════════════════════ */}
            <div className="rounded-[20px] bg-gray-950 p-6 text-white shadow-lg">
                <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="flex items-start gap-4">
                        <div className={`flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br ${tone.gradient} shadow-lg`}>
                            <Brain className="h-8 w-8 text-white" />
                        </div>
                        <div>
                            <div className="flex items-center gap-3">
                                <h1 className="text-2xl font-bold">AI Insights</h1>
                                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${tone.bg}/20 ${tone.text}`}>{tone.label}</span>
                            </div>
                            <p className="mt-2 max-w-3xl text-sm text-white/70">{data.summary.headline}</p>
                            <p className="mt-1 max-w-3xl text-sm text-white/50">{data.summary.detail}</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        <div className="text-right">
                            <div className="text-xs text-white/40 uppercase tracking-wide">Updated</div>
                            <div className="text-sm text-white/70">{lastUpdatedLabel}</div>
                        </div>
                        <button onClick={() => void fetchInsights(true)} className="inline-flex items-center gap-2 rounded-xl bg-white/10 px-4 py-2.5 text-sm font-semibold text-white hover:bg-white/20 transition-colors">
                            <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                            Refresh
                        </button>
                    </div>
                </div>

                {/* Health Score + Key Metrics */}
                <div className="mt-6 grid gap-4 md:grid-cols-4">
                    <div className="rounded-2xl bg-white/5 border border-white/10 p-5">
                        <div className="text-xs uppercase tracking-wide text-white/40">Health Score</div>
                        <div className="mt-2 flex items-baseline gap-2">
                            <span className="text-5xl font-bold">{data.summary.health_score}</span>
                            <span className="text-sm text-white/40">/100</span>
                        </div>
                        <div className="mt-2 flex items-center gap-1.5 text-sm">
                            {data.summary.trend_delta >= 0
                                ? <ArrowUpRight className="h-4 w-4 text-emerald-400" />
                                : <ArrowDownRight className="h-4 w-4 text-rose-400" />}
                            <span className={data.summary.trend_delta >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                                {Math.abs(data.summary.trend_delta)}%
                            </span>
                            <span className="text-white/40">vs last period</span>
                        </div>
                    </div>
                    <div className="rounded-2xl bg-white/5 border border-white/10 p-5">
                        <div className="text-xs uppercase tracking-wide text-white/40">Active Pipeline</div>
                        <div className="mt-2 text-4xl font-bold">{data.summary.metrics.active_leads}</div>
                        <div className="mt-1 text-sm text-white/40">Total open leads</div>
                    </div>
                    <div className="rounded-2xl bg-white/5 border border-white/10 p-5">
                        <div className="text-xs uppercase tracking-wide text-white/40">Insured Open</div>
                        <div className="mt-2 text-4xl font-bold">{data.summary.metrics.insured_open_leads}</div>
                        <div className="mt-1 text-sm text-white/40">High-value leads needing action</div>
                    </div>
                    <div className="rounded-2xl bg-white/5 border border-white/10 p-5">
                        <div className="text-xs uppercase tracking-wide text-white/40">Avg. First Contact</div>
                        <div className="mt-2 text-4xl font-bold">
                            {data.summary.metrics.avg_first_contact_hours == null ? '—' : `${data.summary.metrics.avg_first_contact_hours}h`}
                        </div>
                        <div className="mt-1 text-sm text-white/40">Time to first outreach</div>
                    </div>
                </div>
            </div>

            {/* ═══════════════════════════════════════════════════════════ */}
            {/* SECTION 1 — WHAT'S HAPPENING NOW                          */}
            {/* ═══════════════════════════════════════════════════════════ */}
            <Section icon={Activity} title="What's Happening Now" subtitle="Real-time pipeline snapshot showing where your leads stand today.">
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                    <MetricCard
                        icon={Users}
                        label="New Leads"
                        value={data.pipeline.stages.find(s => s.label === 'New')?.count || 0}
                        sub={(() => {
                            const stale = data.pipeline.alerts.find(a => a.label === 'Untouched New Leads')?.count || 0;
                            return stale > 0 ? `${stale} waiting 48h+ for first contact` : 'Awaiting first contact';
                        })()}
                        accent="blue"
                    />
                    <MetricCard
                        icon={Clock}
                        label="Stale Follow-ups"
                        value={data.pipeline.alerts.find(a => a.label === 'Stale Follow-up')?.count || 0}
                        sub="No activity for 7+ days"
                        accent="amber"
                    />
                    <MetricCard
                        icon={Heart}
                        label="Insured Open"
                        value={data.summary.metrics.insured_open_leads}
                        sub="Money on the table"
                        accent="emerald"
                    />
                    <MetricCard
                        icon={PhoneCall}
                        label="Callbacks Due"
                        value={data.pipeline.alerts.find(a => a.label === 'Callbacks Due')?.count || 0}
                        sub="Within next 24 hours"
                        accent="violet"
                    />
                    <MetricCard
                        icon={Calendar}
                        label="Scheduled"
                        value={data.pipeline.stages.find(s => s.label === 'Scheduled')?.count || 0}
                        sub="Upcoming consultations"
                        accent="sleep"
                    />
                </div>
            </Section>

            {/* ═══════════════════════════════════════════════════════════ */}
            {/* SECTION 2 — CONVERSION FUNNEL                             */}
            {/* ═══════════════════════════════════════════════════════════ */}
            <Section icon={Target} title="Conversion Funnel" subtitle={data.pipeline.commentary}>
                <div className="space-y-3">
                    {funnelStages.map((stage) => (
                        <div key={stage.label} className="flex items-center gap-4">
                            <div className="w-24 flex-shrink-0">
                                <span className={`inline-flex items-center rounded-lg px-2.5 py-1 text-xs font-semibold ${stage.lightColors}`}>
                                    {stage.label}
                                </span>
                            </div>
                            <div className="flex-1">
                                <div className="h-8 rounded-lg bg-gray-100 overflow-hidden">
                                    <div
                                        className={`h-full rounded-lg ${stage.colors} flex items-center px-3 transition-all duration-500`}
                                        style={{ width: funnelBarWidth(stage.pct) }}
                                    >
                                        <span className="text-xs font-bold text-white whitespace-nowrap">
                                            {stage.count} leads
                                        </span>
                                    </div>
                                </div>
                            </div>
                            <div className="w-20 text-right flex-shrink-0">
                                <span className="text-sm font-semibold text-gray-900">{stage.pct}%</span>
                            </div>
                            <div className="w-28 text-right flex-shrink-0">
                                {stage.dropoff_from_previous != null ? (
                                    <span className="text-xs text-gray-500">{stage.dropoff_from_previous}% drop-off</span>
                                ) : (
                                    <span className="text-xs text-gray-400">—</span>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
                {data.pipeline.avg_first_contact_hours != null && (
                    <div className="mt-5 rounded-xl bg-sleep-50 border border-sleep-200 p-4 text-sm text-sleep-800">
                        <Zap className="inline h-4 w-4 mr-1.5 text-sleep-600" />
                        Average first contact speed: <strong>{data.pipeline.avg_first_contact_hours} hours</strong>.
                        {data.pipeline.avg_schedule_days != null && <> Average time to schedule: <strong>{data.pipeline.avg_schedule_days} days</strong>.</>}
                    </div>
                )}
            </Section>

            {/* ═══════════════════════════════════════════════════════════ */}
            {/* SECTION 3 — HOW TO IMPROVE CONVERSIONS                    */}
            {/* ═══════════════════════════════════════════════════════════ */}
            <Section icon={Sparkles} title="How to Improve Conversions" subtitle="AI-generated strategic recommendations based on your actual data patterns.">
                {data.act_now.length > 0 ? (
                    <div className="space-y-3">
                        {data.act_now.slice(0, 6).map((item) => (
                            <div key={item.lead_id} className="rounded-xl border border-gray-200 p-4 hover:border-sleep-300 hover:bg-sleep-50/30 transition-colors">
                                <div className="flex items-start justify-between gap-3">
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-semibold text-gray-900">{item.recommended_action}</p>
                                        <p className="mt-1 text-sm text-gray-600">{item.reason}</p>
                                    </div>
                                    <span className="flex-shrink-0 rounded-full bg-sleep-50 px-2.5 py-1 text-[11px] font-semibold text-sleep-700">{item.priority}</span>
                                </div>
                                <div className="mt-3 rounded-lg bg-gray-50 p-3">
                                    <div className="flex items-center justify-between mb-1.5">
                                        <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">Suggested Script</span>
                                        <button
                                            onClick={() => void copyText(item.script, 'Script copied')}
                                            className="inline-flex items-center gap-1 text-[11px] text-sleep-600 hover:text-sleep-700 font-medium"
                                        >
                                            <Copy className="h-3 w-3" /> Copy
                                        </button>
                                    </div>
                                    <p className="text-sm text-gray-700 leading-relaxed">{item.script}</p>
                                </div>
                                <div className="mt-2.5 flex items-center gap-2 flex-wrap">
                                    <span className="text-[11px] text-gray-500 bg-gray-100 px-2 py-0.5 rounded-md">{item.condition}</span>
                                    <span className="text-[11px] text-gray-500 bg-gray-100 px-2 py-0.5 rounded-md">{item.insurance_status}</span>
                                    <span className="text-[11px] text-gray-500 bg-gray-100 px-2 py-0.5 rounded-md">{item.days_waiting}d waiting</span>
                                    <button
                                        onClick={() => openLead(item)}
                                        className="ml-auto inline-flex items-center gap-1 text-[11px] text-sleep-600 hover:text-sleep-700 font-semibold"
                                    >
                                        Open lead <ChevronRight className="h-3 w-3" />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="rounded-xl border border-dashed border-sleep-200 bg-sleep-50/50 p-6 text-sm text-sleep-800">
                        More outreach history is needed to generate targeted conversion recommendations. As leads progress through the pipeline, specific actionable insights will appear here.
                    </div>
                )}
            </Section>

            {/* ═══════════════════════════════════════════════════════════ */}
            {/* SECTION 4 — CONDITION PERFORMANCE                         */}
            {/* ═══════════════════════════════════════════════════════════ */}
            <div className="grid gap-6 lg:grid-cols-3">
                {/* Condition Performance */}
                <Section icon={BarChart3} title="Condition Performance" subtitle="Conversion rates and volume by sleep condition.">
                    {data.pipeline.conversion_drivers.condition.length > 0 ? (
                        <div className="space-y-4">
                            {data.pipeline.conversion_drivers.condition.slice(0, 6).map((row) => (
                                <div key={row.label}>
                                    <div className="flex items-center justify-between text-sm mb-1">
                                        <span className="font-medium text-gray-800">{row.label}</span>
                                        <div className="flex items-center gap-3">
                                            <span className="text-xs text-gray-500">{row.count} leads</span>
                                            <span className="font-semibold text-gray-900">{row.conversion_rate}%</span>
                                        </div>
                                    </div>
                                    <div className="h-2.5 rounded-full bg-gray-100">
                                        <div className="h-2.5 rounded-full bg-sleep-500 transition-all duration-500" style={{ width: `${Math.min(row.conversion_rate || 0, 100)}%` }} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : <p className="text-sm text-gray-500">Not enough data to rank conditions yet.</p>}
                </Section>

                {/* Source Performance */}
                <Section icon={TrendingUp} title="Source Performance" subtitle="Which lead sources convert best.">
                    {data.pipeline.conversion_drivers.source.length > 0 ? (
                        <div className="space-y-4">
                            {data.pipeline.conversion_drivers.source.slice(0, 6).map((row) => (
                                <div key={row.label}>
                                    <div className="flex items-center justify-between text-sm mb-1">
                                        <span className="font-medium text-gray-800">{row.label}</span>
                                        <div className="flex items-center gap-3">
                                            <span className="text-xs text-gray-500">{row.count} leads</span>
                                            <span className="font-semibold text-gray-900">{row.conversion_rate}%</span>
                                        </div>
                                    </div>
                                    <div className="h-2.5 rounded-full bg-gray-100">
                                        <div className="h-2.5 rounded-full bg-indigo-500 transition-all duration-500" style={{ width: `${Math.min(row.conversion_rate || 0, 100)}%` }} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : <p className="text-sm text-gray-500">Not enough data to rank sources yet.</p>}
                </Section>

                {/* Insurance Performance */}
                <Section icon={ShieldCheck} title="Insurance Performance" subtitle="Conversion rates by insurance status.">
                    {data.pipeline.conversion_drivers.insurance.length > 0 ? (
                        <div className="space-y-4">
                            {data.pipeline.conversion_drivers.insurance.slice(0, 6).map((row) => (
                                <div key={row.label}>
                                    <div className="flex items-center justify-between text-sm mb-1">
                                        <span className="font-medium text-gray-800">{row.label}</span>
                                        <div className="flex items-center gap-3">
                                            <span className="text-xs text-gray-500">{row.count} leads</span>
                                            <span className="font-semibold text-gray-900">{row.conversion_rate}%</span>
                                        </div>
                                    </div>
                                    <div className="h-2.5 rounded-full bg-gray-100">
                                        <div className="h-2.5 rounded-full bg-emerald-500 transition-all duration-500" style={{ width: `${Math.min(row.conversion_rate || 0, 100)}%` }} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : <p className="text-sm text-gray-500">Not enough data to rank by insurance yet.</p>}
                </Section>
            </div>

            {/* ═══════════════════════════════════════════════════════════ */}
            {/* SECTION 5 — COMMUNICATION INSIGHTS                        */}
            {/* ═══════════════════════════════════════════════════════════ */}
            <Section icon={MessageSquare} title="Communication Insights" subtitle={data.communication.commentary}>
                <div className="grid gap-4 md:grid-cols-2 mb-6">
                    <div className="rounded-xl border border-gray-200 bg-gradient-to-br from-gray-50 to-white p-5">
                        <div className="text-xs uppercase tracking-wide text-gray-500">Best Time Window</div>
                        <div className="mt-2 text-3xl font-bold text-gray-900">{data.communication.best_time_of_day}</div>
                        <div className="mt-1 text-sm text-gray-500">Highest answer rate based on your outreach data</div>
                    </div>
                    <div className="rounded-xl border border-gray-200 bg-gradient-to-br from-gray-50 to-white p-5">
                        <div className="text-xs uppercase tracking-wide text-gray-500">Best Contact Method</div>
                        <div className="mt-2 text-3xl font-bold text-gray-900">{data.communication.best_contact_method}</div>
                        <div className="mt-1 text-sm text-gray-500">Channel with the highest success rate</div>
                    </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2 mb-6">
                    <div className="h-56 rounded-xl bg-gray-50 p-3">
                        <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 px-1 mb-1">Answer Rate by Time of Day</div>
                        <ResponsiveContainer width="100%" height="85%">
                            <BarChart data={data.communication.timing_rows}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
                                <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
                                <Tooltip />
                                <Bar dataKey="positive_rate" name="Answer Rate %" fill="#4a6fa5" radius={[6, 6, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                    <div className="h-56 rounded-xl bg-gray-50 p-3">
                        <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 px-1 mb-1">Success Rate by Method</div>
                        <ResponsiveContainer width="100%" height="85%">
                            <BarChart data={data.communication.method_rows}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
                                <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
                                <Tooltip />
                                <Bar dataKey="success_rate" name="Success Rate %" fill="#26a9b5" radius={[6, 6, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Scripts */}
                <h3 className="text-sm font-bold text-gray-800 mb-3 flex items-center gap-2">
                    <Copy className="h-4 w-4 text-gray-400" /> Outreach Scripts
                </h3>
                {data.communication.templates.length > 0 ? (
                    <div className="grid gap-3 md:grid-cols-2">
                        {data.communication.templates.map((tmpl) => (
                            <div key={tmpl.id} className="rounded-xl border border-gray-200 p-4 hover:border-sleep-200 transition-colors">
                                <div className="flex items-center justify-between gap-3 mb-2">
                                    <span className="text-sm font-semibold text-gray-900">{tmpl.title}</span>
                                    <button onClick={() => void copyText(tmpl.body, `${tmpl.title} copied`)} className="text-sleep-600 hover:text-sleep-700 flex-shrink-0">
                                        <Copy className="h-3.5 w-3.5" />
                                    </button>
                                </div>
                                <p className="text-sm text-gray-600 leading-relaxed">{tmpl.body}</p>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="rounded-xl border border-dashed border-sleep-200 bg-sleep-50/50 p-4 text-sm text-sleep-800">
                        Scripts will be generated once enough outreach history exists.
                    </div>
                )}
            </Section>

            {/* ═══════════════════════════════════════════════════════════ */}
            {/* SECTION 6 — PROVIDER INTELLIGENCE                         */}
            {/* ═══════════════════════════════════════════════════════════ */}
            <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
                <Section icon={Building2} title="Provider Intelligence" subtitle={data.provider_intelligence.commentary}>
                    {data.provider_intelligence.providers.length > 0 ? (
                        <div className="space-y-3">
                            {data.provider_intelligence.providers.slice(0, 6).map((provider, i) => (
                                <div key={provider.id} className="flex items-center gap-4 rounded-xl border border-gray-200 p-3.5">
                                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-sleep-50 text-sm font-bold text-sleep-700 flex-shrink-0">
                                        #{i + 1}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-semibold text-gray-900 truncate">{provider.name}</p>
                                        <p className="text-xs text-gray-500">{provider.practice_name || provider.specialty}</p>
                                    </div>
                                    <div className="text-right flex-shrink-0">
                                        <p className="text-lg font-bold text-gray-900">{provider.conversion_rate}%</p>
                                        <p className="text-xs text-gray-500">{provider.referrals} referrals</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="rounded-xl border border-dashed border-sleep-200 bg-sleep-50/50 p-4 text-sm text-sleep-800">
                            Provider intelligence will appear once referral partners have leads in the pipeline.
                        </div>
                    )}
                    {data.provider_intelligence.recommendations.length > 0 && (
                        <div className="mt-4 space-y-2">
                            {data.provider_intelligence.recommendations.map((rec, i) => (
                                <div key={i} className="flex items-start gap-2.5 rounded-lg bg-gray-50 px-4 py-3">
                                    <ArrowRight className="h-4 w-4 text-sleep-500 mt-0.5 flex-shrink-0" />
                                    <p className="text-sm text-gray-700">{rec}</p>
                                </div>
                            ))}
                        </div>
                    )}
                </Section>

                {/* ═══════════════════════════════════════════════════════════ */}
                {/* SECTION 7 — TRENDS                                        */}
                {/* ═══════════════════════════════════════════════════════════ */}
                <Section icon={LineChartIcon} title="Trends & Forecasting" subtitle={data.trends.commentary}>
                    {(data.trends.weekly.length > 0 || data.trends.monthly.length > 0) ? (
                        <div className="space-y-4">
                            {data.trends.weekly.length > 0 && (
                                <div className="h-56 rounded-xl bg-gray-50 p-3">
                                    <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 px-1 mb-1">Weekly Volume</div>
                                    <ResponsiveContainer width="100%" height="85%">
                                        <AreaChart data={data.trends.weekly}>
                                            <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                            <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 10 }} />
                                            <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 10 }} />
                                            <Tooltip />
                                            <Area dataKey="leads" name="Leads" stroke="#4a6fa5" fill="#4a6fa5" fillOpacity={0.15} />
                                            <Area dataKey="scheduled" name="Scheduled" stroke="#26a9b5" fill="#26a9b5" fillOpacity={0.12} />
                                        </AreaChart>
                                    </ResponsiveContainer>
                                </div>
                            )}
                            {data.trends.monthly.length > 0 && (
                                <div className="h-56 rounded-xl bg-gray-50 p-3">
                                    <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 px-1 mb-1">Monthly Trend</div>
                                    <ResponsiveContainer width="100%" height="85%">
                                        <LineChart data={data.trends.monthly}>
                                            <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                            <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 10 }} />
                                            <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 10 }} />
                                            <Tooltip />
                                            <Line type="monotone" dataKey="leads" name="Leads" stroke="#4a6fa5" strokeWidth={2.5} dot={false} />
                                            <Line type="monotone" dataKey="completed" name="Completed" stroke="#ee9a1d" strokeWidth={2.5} dot={false} />
                                        </LineChart>
                                    </ResponsiveContainer>
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="rounded-xl border border-dashed border-sleep-200 bg-sleep-50/50 p-4 text-sm text-sleep-800">
                            Trend charts will appear once enough weekly and monthly history exists.
                        </div>
                    )}
                    <div className="mt-4 rounded-xl bg-gray-950 p-5 text-white">
                        <div className="flex items-center gap-2 text-xs font-semibold text-white/60 uppercase tracking-wide mb-2">
                            <TrendingUp className="h-3.5 w-3.5" /> Forecast
                        </div>
                        <p className="text-sm font-medium leading-relaxed">{data.trends.forecast.summary}</p>
                    </div>
                    {/* Coordinator Performance */}
                    {data.operational?.team_performance?.length > 0 && (
                        <div className="mt-4 rounded-xl border border-gray-200 p-4">
                            <div className="text-sm font-bold text-gray-900 mb-1 flex items-center gap-2">
                                <Users className="h-4 w-4 text-sleep-600" /> Coordinator Performance
                            </div>
                            {data.operational?.commentary && (
                                <p className="text-xs text-gray-500 mb-3">{data.operational.commentary}</p>
                            )}
                            <div className="space-y-2.5">
                                {data.operational.team_performance.slice(0, 6).map((u: any) => (
                                    <div key={u.name} className="flex items-center justify-between text-sm">
                                        <span className="font-medium text-gray-800">{u.name}</span>
                                        <div className="flex items-center gap-3 text-xs">
                                            <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-semibold">{u.completion_rate || 0}% converted</span>
                                            <span className="text-gray-400">{u.scheduled || 0} scheduled · {u.assigned} assigned</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Geographic Insights */}
                    {(data.geographic?.top_zip_codes?.length ?? 0) > 0 && (
                        <div className="mt-4 rounded-xl border border-gray-200 p-4">
                            <div className="text-sm font-bold text-gray-900 mb-1 flex items-center gap-2">
                                <BarChart3 className="h-4 w-4 text-amber-600" /> Geographic Lead Distribution
                            </div>
                            {data.geographic?.commentary && (
                                <p className="text-xs text-gray-500 mb-3">{data.geographic.commentary}</p>
                            )}
                            <div className="space-y-2">
                                {data.geographic!.top_zip_codes.slice(0, 8).map((z: any) => {
                                    const maxCount = data.geographic!.top_zip_codes[0]?.count || 1
                                    return (
                                        <div key={z.zip} className="flex items-center gap-3 text-sm">
                                            <span className="w-16 font-mono font-medium text-gray-700 shrink-0">{z.zip}</span>
                                            <div className="flex-1 h-5 bg-gray-100 rounded-full overflow-hidden">
                                                <div className="h-full bg-amber-400 rounded-full transition-all" style={{ width: `${(z.count / maxCount) * 100}%` }} />
                                            </div>
                                            <span className="text-xs font-semibold text-gray-600 w-20 text-right">{z.count} leads · {z.rate}%</span>
                                        </div>
                                    )
                                })}
                            </div>
                            {data.geographic?.top_locations?.length ? (
                                <div className="mt-3 pt-3 border-t border-gray-100">
                                    <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Top Recorded Locations</div>
                                    <div className="flex flex-wrap gap-2">
                                        {data.geographic!.top_locations.slice(0, 8).map((l: any) => (
                                            <span key={l.location} className="px-2.5 py-1 rounded-full bg-amber-50 text-amber-800 text-xs font-medium">
                                                {l.location} ({l.count})
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            ) : null}
                        </div>
                    )}
                </Section>
            </div>

            {data.insufficient_data && (
                <div className="rounded-xl border border-dashed border-sleep-200 bg-sleep-50/50 p-5 text-sm text-sleep-800">
                    There is limited historical data, so these recommendations are directional. As more leads progress through the funnel, insights will become more precise and actionable.
                </div>
            )}
        </div>
    )
}
