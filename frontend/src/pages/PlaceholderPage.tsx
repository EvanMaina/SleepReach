import { Moon } from 'lucide-react'

interface PlaceholderPageProps {
    title: string
    description: string
}

export default function PlaceholderPage({ title, description }: PlaceholderPageProps) {
    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
                <p className="text-gray-500 mt-1">{description}</p>
            </div>

            <div className="card-premium p-12 flex flex-col items-center justify-center text-center">
                <div className="w-16 h-16 rounded-2xl bg-sleep-50 border border-sleep-100 flex items-center justify-center mb-4">
                    <Moon className="w-8 h-8 text-sleep-400" />
                </div>
                <h2 className="text-lg font-semibold text-gray-900 mb-2">
                    {title}
                </h2>
                <p className="text-sm text-gray-500 max-w-md">
                    This page is being built. The backend API is connected and ready.
                    Full functionality coming soon.
                </p>
            </div>
        </div>
    )
}
