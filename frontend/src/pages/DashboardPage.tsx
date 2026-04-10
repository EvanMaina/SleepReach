import { useEffect, useState, useMemo } from 'react'
import {
    Users, UserCheck, TrendingUp, CalendarCheck,
    ArrowUpRight, ArrowDownRight, Activity, Moon,
    ChevronRight, BarChart3, Wind, Lightbulb, Brain,
    ClipboardList, Pill, HelpCircle, type LucideIcon
} from 'lucide-react'
import {
    AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer
} from 'recharts'
import { useAuth } from '../contexts/AuthContext'

/* ─── Types ─── */
interface DashboardStats {
    total_leads: number
    converted_leads: number
    conversion_rate: number
    scheduled_appointments: number
    total_leads_change: number
    converted_change: number
    conversion_change: number
    scheduled_change: number
}

interface TrendPoint {
    date: string
    leads: number
    converted: number
}

interface ConditionData {
    name: string
    count: number
    percentage: number
    color: string
}

interface TreatmentData {
    name: string
    interest: number
    icon: LucideIcon
    count: number
}

interface CohortRow {
    month: string
    total: number
    retention: number[]
    periods: number[]
}

/* ─── Defaults (zero-state) ─── */
const defaultStats: DashboardStats = {
    total_leads: 0,
    converted_leads: 0,
    conversion_rate: 0,
    scheduled_appointments: 0,
    total_leads_change: 0,
    converted_change: 0,
    conversion_change: 0,
    scheduled_change: 0,
}

/* ─── Condition color map ─── */
const CONDITION_COLORS: Record<string, string> = {
    'SLEEP_APNEA': '#4A6FA5',
    'INSOMNIA': '#6593be',
    'RESTLESS_LEG': '#EE9A1D',
    'NARCOLEPSY': '#26a9b5',
    'WALKING_DREAMS': '#e06790',
    'OTHER': '#7c5cbf',
}

const CONDITION_LABELS: Record<string, string> = {
    'SLEEP_APNEA': 'Snoring / Sleep Apnea',
    'INSOMNIA': 'Insomnia',
    'RESTLESS_LEG': 'Restless Legs Syndrome',
    'NARCOLEPSY': 'Narcolepsy',
    'WALKING_DREAMS': 'Walking / Acting Out Dreams',
    'OTHER': 'Other',
}

/* All conditions to always display (even with 0 leads) — replicates NeuroReach behavior */
const ALL_CONDITIONS = ['SLEEP_APNEA', 'INSOMNIA', 'RESTLESS_LEG', 'NARCOLEPSY', 'WALKING_DREAMS', 'OTHER']

/* All treatment types to always display (even with 0 leads) */
const ALL_TREATMENTS = ['cpap_bipap', 'inspire', 'therapy_cbt', 'sleep_study', 'medication', 'not_sure']

/* ─── Treatment interest icons (Lucide) ─── */
const TREATMENT_ICONS: Record<string, LucideIcon> = {
    'cpap_bipap': Wind,
    'inspire': Lightbulb,
    'therapy_cbt': Brain,
    'sleep_study': ClipboardList,
    'medication': Pill,
    'not_sure': HelpCircle,
}

const TREATMENT_LABELS: Record<string, string> = {
    'cpap_bipap': 'CPAP Therapy',
    'inspire': 'Inspire Therapy',
    'therapy_cbt': 'CBT-I (Cognitive Behavioral)',
    'sleep_study': 'Testing / Sleep Study',
    'medication': 'Medication Review',
    'not_sure': "Not sure — I'd like to learn more",
}

/* ─── Custom Tooltip ─── */
function CustomTooltip({ active, payload, label }: any) {
    if (!active || !payload?.length) return null
    return (
        <div className="bg-white/95 backdrop-blur-xl rounded-xl border border-gray-200/80 shadow-premium-lg px-4 py-3">
            <p className="text-xs font-medium text-gray-500 mb-1.5">{label}</p>
            {payload.map((entry: any, i: number) => (
                <div key={i} className="flex items-center gap-2 text-sm">
                    <div className="w-2 h-2 rounded-full" style={{ background: entry.color }} />
                    <span className="text-gray-600 capitalize">{entry.name}:</span>
                    <span className="font-semibold text-gray-900">{entry.value}</span>
                </div>
            ))}
        </div>
    )
}

/* ─── Retention cell color ─── */
function retentionColor(val: number): string {
    if (val >= 80) return 'bg-sleep-500 text-white'
    if (val >= 60) return 'bg-sleep-400 text-white'
    if (val >= 40) return 'bg-sleep-200 text-sleep-900'
    if (val >= 20) return 'bg-sleep-100 text-sleep-800'
    return 'bg-gray-100 text-gray-500'
}

/* ─── Main Component ─── */
export default function DashboardPage() {
    const { user } = useAuth()
    const [stats, setStats] = useState<DashboardStats>(defaultStats)
    const [conditions, setConditions] = useState<ConditionData[]>([])
    const [treatments, setTreatments] = useState<TreatmentData[]>([])
    const [trendView, setTrendView] = useState<'daily' | 'monthly'>('daily')
    const [dailyTrend, setDailyTrend] = useState<TrendPoint[]>([])
    const [monthlyTrend, setMonthlyTrend] = useState<TrendPoint[]>([])
    const [cohorts, setCohorts] = useState<CohortRow[]>([])
    const [cohortLabels, setCohortLabels] = useState<string[]>([])
    const [cohortKpis, setCohortKpis] = useState<{ avgRetention: string, bestCohort: string, totalPatients: number, trend: string }>({ avgRetention: '0%', bestCohort: 'N/A', totalPatients: 0, trend: '0%' })
    const [cohortDisplayMode, setCohortDisplayMode] = useState<'percent' | 'count'>('percent')
    const [cohortTimeFilter, setCohortTimeFilter] = useState<string>('6')
    const [cohortAvailableYears, setCohortAvailableYears] = useState<number[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [loadError, setLoadError] = useState<string | null>(null)

    /* ─── Cohort data fetcher (reusable for filter changes) ─── */
    const fetchCohortData = async (api: any, monthsParam: number, yearParam?: number) => {
        try {
            const params: any = yearParam ? { year: yearParam } : { months: monthsParam }
            const cohortRes = await api.get('/analytics/cohort-retention', { params })
            if (cohortRes.data) {
                setCohortLabels(cohortRes.data.period_labels || [])
                if (cohortRes.data.available_years?.length) {
                    setCohortAvailableYears(cohortRes.data.available_years)
                }
                // Filter out zero-size cohorts (like NeuroReach)
                const allCohorts = (cohortRes.data.cohorts || [])
                const nonEmptyCohorts = allCohorts.filter((c: any) => c.cohort_size > 0)
                setCohorts(nonEmptyCohorts.map((c: any) => ({
                    month: c.cohort,
                    total: c.cohort_size || 0,
                    retention: c.percentages || [],
                    periods: c.periods || [],
                })))
                // Compute cohort KPIs from real data (only non-empty cohorts)
                const totalPatients = nonEmptyCohorts.reduce((s: number, c: any) => s + (c.cohort_size || 0), 0)
                const retentionValues = nonEmptyCohorts
                    .filter((c: any) => c.percentages?.length > 1)
                    .map((c: any) => c.percentages[1] || 0)
                const avgRetention = retentionValues.length > 0
                    ? Math.round(retentionValues.reduce((a: number, b: number) => a + b, 0) / retentionValues.length)
                    : 0
                const bestCohortData = nonEmptyCohorts
                    .filter((c: any) => c.percentages?.length > 1)
                    .sort((a: any, b: any) => (b.percentages[1] || 0) - (a.percentages[1] || 0))[0]
                setCohortKpis({
                    avgRetention: `${avgRetention}%`,
                    bestCohort: bestCohortData ? `${bestCohortData.cohort}` : 'N/A',
                    totalPatients,
                    trend: '—',
                })
            }
        } catch { /* use empty */ }
    }

    /* ─── Handle cohort time filter change ─── */
    const handleCohortFilterChange = async (value: string) => {
        setCohortTimeFilter(value)
        try {
            const { default: api } = await import('../lib/api')
            const isYear = value.length === 4 && !isNaN(Number(value))
            if (isYear) {
                await fetchCohortData(api, 12, Number(value))
            } else {
                await fetchCohortData(api, Number(value))
            }
        } catch { /* ignore */ }
    }

    useEffect(() => {
        const fetchAll = async () => {
            try {
                const { default: api } = await import('../lib/api')

                // Fire ALL requests in parallel for maximum speed
                const [summaryRes, dailyRes, monthlyRes, condRes, treatRes] = await Promise.allSettled([
                    api.get('/analytics/dashboard-summary'),
                    api.get('/analytics/leads-trend', { params: { period: 30 } }),
                    api.get('/analytics/leads-trend', { params: { period: 90 } }),
                    api.get('/analytics/conditions-distribution'),
                    api.get('/analytics/sleep-treatment-distribution'),
                ])

                // 1. Dashboard Summary (KPIs)
                if (summaryRes.status === 'fulfilled' && summaryRes.value.data) {
                    const d = summaryRes.value.data
                    setStats({
                        total_leads: d.total_leads || 0,
                        converted_leads: d.converted_leads || 0,
                        conversion_rate: d.conversion_rate || 0,
                        scheduled_appointments: d.scheduled_appointments || 0,
                        total_leads_change: d.trends?.total_leads ?? 0,
                        converted_change: d.trends?.converted_leads ?? 0,
                        conversion_change: d.trends?.conversion_rate ?? 0,
                        scheduled_change: d.trends?.scheduled_appointments ?? 0,
                    })
                }

                // 2. Leads Trend (daily - 30 days)
                if (dailyRes.status === 'fulfilled' && dailyRes.value.data?.data) {
                    setDailyTrend(dailyRes.value.data.data.map((d: any) => ({
                        date: d.label,
                        leads: d.new_leads || 0,
                        converted: d.converted_leads || 0,
                    })))
                }

                // 3. Leads Trend (monthly - 90 days)
                if (monthlyRes.status === 'fulfilled' && monthlyRes.value.data?.data) {
                    const byMonth: Record<string, { leads: number, converted: number }> = {}
                    monthlyRes.value.data.data.forEach((d: any) => {
                        const monthKey = d.date?.substring(0, 7) || d.label
                        if (!byMonth[monthKey]) byMonth[monthKey] = { leads: 0, converted: 0 }
                        byMonth[monthKey].leads += d.new_leads || 0
                        byMonth[monthKey].converted += d.converted_leads || 0
                    })
                    setMonthlyTrend(Object.entries(byMonth).map(([key, val]) => {
                        const dt = new Date(key + '-01')
                        return {
                            date: dt.toLocaleDateString('en-US', { month: 'short' }),
                            leads: val.leads,
                            converted: val.converted,
                        }
                    }))
                }

                // 4. Conditions Distribution
                if (condRes.status === 'fulfilled') {
                    const apiConditions: Record<string, { count: number, percentage: number }> = {}
                    if (condRes.value.data?.conditions?.length) {
                        condRes.value.data.conditions.forEach((c: any) => {
                            apiConditions[c.condition] = { count: c.count || 0, percentage: c.percentage || 0 }
                        })
                    }
                    setConditions(ALL_CONDITIONS.map(key => ({
                        name: CONDITION_LABELS[key] || key.replace(/_/g, ' '),
                        count: apiConditions[key]?.count || 0,
                        percentage: apiConditions[key]?.percentage || 0,
                        color: CONDITION_COLORS[key] || '#8eb1d4',
                    })))
                }

                // 5. Treatment Interest Distribution
                if (treatRes.status === 'fulfilled') {
                    const apiTreatments: Record<string, { count: number, percentage: number, trend: number }> = {}
                    if (treatRes.value.data?.interests?.length) {
                        treatRes.value.data.interests.forEach((t: any) => {
                            apiTreatments[t.interest_type] = { count: t.count || 0, percentage: t.percentage || 0, trend: t.trend || 0 }
                        })
                    }
                    setTreatments(ALL_TREATMENTS.map(key => {
                        const data = apiTreatments[key]
                        return {
                            name: TREATMENT_LABELS[key] || key.replace(/_/g, ' '),
                            interest: data?.percentage || 0,
                            icon: TREATMENT_ICONS[key] || HelpCircle,
                            count: data?.count || 0,
                        }
                    }))
                }

                // 6. Cohort Retention (depends on api import, runs after parallel batch)
                await fetchCohortData(api, 6)
            } catch (err) {
                console.error('Dashboard load failed:', err)
                setLoadError('Unable to load dashboard data. Please refresh the page.')
            } finally {
                setIsLoading(false)
            }
        }
        fetchAll()
    }, [])

    const trendData = useMemo(() =>
        trendView === 'daily' ? dailyTrend : monthlyTrend
        , [trendView, dailyTrend, monthlyTrend])

    const totalTrendLeads = useMemo(() =>
        trendData.reduce((s, d) => s + d.leads, 0)
        , [trendData])

    const totalTrendConverted = useMemo(() =>
        trendData.reduce((s, d) => s + d.converted, 0)
        , [trendData])

    const greeting = () => {
        const hour = new Date().getHours()
        if (hour < 12) return 'Good morning'
        if (hour < 17) return 'Good afternoon'
        return 'Good evening'
    }

    /* ─── KPI card config ─── */
    const kpiCards = [
        {
            label: 'Total Leads',
            value: stats.total_leads,
            change: stats.total_leads_change,
            icon: Users,
            gradient: 'from-[#4A6FA5] to-[#6593be]',
        },
        {
            label: 'Converted Leads',
            value: stats.converted_leads,
            change: stats.converted_change,
            icon: UserCheck,
            gradient: 'from-[#26a9b5] to-[#41c5cf]',
        },
        {
            label: 'Conversion Rate',
            value: `${stats.conversion_rate}%`,
            change: stats.conversion_change,
            icon: TrendingUp,
            gradient: 'from-[#EE9A1D] to-[#f2b034]',
        },
        {
            label: 'Scheduled Appts',
            value: stats.scheduled_appointments,
            change: stats.scheduled_change,
            icon: CalendarCheck,
            gradient: 'from-[#344d72] to-[#4A6FA5]',
        },
    ]

    return (
        <div className="space-y-8 animate-fade-in">
            {/* ─── Header ─── */}
            <div className="flex items-end justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
                        {greeting()}{user?.first_name ? `, ${user.first_name}` : ''}
                    </h1>
                    <p className="text-gray-500 mt-1 text-[15px]">
                        Lead analytics and performance metrics overview
                    </p>
                </div>
                <div className="hidden sm:flex items-center gap-2 text-xs text-gray-400">
                    <Activity className="w-3.5 h-3.5" />
                    <span>Last updated: just now</span>
                </div>
            </div>

            {loadError && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 flex items-center gap-2">
                    <span className="font-medium">Error:</span> {loadError}
                    <button onClick={() => window.location.reload()} className="ml-auto text-xs font-semibold text-red-600 hover:text-red-800 underline">Refresh</button>
                </div>
            )}

            {/* ═══════════════════ 1. KPI Cards Row ═══════════════════ */}
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                {kpiCards.map((card) => (
                    <div
                        key={card.label}
                        className={`relative overflow-hidden rounded-2xl p-5 bg-gradient-to-br ${card.gradient} text-white shadow-md hover:shadow-lg transition-all duration-300 hover:-translate-y-0.5 group`}
                    >
                        {/* Background decoration */}
                        <div className="absolute top-0 right-0 w-24 h-24 rounded-full bg-white/10 -translate-y-6 translate-x-6 group-hover:scale-110 transition-transform duration-500" />
                        <div className="absolute bottom-0 left-0 w-16 h-16 rounded-full bg-white/5 translate-y-4 -translate-x-4" />

                        <div className="relative z-10">
                            <div className="flex items-center justify-between mb-3">
                                <div className="w-10 h-10 rounded-xl bg-white/15 backdrop-blur-sm flex items-center justify-center">
                                    <card.icon className="w-5 h-5 text-white" />
                                </div>
                                {card.change !== 0 && (
                                    <div className={`flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full ${card.change >= 0 ? 'bg-white/20 text-white' : 'bg-red-500/30 text-red-100'}`}>
                                        {card.change >= 0 ? (
                                            <ArrowUpRight className="w-3 h-3" />
                                        ) : (
                                            <ArrowDownRight className="w-3 h-3" />
                                        )}
                                        {Math.abs(card.change)}%
                                    </div>
                                )}
                            </div>
                            <p className="text-white/70 text-xs font-medium uppercase tracking-wider mb-1">{card.label}</p>
                            <p className="text-[1.75rem] font-bold leading-none">
                                {isLoading ? (
                                    <span className="inline-block w-16 h-8 bg-white/20 rounded animate-pulse" />
                                ) : (
                                    card.value
                                )}
                            </p>
                        </div>
                    </div>
                ))}
            </div>

            {/* ═══════════════════ 2. Leads Trend Chart ═══════════════════ */}
            <div className="chart-card">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h2 className="section-title">
                            <BarChart3 className="w-5 h-5 text-sleep-500" />
                            Leads Trend
                        </h2>
                        <div className="flex items-center gap-5 mt-2">
                            <div className="flex items-center gap-2">
                                <div className="w-2.5 h-2.5 rounded-full bg-sleep-500" />
                                <span className="text-sm text-gray-500">
                                    Total: <span className="font-semibold text-gray-900">{totalTrendLeads}</span>
                                </span>
                            </div>
                            <div className="flex items-center gap-2">
                                <div className="w-2.5 h-2.5 rounded-full bg-warm-400" />
                                <span className="text-sm text-gray-500">
                                    Converted: <span className="font-semibold text-gray-900">{totalTrendConverted}</span>
                                </span>
                            </div>
                        </div>
                    </div>
                    <div className="toggle-pill">
                        <button
                            className={trendView === 'daily' ? 'active' : ''}
                            onClick={() => setTrendView('daily')}
                        >
                            Daily
                        </button>
                        <button
                            className={trendView === 'monthly' ? 'active' : ''}
                            onClick={() => setTrendView('monthly')}
                        >
                            Monthly
                        </button>
                    </div>
                </div>

                {trendData.length === 0 && !isLoading ? (
                    <div className="h-[280px] flex items-center justify-center">
                        <div className="text-center">
                            <BarChart3 className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                            <p className="text-sm text-gray-400">No trend data yet. Leads will appear here as they come in.</p>
                        </div>
                    </div>
                ) : (
                    <div className="h-[280px] -ml-2">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={trendData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                                <defs>
                                    <linearGradient id="gradLeads" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#4A6FA5" stopOpacity={0.25} />
                                        <stop offset="100%" stopColor="#4A6FA5" stopOpacity={0.02} />
                                    </linearGradient>
                                    <linearGradient id="gradConverted" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#EE9A1D" stopOpacity={0.2} />
                                        <stop offset="100%" stopColor="#EE9A1D" stopOpacity={0.02} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                                <XAxis
                                    dataKey="date"
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{ fontSize: 11, fill: '#9ca3af' }}
                                    dy={8}
                                />
                                <YAxis
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{ fontSize: 11, fill: '#9ca3af' }}
                                    dx={-4}
                                    allowDecimals={false}
                                />
                                <Tooltip content={<CustomTooltip />} />
                                <Area
                                    type="monotone"
                                    dataKey="leads"
                                    stroke="#4A6FA5"
                                    strokeWidth={2.5}
                                    fill="url(#gradLeads)"
                                    name="Leads"
                                />
                                <Area
                                    type="monotone"
                                    dataKey="converted"
                                    stroke="#EE9A1D"
                                    strokeWidth={2}
                                    fill="url(#gradConverted)"
                                    name="Converted"
                                    strokeDasharray="5 3"
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                )}
            </div>

            {/* ═══════════════════ 3 & 4. Conditions + Treatment Interest ═══════════════════ */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Leading Conditions */}
                <div className="chart-card">
                    <div className="flex items-center justify-between mb-5">
                        <h2 className="section-title">
                            <Moon className="w-5 h-5 text-sleep-500" />
                            Leading Conditions
                        </h2>
                        <button className="text-xs text-sleep-500 font-medium flex items-center gap-1 hover:text-sleep-700 transition-colors">
                            View all <ChevronRight className="w-3.5 h-3.5" />
                        </button>
                    </div>
                    {conditions.length > 0 ? (
                        <div className="space-y-4">
                            {conditions.map((cond) => {
                                const pct = cond.percentage || 0
                                return (
                                    <div key={cond.name}>
                                        <div className="flex items-center justify-between mb-1.5">
                                            <span className="text-sm font-medium text-gray-700">{cond.name}</span>
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs text-gray-400">{cond.count} lead{cond.count !== 1 ? 's' : ''}</span>
                                                <span className="text-sm font-semibold text-gray-900">{pct}%</span>
                                            </div>
                                        </div>
                                        <div className="w-full h-2.5 bg-gray-100 rounded-full overflow-hidden">
                                            <div
                                                className="h-full rounded-full transition-all duration-700 ease-out"
                                                style={{
                                                    width: `${Math.max(pct, 2)}%`,
                                                    background: `linear-gradient(90deg, ${cond.color}, ${cond.color}cc)`,
                                                }}
                                            />
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    ) : (
                        <div className="text-center py-8 bg-gray-50 rounded-xl">
                            <Moon className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                            <p className="text-sm text-gray-400">No condition data yet. Leads will appear here as they come in.</p>
                        </div>
                    )}
                </div>

                {/* Treatment Interest */}
                <div className="chart-card">
                    <div className="flex items-center justify-between mb-5">
                        <h2 className="section-title">
                            <Activity className="w-5 h-5 text-teal-500" />
                            Treatment Interest
                        </h2>
                        <button className="text-xs text-sleep-500 font-medium flex items-center gap-1 hover:text-sleep-700 transition-colors">
                            View details <ChevronRight className="w-3.5 h-3.5" />
                        </button>
                    </div>
                    {treatments.length > 0 ? (
                        <div className="space-y-3">
                            {treatments.map((item) => (
                                <div
                                    key={item.name}
                                    className="flex items-center gap-3 p-3 rounded-xl bg-gray-50/60 hover:bg-gray-50 transition-colors group"
                                >
                                    <div className="w-9 h-9 rounded-lg bg-gray-100 border border-gray-200/60 flex items-center justify-center">
                                        <item.icon className="w-4 h-4 text-gray-500" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="mb-1.5 flex items-center justify-between">
                                            <span className="text-sm font-medium text-gray-700">{item.name}</span>
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs text-gray-400">{item.count} lead{item.count !== 1 ? 's' : ''}</span>
                                                <span className="text-sm font-semibold text-gray-900">{item.interest.toFixed(1)}%</span>
                                            </div>
                                        </div>
                                        <div className="w-full h-1.5 bg-gray-200 rounded-full overflow-hidden">
                                            <div
                                                className="h-full rounded-full bg-gradient-to-r from-teal-500 to-teal-400 transition-all duration-700"
                                                style={{ width: `${Math.max(item.interest, 2)}%` }}
                                            />
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="text-center py-8 bg-gray-50 rounded-xl">
                            <Activity className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                            <p className="text-sm text-gray-400">No treatment interest data yet. Leads will appear here as they come in.</p>
                        </div>
                    )}
                </div>
            </div>

            {/* ═══════════════════ 5. Monthly Cohort Retention Analysis ═══════════════════ */}
            <div className="chart-card">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h2 className="section-title">
                            <TrendingUp className="w-5 h-5 text-sleep-500" />
                            Monthly Cohort Retention Analysis
                        </h2>
                        <p className="text-sm text-gray-400 mt-1">
                            Patient engagement retention across monthly cohorts
                        </p>
                    </div>
                    <div className="flex items-center gap-3">
                        {/* Display mode toggle (% vs #) */}
                        <div className="toggle-pill">
                            <button
                                className={cohortDisplayMode === 'percent' ? 'active' : ''}
                                onClick={() => setCohortDisplayMode('percent')}
                            >
                                %
                            </button>
                            <button
                                className={cohortDisplayMode === 'count' ? 'active' : ''}
                                onClick={() => setCohortDisplayMode('count')}
                            >
                                #
                            </button>
                        </div>
                        {/* Time filter dropdown */}
                        <select
                            className="text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 bg-white text-gray-600 font-medium focus:outline-none focus:ring-2 focus:ring-sleep-500/30"
                            value={cohortTimeFilter}
                            onChange={(e) => handleCohortFilterChange(e.target.value)}
                        >
                            <option value="1">Last 1 month</option>
                            <option value="3">Last 3 months</option>
                            <option value="6">Last 6 months</option>
                            <option value="12">Last 12 months</option>
                            {cohortAvailableYears.map((yr: number) => (
                                <option key={yr} value={String(yr)}>Year {yr}</option>
                            ))}
                        </select>
                    </div>
                </div>

                {/* Cohort KPI summary */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
                    {[
                        { label: 'Avg. Retention', value: cohortKpis.avgRetention, sub: 'across all cohorts' },
                        { label: 'Best Cohort', value: cohortKpis.bestCohort, sub: 'highest contacted rate' },
                        { label: 'Total Patients', value: String(cohortKpis.totalPatients), sub: `${cohortTimeFilter.length === 4 ? cohortTimeFilter : cohortTimeFilter + '-month'} window` },
                        { label: 'Trend', value: cohortKpis.trend, sub: 'vs prior period' },
                    ].map((kpi) => (
                        <div key={kpi.label} className="bg-gray-50 rounded-xl p-3.5">
                            <p className="text-xs text-gray-400 font-medium mb-0.5">{kpi.label}</p>
                            <p className="text-lg font-bold text-gray-900">{kpi.value}</p>
                            <p className="text-[11px] text-gray-400">{kpi.sub}</p>
                        </div>
                    ))}
                </div>

                {/* Retention table */}
                {cohorts.length > 0 ? (
                    <div className="overflow-x-auto -mx-6 px-6">
                        <table className="w-full min-w-[600px]">
                            <thead>
                                <tr>
                                    <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider pb-3 pr-4">Cohort</th>
                                    <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider pb-3 pr-4">Patients</th>
                                    {(cohortLabels.length > 0 ? cohortLabels : ['Initial', 'Contacted', 'Scheduled', 'Completed', 'Active', 'Retained']).map((label: string) => (
                                        <th key={label} className="text-center text-xs font-semibold text-gray-500 uppercase tracking-wider pb-3 px-1">{label}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {cohorts.map((row: CohortRow, ri: number) => (
                                    <tr key={row.month} className={ri % 2 === 0 ? 'bg-gray-50/50' : ''}>
                                        <td className="py-2.5 pr-4 text-sm font-medium text-gray-700">{row.month}</td>
                                        <td className="py-2.5 pr-4 text-sm font-semibold text-gray-900">{row.total}</td>
                                        {Array.from({ length: cohortLabels.length || 6 }, (_, ci: number) => {
                                            const pctVal = row.retention[ci]
                                            const countVal = row.periods?.[ci]
                                            const displayVal = cohortDisplayMode === 'count' ? countVal : pctVal
                                            return (
                                                <td key={ci} className="py-2.5 px-1 text-center">
                                                    {displayVal !== undefined ? (
                                                        <span className={`inline-flex items-center justify-center w-12 h-7 rounded-md text-xs font-semibold ${retentionColor(pctVal ?? 0)}`}>
                                                            {cohortDisplayMode === 'count' ? displayVal : `${displayVal}%`}
                                                        </span>
                                                    ) : (
                                                        <span className="text-gray-300 text-xs">—</span>
                                                    )}
                                                </td>
                                            )
                                        })}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <div className="text-center py-8 bg-gray-50 rounded-xl">
                        <TrendingUp className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                        <p className="text-sm text-gray-400">No cohort data yet. Data will appear here as leads progress through the pipeline.</p>
                    </div>
                )}
            </div>
        </div>
    )
}
