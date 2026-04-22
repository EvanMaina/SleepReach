import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import {
    LayoutDashboard, Headphones, Users, Trash2,
    Stethoscope, BarChart3, Settings, LogOut, ChevronLeft,
    ChevronDown, ChevronUp, Inbox, Phone, Clock, PhoneOff, Calendar,
    CheckCircle2, XCircle, Flame, Diamond, CircleDot, Sparkles,
    Moon, Sun, Camera
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import { useState, useEffect, useRef } from 'react'

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
    const [darkMode, setDarkMode] = useState(() => localStorage.getItem('sleepreach_theme') === 'dark')
    const avatarKey = `sleepreach_avatar_${user?.id || 'anon'}`
    const [profilePic, setProfilePic] = useState<string | null>(() => localStorage.getItem(`sleepreach_avatar_${user?.id || 'anon'}`))
    const avatarInputRef = useRef<HTMLInputElement>(null)
    const [userMenuOpen, setUserMenuOpen] = useState(false)
    const userMenuRef = useRef<HTMLDivElement>(null)

    // Close the profile menu on outside click, Escape, or route change
    useEffect(() => {
        if (!userMenuOpen) return
        const handleClickOutside = (event: MouseEvent) => {
            if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
                setUserMenuOpen(false)
            }
        }
        const handleEscape = (event: KeyboardEvent) => {
            if (event.key === 'Escape') setUserMenuOpen(false)
        }
        document.addEventListener('mousedown', handleClickOutside)
        document.addEventListener('keydown', handleEscape)
        return () => {
            document.removeEventListener('mousedown', handleClickOutside)
            document.removeEventListener('keydown', handleEscape)
        }
    }, [userMenuOpen])

    useEffect(() => { setUserMenuOpen(false) }, [location.pathname])
    useEffect(() => { if (collapsed) setUserMenuOpen(false) }, [collapsed])

    const handleAvatarFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file) return
        const validTypes = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']
        if (!validTypes.includes(file.type)) {
            toast.error('Please upload a valid image (PNG, JPG, WebP, or GIF)')
            e.target.value = ''
            return
        }
        if (file.size > 2 * 1024 * 1024) {
            toast.error('Image must be under 2MB')
            e.target.value = ''
            return
        }
        const reader = new FileReader()
        reader.onload = () => {
            const dataUrl = reader.result as string
            setProfilePic(dataUrl)
            localStorage.setItem(avatarKey, dataUrl)
            toast.success('Profile photo updated')
        }
        reader.onerror = () => toast.error('Failed to read image file')
        reader.readAsDataURL(file)
        e.target.value = ''
    }

    const handleRemovePhoto = () => {
        setProfilePic(null)
        localStorage.removeItem(avatarKey)
        toast.success('Photo removed')
    }

    // Sync avatar when user changes (different login)
    useEffect(() => {
        if (user?.id) {
            setProfilePic(localStorage.getItem(`sleepreach_avatar_${user.id}`))
        }
    }, [user?.id])

    const toggleTheme = () => {
        const next = !darkMode
        setDarkMode(next)
        localStorage.setItem('sleepreach_theme', next ? 'dark' : 'light')
        if (next) {
            document.documentElement.classList.add('dark')
        } else {
            document.documentElement.classList.remove('dark')
        }
    }

    // Apply saved theme on mount
    useEffect(() => {
        if (darkMode) document.documentElement.classList.add('dark')
        else document.documentElement.classList.remove('dark')
    }, [])

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

                {/* Remaining nav items — Settings visible to primary_admin and administrators */}
                {navigation.slice(1).filter((item) =>
                    item.name !== 'Settings' || ['primary_admin', 'administrator'].includes(user?.role || '')
                ).map((item) => (
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

            {/* ─── Profile Section (SaaS-pattern: clickable trigger → popover menu) ─── */}
            <div className="border-t border-gray-100 px-3 py-3">
                {/* Hidden file input — shared by avatar hover + "Change photo" button */}
                {user && (
                    <input
                        ref={avatarInputRef}
                        type="file"
                        accept="image/png,image/jpeg,image/webp,image/gif"
                        className="hidden"
                        onChange={handleAvatarFileChange}
                    />
                )}

                {/* Expanded mode — full clickable profile button with dropdown menu */}
                {user && !collapsed && (
                    <div ref={userMenuRef} className="relative">
                        {/* Popover menu (opens upward above the trigger) */}
                        {userMenuOpen && (
                            <div
                                role="menu"
                                className="absolute bottom-full left-0 right-0 mb-2 rounded-2xl border border-gray-200/80 bg-white shadow-[0_18px_40px_-12px_rgba(0,0,0,0.18)] overflow-hidden z-50"
                            >
                                {/* Identity header */}
                                <div className="p-4 border-b border-gray-100 bg-gradient-to-b from-gray-50/80 to-white">
                                    <div className="flex items-start gap-3">
                                        <button
                                            onClick={() => avatarInputRef.current?.click()}
                                            className="relative group shrink-0 rounded-full"
                                            aria-label={profilePic ? 'Change profile photo' : 'Upload profile photo'}
                                        >
                                            {profilePic ? (
                                                <img src={profilePic} alt="" className="w-14 h-14 rounded-full object-cover shadow-sm ring-2 ring-white" />
                                            ) : (
                                                <div className="w-14 h-14 rounded-full bg-gradient-to-br from-sleep-500 to-sleep-700 flex items-center justify-center text-white text-base font-bold shadow-sm ring-2 ring-white">
                                                    {user.first_name[0]}{user.last_name[0]}
                                                </div>
                                            )}
                                            <div className="absolute inset-0 rounded-full bg-black/0 group-hover:bg-black/45 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all">
                                                <Camera className="w-4 h-4 text-white" />
                                            </div>
                                        </button>
                                        <div className="min-w-0 flex-1 pt-0.5">
                                            <p className="text-sm font-semibold text-gray-900 truncate leading-tight">
                                                {user.first_name} {user.last_name}
                                            </p>
                                            <p className="text-[11px] text-gray-500 truncate mt-0.5">{user.email}</p>
                                            <span className="inline-flex mt-1.5 rounded-md bg-sleep-50 text-sleep-700 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider capitalize">
                                                {user.role.replace(/_/g, ' ')}
                                            </span>
                                        </div>
                                    </div>
                                    <div className="mt-3 flex items-center gap-2">
                                        <button
                                            onClick={() => avatarInputRef.current?.click()}
                                            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-colors shadow-sm"
                                        >
                                            <Camera className="w-3 h-3" />
                                            {profilePic ? 'Change photo' : 'Upload photo'}
                                        </button>
                                        {profilePic && (
                                            <button
                                                onClick={handleRemovePhoto}
                                                className="text-[11px] font-medium text-red-500 hover:text-red-600 transition-colors px-1"
                                            >
                                                Remove
                                            </button>
                                        )}
                                    </div>
                                    <p className="mt-2.5 text-[10px] text-gray-400">
                                        PNG, JPG, WebP, or GIF — up to 2MB
                                    </p>
                                </div>

                                {/* Appearance */}
                                <div className="py-1.5">
                                    <button
                                        role="menuitem"
                                        onClick={toggleTheme}
                                        className="flex items-center gap-3 w-full px-4 py-2 text-[13px] font-medium text-gray-700 hover:bg-gray-50 transition-colors"
                                    >
                                        {darkMode ? <Sun className="w-4 h-4 shrink-0 text-amber-500" /> : <Moon className="w-4 h-4 shrink-0 text-gray-500" />}
                                        <span className="flex-1 text-left">Dark mode</span>
                                        <span
                                            className={clsx(
                                                'relative inline-flex h-[18px] w-8 shrink-0 rounded-full transition-colors',
                                                darkMode ? 'bg-sleep-600' : 'bg-gray-300'
                                            )}
                                            aria-hidden="true"
                                        >
                                            <span
                                                className={clsx(
                                                    'absolute top-[2px] h-[14px] w-[14px] rounded-full bg-white shadow transition-all',
                                                    darkMode ? 'left-[16px]' : 'left-[2px]'
                                                )}
                                            />
                                        </span>
                                    </button>
                                </div>

                                {/* Sign out */}
                                <div className="border-t border-gray-100 py-1.5">
                                    <button
                                        role="menuitem"
                                        onClick={() => { setUserMenuOpen(false); handleLogout() }}
                                        className="flex items-center gap-3 w-full px-4 py-2 text-[13px] font-medium text-gray-600 hover:text-red-600 hover:bg-red-50 transition-colors"
                                    >
                                        <LogOut className="w-4 h-4 shrink-0" />
                                        <span>Sign out</span>
                                    </button>
                                </div>
                            </div>
                        )}

                        {/* Trigger — premium clickable profile card */}
                        <button
                            onClick={() => setUserMenuOpen((v) => !v)}
                            aria-haspopup="menu"
                            aria-expanded={userMenuOpen}
                            title="Manage your account"
                            className={clsx(
                                'group relative w-full flex items-center gap-3 px-2.5 py-2 rounded-xl text-left',
                                'border transition-all duration-200',
                                'focus:outline-none focus-visible:ring-2 focus-visible:ring-sleep-400/40',
                                userMenuOpen
                                    ? 'bg-white border-gray-300/80 shadow-md'
                                    : 'bg-gradient-to-br from-gray-50/90 to-white border-gray-200/70 shadow-sm hover:border-gray-300/80 hover:shadow-md hover:-translate-y-[0.5px]'
                            )}
                        >
                            {/* Avatar with online presence dot */}
                            <div className="relative shrink-0">
                                {profilePic ? (
                                    <img src={profilePic} alt="" className="w-9 h-9 rounded-full object-cover shadow-sm ring-2 ring-white" />
                                ) : (
                                    <div className="w-9 h-9 rounded-full bg-gradient-to-br from-sleep-500 to-sleep-700 flex items-center justify-center text-white text-[11px] font-bold shadow-sm ring-2 ring-white">
                                        {user.first_name[0]}{user.last_name[0]}
                                    </div>
                                )}
                                <span
                                    className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-white"
                                    aria-label="Online"
                                />
                            </div>

                            {/* Name + role */}
                            <div className="min-w-0 flex-1">
                                <p className="text-[13px] font-semibold text-gray-900 dark:text-gray-100 truncate leading-tight">
                                    {user.first_name} {user.last_name}
                                </p>
                                <p className="text-[11px] text-gray-500 truncate capitalize leading-tight mt-0.5">
                                    {user.role.replace(/_/g, ' ')}
                                </p>
                            </div>

                            {/* Chevron badge — unmistakable click affordance */}
                            <span
                                className={clsx(
                                    'flex items-center justify-center w-6 h-6 rounded-md border transition-all duration-200 shrink-0',
                                    userMenuOpen
                                        ? 'bg-sleep-50 border-sleep-200'
                                        : 'bg-white border-gray-200/70 group-hover:bg-sleep-50/60 group-hover:border-sleep-200/80'
                                )}
                                aria-hidden="true"
                            >
                                <ChevronUp
                                    className={clsx(
                                        'w-3.5 h-3.5 transition-all duration-200',
                                        userMenuOpen ? 'rotate-180 text-sleep-700' : 'text-gray-500 group-hover:text-sleep-700'
                                    )}
                                />
                            </span>
                        </button>
                    </div>
                )}

                {/* Collapsed mode — compact sign-out only */}
                {collapsed && (
                    <button
                        onClick={handleLogout}
                        className="flex items-center justify-center w-full px-3 py-2 rounded-xl text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                        title="Sign out"
                        aria-label="Sign out"
                    >
                        <LogOut className="w-[17px] h-[17px] shrink-0" />
                    </button>
                )}
            </div>
        </aside>
    )
}
