/** @type {import('tailwindcss').Config} */
export default {
    important: '#sleepreach-widget-root',
    content: [
        './src/widget-entry.tsx',
        './src/pages/WidgetPage.tsx',
        './src/widget-embed.css',
    ],
    theme: {
        extend: {},
    },
    corePlugins: {
        preflight: false,
    },
    plugins: [],
}
