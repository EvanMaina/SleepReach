import { Outlet } from 'react-router-dom'
import Sidebar from '../components/Sidebar'

export default function DashboardLayout() {
    return (
        <div className="h-screen overflow-hidden bg-gray-50/80">
            <Sidebar />
            {/*
              Mobile (<md):  sidebar hidden via overlay, main takes full width
              Tablet (md):   sidebar collapsed 72px, main pl-[72px]
              Desktop (xl):  sidebar expanded 260px, main pl-[260px]
            */}
            <main className="h-screen overflow-hidden pl-0 md:pl-[72px] xl:pl-[260px] transition-all duration-200">
                <div className="h-full overflow-y-auto px-2 py-4 sm:px-3 sm:py-5 lg:px-5 lg:py-6 xl:px-6 xl:py-8">
                    <Outlet />
                </div>
            </main>
        </div>
    )
}
