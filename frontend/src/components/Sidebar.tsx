import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import {
    LayoutDashboard, Headphones, Users, Trash2,
    Stethoscope, BarChart3, Settings, LogOut, ChevronLeft,
    ChevronDown, Inbox, Phone, Clock, PhoneOff, Calendar,
    CheckCircle2, XCircle, Flame, Diamond, CircleDot, Sparkles
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import clsx from 'clsx'
import { useState, useEffect } from 'react'

/* ─── Queue definitions for Coordinator sub-items ─── */
const coordinatorQueues = [
    { key: 'new', label: 'New Leads', icon: Inbox },
    { key: 'contacted', label: 'Contacted', icon: Phone },
    { key: 'follow_up', label: 'Follow-up', icon: Clock },
    { key: 'callback', label: 'Callback', icon: PhoneOff },
    { key: 'scheduled', label: 'Scheduled', icon: Calendar },
    { key: 'completed', label: 'Completed', icon: CheckCircle2 },
    { key: 'unreachable', label: 'Unreachable', icon: XCircle },
    { key: 'not_interested', label: 'Not Interested', icon: XCircle },
    { key: 'hot', label: 'Hot Priority', icon: Flame },
    { key: 'medium', label: 'Medium Priority', icon: Diamond },
    { key: 'low', label: 'Low Priority', icon: CircleDot },
]

/* ─── Standard nav items ─── */
const navigation = [
    { name: 'Dashboard', href: '/', icon: LayoutDashboard },
    { name: 'All Leads', href: '/leads', icon: Users },
    { name: 'Deleted Leads', href: '/deleted', icon: Trash2 },
    { name: 'Providers', href: '/providers', icon: Stethoscope },
    { name: 'Analytics', href: '/analytics', icon: BarChart3 },
    { name: 'AI Insights', href: '/ai-insights', icon: Sparkles },
    { name: 'Settings', href: '/settings', icon: Settings },
]

export default function Sidebar() {
    const { user, logout } = useAuth()
    const navigate = useNavigate()
    const location = useLocation()
    const [collapsed, setCollapsed] = useState(() => window.innerWidth < 1280)
    const [coordinatorExpanded, setCoordinatorExpanded] = useState(false)

    // Auto-collapse sidebar on screens smaller than xl (1280px)
    useEffect(() => {
        const handleResize = () => {
            if (window.innerWidth < 1280) setCollapsed(true)
        }
        window.addEventListener('resize', handleResize)
        return () => window.removeEventListener('resize', handleResize)
    }, [])

    const isCoordinatorRoute = location.pathname.startsWith('/coordinator')
    useEffect(() => {
        if (isCoordinatorRoute) setCoordinatorExpanded(true)
    }, [isCoordinatorRoute])

    const activeQueue = isCoordinatorRoute
        ? (location.pathname.split('/coordinator/')[1] || 'new')
        : ''

    const handleLogout = () => {
        logout()
        navigate('/login')
    }

    const handleCoordinatorClick = () => {
        if (collapsed) {
            setCollapsed(false)
            setCoordinatorExpanded(true)
            navigate('/coordinator/new')
        } else {
            if (!coordinatorExpanded) {
                setCoordinatorExpanded(true)
                if (!isCoordinatorRoute) navigate('/coordinator/new')
            } else {
                setCoordinatorExpanded(false)
            }
        }
    }

    const handleQueueClick = (queueKey: string) => navigate(`/coordinator/${queueKey}`)

    useEffect(() => {
        if (!isCoordinatorRoute) setCoordinatorExpanded(false)
    }, [isCoordinatorRoute])

    return (
        <aside
            className={clsx(
                'fixed inset-y-0 left-0 z-30 flex flex-col bg-white border-r border-gray-200/80 transition-all duration-200 ease-out',
                'hidden md:flex',  // Hidden on mobile, visible on tablet+
                collapsed ? 'w-[72px]' : 'w-[260px]'
            )}
        >
            {/* Brand — Sleep Institute Logo */}
            <div className="flex items-center gap-3 h-[60px] px-4 border-b border-gray-100 shrink-0">
                <div className="w-9 h-9 rounded-xl bg-sleep-900 flex items-center justify-center shrink-0 overflow-hidden p-[3px]">
                    <img
                        src="/images/sleep-logo.png"
                        alt="Sleep Institute"
                        className="w-full h-full object-contain"
                        style={{ filter: 'brightness(0) invert(1) opacity(0.9)' }}
                    />
                </div>
                {!collapsed && (
                    <div className="flex flex-col min-w-0">
                        <span className="text-[15px] font-bold text-gray-900 tracking-tight leading-tight">SleepReach</span>
                        <span className="text-[10px] text-gray-400 truncate">Sleep Institute of Arizona</span>
                    </div>
                )}
                <button
                    onClick={() => setCollapsed(!collapsed)}
                    className={clsx(
                        'ml-auto w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-all',
                        collapsed && 'ml-0'
                    )}
                >
                    <ChevronLeft className={clsx('w-4 h-4 transition-transform', collapsed && 'rotate-180')} />
                </button>
            </div>

            {/* Navigation */}
            <nav className="flex-1 py-3 px-3 space-y-0.5 overflow-y-auto">
                {/* Dashboard */}
                <NavLink
                    to="/"
                    end
                    className={({ isActive }) =>
                        clsx(
                            'flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13.5px] font-medium transition-all duration-150',
                            isActive
                                ? 'bg-sleep-50 text-sleep-800 shadow-sm border border-sleep-100/60'
                                : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'
                        )
                    }
                >
                    <LayoutDashboard className="w-[18px] h-[18px] shrink-0" />
                    {!collapsed && <span>Dashboard</span>}
                </NavLink>

                {/* Coordinator with expandable queues */}
                <div>
                    <button
                        onClick={handleCoordinatorClick}
                        className={clsx(
                            'w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13.5px] font-medium transition-all duration-150',
                            isCoordinatorRoute
                                ? 'bg-sleep-50 text-sleep-800 shadow-sm border border-sleep-100/60'
                                : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'
                        )}
                    >
                        <Headphones className="w-[18px] h-[18px] shrink-0" />
                        {!collapsed && (
                            <>
                                <span className="flex-1 text-left">Coordinator</span>
                                <ChevronDown
                                    className={clsx(
                                        'w-4 h-4 text-gray-400 transition-transform duration-200',
                                        coordinatorExpanded && 'rotate-180'
                                    )}
                                />
                            </>
                        )}
                    </button>

                    {coordinatorExpanded && !collapsed && (
                        <div className="mt-1 ml-[18px] pl-4 border-l-2 border-sleep-100 space-y-0.5">
                            {coordinatorQueues.map((q) => (
                                <button
                                    key={q.key}
                                    onClick={() => handleQueueClick(q.key)}
                                    className={clsx(
                                        'w-full flex items-center gap-2.5 px-3 py-[7px] rounded-lg text-[13px] font-medium transition-all duration-150',
                                        activeQueue === q.key
                                            ? 'bg-sleep-100/80 text-sleep-800 font-semibold'
                                            : 'text-gray-500 hover:text-gray-800 hover:bg-gray-50'
                                    )}
                                >
                                    <q.icon className="w-[15px] h-[15px] shrink-0" />
                                    <span className="truncate">{q.label}</span>
                                </button>
                            ))}
                        </div>
                    )}
                </div>

                {/* Remaining nav items */}
                {navigation.slice(1).map((item) => (
                    <NavLink
                        key={item.name}
                        to={item.href}
                        className={({ isActive }) =>
                            clsx(
                                'flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13.5px] font-medium transition-all duration-150',
                                isActive
                                    ? 'bg-sleep-50 text-sleep-800 shadow-sm border border-sleep-100/60'
                                    : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'
                            )
                        }
                    >
                        <item.icon className="w-[18px] h-[18px] shrink-0" />
                        {!collapsed && <span>{item.name}</span>}
                    </NavLink>
                ))}
            </nav>

            {/* User section */}
            <div className="border-t border-gray-100 px-3 py-3 space-y-2">
                {user && !collapsed && (
                    <div className="flex items-center gap-3 px-3 py-2.5">
                        <div className="w-9 h-9 rounded-full bg-gradient-to-br from-sleep-500 to-sleep-700 flex items-center justify-center text-white text-[11px] font-bold shrink-0 shadow-sm">
                            {user.first_name[0]}{user.last_name[0]}
                        </div>
                        <div className="min-w-0">
                            <p className="text-[13px] font-semibold text-gray-900 truncate leading-tight">
                                {user.first_name} {user.last_name}
                            </p>
                            <p className="text-[11px] text-gray-400 truncate capitalize leading-tight mt-0.5">
                                {user.role.replace(/_/g, ' ')}
                            </p>
                        </div>
                    </div>
                )}
                <button
                    onClick={handleLogout}
                    className={clsx(
                        'flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-150',
                        'text-gray-400 hover:text-red-600 hover:bg-red-50',
                        collapsed && 'justify-center'
                    )}
                >
                    <LogOut className="w-[17px] h-[17px] shrink-0" />
                    {!collapsed && <span>Sign out</span>}
                </button>
            </div>
        </aside>
    )
}
