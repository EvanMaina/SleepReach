import { Outlet } from 'react-router-dom'
import Sidebar from '../components/Sidebar'

export default function DashboardLayout() {
    return (
        <div className="h-screen overflow-hidden bg-gray-50/80">
            <Sidebar />
            <main className="h-screen overflow-hidden pl-[260px]">
                <div className="h-full overflow-y-auto p-8">
                    <Outlet />
                </div>
            </main>
        </div>
    )
}
