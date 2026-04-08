import { Outlet } from 'react-router-dom'
import Sidebar from '../components/Sidebar'

export default function DashboardLayout() {
    return (
        <div className="h-screen overflow-hidden bg-gray-50/80">
            <Sidebar />
            {/* Sidebar: 72px collapsed (below xl), 260px expanded (xl+) */}
            <main className="h-screen overflow-hidden pl-[72px] xl:pl-[260px] transition-all duration-200">
                <div className="h-full overflow-y-auto px-3 py-5 lg:px-5 lg:py-6 xl:px-6 xl:py-8">
                    <Outlet />
                </div>
            </main>
        </div>
    )
}
