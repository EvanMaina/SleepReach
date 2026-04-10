/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                // SleepReach brand palette — derived from sleeplessinarizona.com
                // Primary: Steel blue / navy from the clinic header & navigation
                sleep: {
                    50: '#f0f5fa',
                    100: '#dce6f2',
                    200: '#bccfe6',
                    300: '#8eb1d4',
                    400: '#6593be',
                    500: '#4A6FA5',  // Primary brand blue
                    600: '#3d5c8a',
                    700: '#344d72',
                    800: '#2e415f',
                    900: '#293850',
                    950: '#1a2435',
                },
                // Warm gold/amber accent from clinic website
                warm: {
                    50: '#fef9ee',
                    100: '#fdf0d2',
                    200: '#fae0a4',
                    300: '#f6cb6c',
                    400: '#f2b034',
                    500: '#EE9A1D',  // Warm gold accent
                    600: '#d47d13',
                    700: '#b05e13',
                    800: '#8f4a16',
                    900: '#763e16',
                    950: '#401f09',
                },
                // Teal accent (from clinic imagery)
                teal: {
                    50: '#effcfc',
                    100: '#d6f6f7',
                    200: '#b2ecef',
                    300: '#7ddde3',
                    400: '#41c5cf',
                    500: '#26a9b5',
                    600: '#228899',
                    700: '#226e7c',
                    800: '#245a66',
                    900: '#224b57',
                    950: '#11303b',
                },
            },
            fontFamily: {
                sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
                display: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
            },
            boxShadow: {
                'premium': '0 1px 3px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.06)',
                'premium-lg': '0 4px 6px rgba(0,0,0,0.04), 0 10px 24px rgba(0,0,0,0.08)',
                'premium-xl': '0 8px 16px rgba(0,0,0,0.06), 0 20px 40px rgba(0,0,0,0.1)',
                'glow-blue': '0 0 20px rgba(74, 111, 165, 0.15)',
                'glow-warm': '0 0 20px rgba(238, 154, 29, 0.15)',
            },
            borderRadius: {
                'xl': '0.875rem',
                '2xl': '1rem',
                '3xl': '1.25rem',
            },
            backgroundImage: {
                'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
            },
            animation: {
                'fade-in': 'fadeIn 0.5s ease-out',
                'slide-up': 'slideUp 0.5s ease-out',
                'slide-in-right': 'slideInRight 0.3s ease-out',
                'count-up': 'countUp 1s ease-out',
            },
            keyframes: {
                fadeIn: {
                    '0%': { opacity: '0' },
                    '100%': { opacity: '1' },
                },
                slideUp: {
                    '0%': { opacity: '0', transform: 'translateY(10px)' },
                    '100%': { opacity: '1', transform: 'translateY(0)' },
                },
                slideInRight: {
                    '0%': { opacity: '0', transform: 'translateX(-10px)' },
                    '100%': { opacity: '1', transform: 'translateX(0)' },
                },
            },
        },
    },
    plugins: [],
}
