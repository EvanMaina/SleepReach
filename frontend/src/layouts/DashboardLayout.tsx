import { Outlet } from 'react-router-dom'
import Sidebar from '../components/Sidebar'

export default function DashboardLayout() {
    return (
        <div className="min-h-screen bg-gray-50/80">
            <Sidebar />
            <main className="pl-[260px] min-h-screen">
                <div className="p-8">
                    <Outlet />
                </div>
            </main>
        </div>
    )
}
