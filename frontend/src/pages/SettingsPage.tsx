import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import {
    Bell,
    Building2,
    Check,
    CheckCircle2,
    Edit3,
    Loader2,
    Mail,
    MapPin,
    Phone,
    Save,
    Settings,
    Shield,
    Trash2,
    UserPlus,
    Users,
    X,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { usersAPI } from '../lib/api'

interface TeamUser {
    id: string
    email: string
    first_name: string
    last_name: string
    role: string
    status: string
    last_login?: string | null
}

interface ClinicSettings {
    clinic_name: string
    clinic_address: string
    clinic_phone: string
    clinic_email: string
}

interface Preferences {
    notify_new_lead: boolean
    notify_hot_lead: boolean
    notify_daily_summary: boolean
}

const ROLE_OPTIONS = [
    { value: 'primary_admin', label: 'Primary Admin' },
    { value: 'administrator', label: 'Administrator' },
    { value: 'coordinator', label: 'Coordinator' },
    { value: 'specialist', label: 'Specialist' },
]

const ROLE_MATRIX = [
    {
        role: 'primary_admin',
        label: 'Primary Admin',
        description: 'Top-level owner with full authority and highest-rank protection.',
        perms: ['View Leads', 'Edit Leads', 'Delete Leads', 'View Analytics', 'Manage Users', 'Manage Admins', 'View Settings'],
    },
    {
        role: 'administrator',
        label: 'Administrator',
        description: 'Full operational access for clinic configuration and team management.',
        perms: ['View Leads', 'Edit Leads', 'Delete Leads', 'View Analytics', 'Manage Users', 'View Settings'],
    },
    {
        role: 'coordinator',
        label: 'Coordinator',
        description: 'Lead outreach, scheduling, and patient communication workflows.',
        perms: ['View Leads', 'Edit Leads', 'View Analytics'],
    },
    {
        role: 'specialist',
        label: 'Specialist',
        description: 'Read-focused access for clinical review and follow-through.',
        perms: ['View Leads'],
    },
]

const ALL_PERMISSIONS = [
    'View Leads',
    'Edit Leads',
    'Delete Leads',
    'View Analytics',
    'Manage Users',
    'Manage Admins',
    'View Settings',
]

function parseApiError(err: unknown, fallback: string) {
    const detail = (err as any)?.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) return detail.trim()
    if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
    if (err instanceof Error && err.message) return err.message
    return fallback
}

function roleBadge(role: string) {
    const map: Record<string, string> = {
        primary_admin: 'bg-indigo-600 text-white',
        administrator: 'bg-purple-500 text-white',
        coordinator: 'bg-blue-500 text-white',
        specialist: 'bg-emerald-500 text-white',
    }
    return map[role] || map.specialist
}

function statusBadge(status: string) {
    const map: Record<string, string> = {
        active: 'bg-emerald-50 text-emerald-700',
        inactive: 'bg-gray-100 text-gray-600',
        pending: 'bg-amber-50 text-amber-700',
    }
    return map[status] || map.inactive
}

function UserModal({
    isOpen,
    title,
    user,
    error,
    isSaving,
    onClose,
    onSubmit,
}: {
    isOpen: boolean
    title: string
    user: { first_name: string; last_name: string; email: string; role: string; status?: string }
    error: string | null
    isSaving: boolean
    onClose: () => void
    onSubmit: (event: FormEvent) => void
}) {
    if (!isOpen) return null

    return (
        <div
            className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-4"
            onClick={onClose}
        >
            <div
                className="w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-2xl"
                onClick={(event) => event.stopPropagation()}
            >
                <div className="flex items-center justify-between border-b border-gray-200 bg-gradient-to-r from-sleep-50 via-white to-white px-6 py-5">
                    <div>
                        <h2 className="text-xl font-bold text-gray-900">{title}</h2>
                        <p className="text-sm text-gray-500">
                            Manage team access with NeuroReach-style controls.
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        className="rounded-xl p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                    >
                        <X size={20} />
                    </button>
                </div>

                <form onSubmit={onSubmit} className="space-y-4 px-6 py-6">
                    {error ? (
                        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                            {error}
                        </div>
                    ) : null}

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">
                                First Name
                            </label>
                            <input
                                name="first_name"
                                defaultValue={user.first_name}
                                required
                                className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                            />
                        </div>
                        <div>
                            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">
                                Last Name
                            </label>
                            <input
                                name="last_name"
                                defaultValue={user.last_name}
                                required
                                className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                            />
                        </div>
                    </div>

                    <div>
                        <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">
                            Email
                        </label>
                        <input
                            name="email"
                            type="email"
                            defaultValue={user.email}
                            required
                            disabled={Boolean(user.email && title === 'Edit User')}
                            className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm disabled:bg-gray-50 disabled:text-gray-400 focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                        />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">
                                Role
                            </label>
                            <select
                                name="role"
                                defaultValue={user.role}
                                className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                            >
                                {ROLE_OPTIONS.map((option) => (
                                    <option key={option.value} value={option.value}>
                                        {option.label}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">
                                Status
                            </label>
                            <select
                                name="status"
                                defaultValue={user.status || 'active'}
                                className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                            >
                                <option value="active">Active</option>
                                <option value="pending">Pending</option>
                                <option value="inactive">Inactive</option>
                            </select>
                        </div>
                    </div>

                    <div className="flex items-center justify-end gap-3 border-t border-gray-200 pt-4">
                        <button
                            type="button"
                            onClick={onClose}
                            className="rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={isSaving}
                            className="inline-flex items-center gap-2 rounded-xl bg-sleep-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-sleep-700 disabled:opacity-60"
                        >
                            {isSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                            Save Changes
                        </button>
                    </div>
                </form>
            </div>
        </div>
    )
}

function UsersTab() {
    const { user: currentUser } = useAuth()
    const [users, setUsers] = useState<TeamUser[]>([])
    const [search, setSearch] = useState('')
    const [isLoading, setIsLoading] = useState(true)
    const [pageError, setPageError] = useState<string | null>(null)
    const [modalError, setModalError] = useState<string | null>(null)
    const [addOpen, setAddOpen] = useState(false)
    const [editUser, setEditUser] = useState<TeamUser | null>(null)
    const [isSaving, setIsSaving] = useState(false)
    const [deactivatingId, setDeactivatingId] = useState<string | null>(null)

    const fetchUsers = useCallback(async () => {
        setIsLoading(true)
        try {
            const response = await usersAPI.list()
            setUsers(response.data?.items || response.data || [])
            setPageError(null)
        } catch (err) {
            setPageError(parseApiError(err, 'Failed to load users'))
        } finally {
            setIsLoading(false)
        }
    }, [])

    useEffect(() => {
        fetchUsers()
    }, [fetchUsers])

    const filteredUsers = useMemo(() => {
        const query = search.trim().toLowerCase()
        if (!query) return users
        return users.filter((item) =>
            item.email.toLowerCase().includes(query) ||
            item.first_name.toLowerCase().includes(query) ||
            item.last_name.toLowerCase().includes(query),
        )
    }, [search, users])

    const handleCreate = async (event: FormEvent) => {
        event.preventDefault()
        const form = new FormData(event.currentTarget as HTMLFormElement)
        setIsSaving(true)
        setModalError(null)
        try {
            await usersAPI.create({
                first_name: String(form.get('first_name') || '').trim(),
                last_name: String(form.get('last_name') || '').trim(),
                email: String(form.get('email') || '').trim(),
                role: String(form.get('role') || 'coordinator'),
            })
            setAddOpen(false)
            await fetchUsers()
        } catch (err) {
            setModalError(parseApiError(err, 'Failed to create user'))
        } finally {
            setIsSaving(false)
        }
    }

    const handleUpdate = async (event: FormEvent) => {
        event.preventDefault()
        if (!editUser) return
        const form = new FormData(event.currentTarget as HTMLFormElement)
        setIsSaving(true)
        setModalError(null)
        try {
            await usersAPI.update(editUser.id, {
                first_name: String(form.get('first_name') || '').trim(),
                last_name: String(form.get('last_name') || '').trim(),
                role: String(form.get('role') || editUser.role),
                status: String(form.get('status') || editUser.status),
            })
            setEditUser(null)
            await fetchUsers()
        } catch (err) {
            setModalError(parseApiError(err, 'Failed to update user'))
        } finally {
            setIsSaving(false)
        }
    }

    const handleDeactivate = async (userId: string) => {
        setDeactivatingId(userId)
        setPageError(null)
        try {
            await usersAPI.delete(userId)
            await fetchUsers()
        } catch (err) {
            setPageError(parseApiError(err, 'Failed to deactivate user'))
        } finally {
            setDeactivatingId(null)
        }
    }

    return (
        <>
            <div className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-4 border-b border-gray-100 px-6 py-4">
                    <div>
                        <h2 className="text-lg font-semibold text-gray-900">Users</h2>
                        <p className="text-sm text-gray-500">
                            Invite, edit, deactivate, and assign roles to team members.
                        </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <div className="min-w-[240px]">
                            <input
                                value={search}
                                onChange={(event) => setSearch(event.target.value)}
                                placeholder="Search users"
                                className="w-full rounded-xl border border-gray-300 px-4 py-2.5 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                            />
                        </div>
                        <button
                            onClick={() => {
                                setModalError(null)
                                setAddOpen(true)
                            }}
                            className="inline-flex items-center gap-2 rounded-xl bg-sleep-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-sleep-700"
                        >
                            <UserPlus size={16} />
                            Add User
                        </button>
                    </div>
                </div>

                {pageError ? (
                    <div className="mx-6 mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                        {pageError}
                    </div>
                ) : null}

                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-gray-100 bg-gray-50/70">
                                <th className="px-6 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">User</th>
                                <th className="px-4 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Role</th>
                                <th className="px-4 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Status</th>
                                <th className="px-4 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Last Login</th>
                                <th className="px-6 py-3.5 text-right text-[11px] font-semibold uppercase tracking-wider text-gray-500">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading ? (
                                <tr><td colSpan={5} className="px-6 py-16 text-center text-sm text-gray-400">Loading users...</td></tr>
                            ) : filteredUsers.length === 0 ? (
                                <tr><td colSpan={5} className="px-6 py-16 text-center text-sm text-gray-400">No users found.</td></tr>
                            ) : (
                                filteredUsers.map((teamUser) => (
                                    <tr key={teamUser.id} className="border-t border-gray-50 hover:bg-sleep-50/20">
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-3">
                                                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-sleep-100 text-sm font-bold text-sleep-700">
                                                    {teamUser.first_name.charAt(0)}
                                                    {teamUser.last_name.charAt(0)}
                                                </div>
                                                <div>
                                                    <p className="text-sm font-semibold text-gray-900">
                                                        {teamUser.first_name} {teamUser.last_name}
                                                        {currentUser?.id === teamUser.id ? (
                                                            <span className="ml-1.5 text-xs font-normal text-sleep-600">(you)</span>
                                                        ) : null}
                                                    </p>
                                                    <p className="text-xs text-gray-500">{teamUser.email}</p>
                                                </div>
                                            </div>
                                        </td>
                                        <td className="px-4 py-4">
                                            <span className={`inline-flex rounded-md px-2.5 py-1 text-xs font-semibold capitalize ${roleBadge(teamUser.role)}`}>
                                                {teamUser.role.replace('_', ' ')}
                                            </span>
                                        </td>
                                        <td className="px-4 py-4">
                                            <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${statusBadge(teamUser.status)}`}>
                                                {teamUser.status}
                                            </span>
                                        </td>
                                        <td className="px-4 py-4 text-sm text-gray-500">
                                            {teamUser.last_login ? new Date(teamUser.last_login).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'Never'}
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="flex items-center justify-end gap-1">
                                                <button
                                                    onClick={() => {
                                                        setModalError(null)
                                                        setEditUser(teamUser)
                                                    }}
                                                    className="rounded-lg p-2 text-gray-400 transition-colors hover:bg-sleep-50 hover:text-sleep-700"
                                                    title="Edit user"
                                                >
                                                    <Edit3 size={15} />
                                                </button>
                                                {currentUser?.id !== teamUser.id ? (
                                                    <button
                                                        onClick={() => handleDeactivate(teamUser.id)}
                                                        disabled={deactivatingId === teamUser.id}
                                                        className="rounded-lg p-2 text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                                                        title="Deactivate user"
                                                    >
                                                        {deactivatingId === teamUser.id ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
                                                    </button>
                                                ) : null}
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            <UserModal
                isOpen={addOpen}
                title="Add User"
                user={{ first_name: '', last_name: '', email: '', role: 'coordinator', status: 'pending' }}
                error={modalError}
                isSaving={isSaving}
                onClose={() => setAddOpen(false)}
                onSubmit={handleCreate}
            />
            <UserModal
                isOpen={Boolean(editUser)}
                title="Edit User"
                user={{
                    first_name: editUser?.first_name || '',
                    last_name: editUser?.last_name || '',
                    email: editUser?.email || '',
                    role: editUser?.role || 'coordinator',
                    status: editUser?.status || 'active',
                }}
                error={modalError}
                isSaving={isSaving}
                onClose={() => setEditUser(null)}
                onSubmit={handleUpdate}
            />
        </>
    )
}

function RolesTab() {
    return (
        <div className="space-y-6">
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
                {ROLE_MATRIX.map((role) => (
                    <div key={role.role} className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
                        <span className={`inline-flex rounded-md px-2.5 py-1 text-xs font-semibold ${roleBadge(role.role)}`}>
                            {role.label}
                        </span>
                        <p className="mt-4 text-sm font-semibold text-gray-900">{role.label}</p>
                        <p className="mt-1 text-sm text-gray-500">{role.description}</p>
                        <p className="mt-4 text-xs font-medium uppercase tracking-wide text-gray-400">
                            {role.perms.length} permissions
                        </p>
                    </div>
                ))}
            </div>

            <div className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
                <div className="border-b border-gray-100 px-6 py-4">
                    <h2 className="text-lg font-semibold text-gray-900">Roles & Permissions</h2>
                    <p className="text-sm text-gray-500">Role definitions aligned with NeuroReach&apos;s RBAC model.</p>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-gray-100 bg-gray-50/70">
                                <th className="px-6 py-3.5 text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">Permission</th>
                                {ROLE_MATRIX.map((role) => (
                                    <th key={role.role} className="px-4 py-3.5 text-center text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                                        {role.label}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {ALL_PERMISSIONS.map((permission) => (
                                <tr key={permission} className="border-t border-gray-50">
                                    <td className="px-6 py-3 text-sm font-medium text-gray-700">{permission}</td>
                                    {ROLE_MATRIX.map((role) => (
                                        <td key={role.role} className="px-4 py-3 text-center">
                                            {role.perms.includes(permission) ? (
                                                <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-100 text-emerald-600">
                                                    <Check size={15} />
                                                </span>
                                            ) : (
                                                <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-gray-100 text-gray-300">
                                                    <X size={15} />
                                                </span>
                                            )}
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    )
}

function SiteSettingsTab() {
    const { user } = useAuth()
    const [clinic, setClinic] = useState<ClinicSettings>({
        clinic_name: '',
        clinic_address: '',
        clinic_phone: '',
        clinic_email: '',
    })
    const [prefs, setPrefs] = useState<Preferences>({
        notify_new_lead: true,
        notify_hot_lead: true,
        notify_daily_summary: true,
    })
    const [clinicLoading, setClinicLoading] = useState(true)
    const [prefsLoading, setPrefsLoading] = useState(true)
    const [clinicSaving, setClinicSaving] = useState(false)
    const [prefsSaving, setPrefsSaving] = useState(false)
    const [clinicError, setClinicError] = useState<string | null>(null)
    const [prefsError, setPrefsError] = useState<string | null>(null)
    const [clinicSuccess, setClinicSuccess] = useState(false)

    useEffect(() => {
        usersAPI.getClinicSettings()
            .then((response) => setClinic(response.data))
            .catch((err) => setClinicError(parseApiError(err, 'Failed to load clinic settings')))
            .finally(() => setClinicLoading(false))

        usersAPI.getPreferences()
            .then((response) => setPrefs(response.data))
            .catch((err) => setPrefsError(parseApiError(err, 'Failed to load notification preferences')))
            .finally(() => setPrefsLoading(false))
    }, [])

    const handleClinicSave = async (event: FormEvent) => {
        event.preventDefault()
        setClinicSaving(true)
        setClinicError(null)
        setClinicSuccess(false)
        try {
            const response = await usersAPI.updateClinicSettings(clinic)
            setClinic(response.data)
            setClinicSuccess(true)
            window.setTimeout(() => setClinicSuccess(false), 3000)
        } catch (err) {
            setClinicError(parseApiError(err, 'Failed to save clinic settings'))
        } finally {
            setClinicSaving(false)
        }
    }

    const handleToggle = async (key: keyof Preferences) => {
        setPrefsSaving(true)
        setPrefsError(null)
        const next = { ...prefs, [key]: !prefs[key] }
        try {
            const response = await usersAPI.updatePreferences({ [key]: next[key] })
            setPrefs(response.data)
        } catch (err) {
            setPrefsError(parseApiError(err, 'Failed to save notification preferences'))
        } finally {
            setPrefsSaving(false)
        }
    }

    return (
        <div className="space-y-6">
            <div className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
                <div className="border-b border-gray-100 px-6 py-5">
                    <h2 className="text-lg font-semibold text-gray-900">Clinic Information</h2>
                    <p className="text-sm text-gray-500">Details shown in patient communications and reports.</p>
                </div>

                {clinicLoading ? (
                    <div className="flex items-center justify-center py-12 text-sm text-gray-400">
                        <Loader2 size={18} className="mr-2 animate-spin" />
                        Loading clinic settings...
                    </div>
                ) : (
                    <form onSubmit={handleClinicSave} className="space-y-5 px-6 py-6">
                        {clinicError ? (
                            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                                {clinicError}
                            </div>
                        ) : null}
                        {clinicSuccess ? (
                            <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                                <CheckCircle2 size={16} />
                                Clinic settings saved successfully.
                            </div>
                        ) : null}

                        <div>
                            <label className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500">
                                <Building2 size={12} />
                                Clinic Name
                            </label>
                            <input
                                value={clinic.clinic_name}
                                onChange={(event) => setClinic((prev) => ({ ...prev, clinic_name: event.target.value }))}
                                className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                            />
                        </div>

                        <div>
                            <label className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500">
                                <MapPin size={12} />
                                Address
                            </label>
                            <input
                                value={clinic.clinic_address}
                                onChange={(event) => setClinic((prev) => ({ ...prev, clinic_address: event.target.value }))}
                                className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                            />
                        </div>

                        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                            <div>
                                <label className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500">
                                    <Phone size={12} />
                                    Phone
                                </label>
                                <input
                                    value={clinic.clinic_phone}
                                    onChange={(event) => setClinic((prev) => ({ ...prev, clinic_phone: event.target.value }))}
                                    className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                                />
                            </div>
                            <div>
                                <label className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500">
                                    <Mail size={12} />
                                    Email
                                </label>
                                <input
                                    type="email"
                                    value={clinic.clinic_email}
                                    onChange={(event) => setClinic((prev) => ({ ...prev, clinic_email: event.target.value }))}
                                    className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-sleep-500 focus:outline-none focus:ring-2 focus:ring-sleep-500/20"
                                />
                            </div>
                        </div>

                        <div className="pt-1">
                            <button
                                type="submit"
                                disabled={clinicSaving}
                                className="inline-flex items-center gap-2 rounded-xl bg-sleep-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-sleep-700 disabled:opacity-60"
                            >
                                {clinicSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                                Save Clinic Info
                            </button>
                        </div>
                    </form>
                )}
            </div>

            <div className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
                <div className="border-b border-gray-100 px-6 py-5">
                    <div className="flex items-center gap-2">
                        <h2 className="text-lg font-semibold text-gray-900">Notification Preferences</h2>
                        <span className="rounded-full border border-amber-200 bg-amber-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-700">
                            Coming Soon
                        </span>
                    </div>
                    <p className="text-sm text-gray-500">
                        Toggle preferences are saved, but outbound delivery is still being finalized.
                    </p>
                </div>

                {prefsLoading ? (
                    <div className="flex items-center justify-center py-12 text-sm text-gray-400">
                        <Loader2 size={18} className="mr-2 animate-spin" />
                        Loading notification preferences...
                    </div>
                ) : (
                    <div className="space-y-4 px-6 py-6">
                        {prefsError ? (
                            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                                {prefsError}
                            </div>
                        ) : null}

                        {[
                            { key: 'notify_new_lead' as const, label: 'New Lead Notification', description: 'Notify me when a new lead is submitted.' },
                            { key: 'notify_hot_lead' as const, label: 'Hot Lead Alert', description: 'Notify me when a lead is scored as high priority.' },
                            { key: 'notify_daily_summary' as const, label: 'Daily Summary Email', description: 'Send a daily digest of lead activity and conversions.' },
                        ].map((item) => (
                            <div key={item.key} className="flex items-center justify-between gap-4 rounded-2xl border border-gray-100 bg-gray-50/60 px-4 py-4">
                                <div className="flex items-start gap-3">
                                    <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-xl bg-white shadow-sm">
                                        <Bell size={18} className="text-sleep-600" />
                                    </div>
                                    <div>
                                        <p className="text-sm font-semibold text-gray-900">{item.label}</p>
                                        <p className="text-sm text-gray-500">{item.description}</p>
                                    </div>
                                </div>
                                <button
                                    type="button"
                                    onClick={() => handleToggle(item.key)}
                                    disabled={prefsSaving}
                                    className={`relative h-6 w-11 rounded-full transition-colors ${
                                        prefs[item.key] ? 'bg-sleep-600' : 'bg-gray-300'
                                    } disabled:opacity-50`}
                                >
                                    <span
                                        className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
                                            prefs[item.key] ? 'translate-x-5' : 'translate-x-0'
                                        }`}
                                    />
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <div className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
                <div className="border-b border-gray-100 px-6 py-5">
                    <h2 className="text-lg font-semibold text-gray-900">Security</h2>
                    <p className="text-sm text-gray-500">Current account and access details.</p>
                </div>
                <div className="space-y-4 px-6 py-6">
                    <div className="flex items-center gap-4 rounded-2xl border border-gray-100 bg-gray-50/60 p-4">
                        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-sleep-100">
                            <Shield size={22} className="text-sleep-700" />
                        </div>
                        <div className="flex-1">
                            <p className="text-sm font-semibold text-gray-900">Logged In As</p>
                            <p className="text-sm text-gray-500">{user?.email || '—'}</p>
                        </div>
                        <span className={`inline-flex rounded-md px-2.5 py-1 text-xs font-semibold ${roleBadge(user?.role || '')}`}>
                            {(user?.role || 'specialist').replace('_', ' ')}
                        </span>
                    </div>

                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                        <div className="rounded-2xl border border-gray-100 bg-gray-50/60 p-4">
                            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Last Login</p>
                            <p className="mt-2 text-sm text-gray-700">
                                {user?.last_login ? new Date(user.last_login).toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'N/A'}
                            </p>
                        </div>
                        <div className="rounded-2xl border border-gray-100 bg-gray-50/60 p-4">
                            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Account Created</p>
                            <p className="mt-2 text-sm text-gray-700">
                                {user?.created_at ? new Date(user.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A'}
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default function SettingsPage() {
    const [activeTab, setActiveTab] = useState<'users' | 'roles' | 'site'>('users')

    const tabs = [
        { id: 'users' as const, label: 'Users', icon: <Users size={18} /> },
        { id: 'roles' as const, label: 'Roles & Permissions', icon: <Shield size={18} /> },
        { id: 'site' as const, label: 'Site Settings', icon: <Settings size={18} /> },
    ]

    return (
        <div className="space-y-6 animate-fade-in">
            <div className="flex items-center gap-4">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-gray-700 to-gray-900 shadow-xl shadow-gray-900/15">
                    <Settings size={26} className="text-white" />
                </div>
                <div>
                    <h1 className="text-3xl font-bold tracking-tight text-gray-900">Settings</h1>
                    <p className="text-[15px] text-gray-500">Manage users, roles, and clinic configuration.</p>
                </div>
            </div>

            <div className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
                <div className="flex flex-wrap gap-2 border-b border-gray-100 px-4 py-3">
                    {tabs.map((tab) => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={`inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors ${
                                activeTab === tab.id
                                    ? 'bg-sleep-50 text-sleep-700 ring-1 ring-sleep-200'
                                    : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
                            }`}
                        >
                            {tab.icon}
                            {tab.label}
                        </button>
                    ))}
                </div>
            </div>

            {activeTab === 'users' && <UsersTab />}
            {activeTab === 'roles' && <RolesTab />}
            {activeTab === 'site' && <SiteSettingsTab />}
        </div>
    )
}
