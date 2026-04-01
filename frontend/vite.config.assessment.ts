import { defineConfig, Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import autoprefixer from 'autoprefixer'
import tailwindcss from 'tailwindcss'

function cssInjectedByJsPlugin(): Plugin {
    return {
        name: 'css-injected-by-js',
        apply: 'build',
        enforce: 'post',
        generateBundle(_options, bundle) {
            let cssCode = ''
            const cssAssetKeys: string[] = []

            for (const [key, chunk] of Object.entries(bundle)) {
                if (key.endsWith('.css') && chunk.type === 'asset') {
                    cssCode += String(chunk.source)
                    cssAssetKeys.push(key)
                }
            }

            for (const key of cssAssetKeys) {
                delete bundle[key]
            }

            if (!cssCode) return

            for (const chunk of Object.values(bundle)) {
                if (chunk.type === 'chunk' && chunk.isEntry) {
                    const cssInjection =
                        `(function(){try{var s=document.createElement('style');s.setAttribute('data-sr-assessment','');s.textContent=${JSON.stringify(cssCode)};document.head.appendChild(s);}catch(e){console.error('SleepReach assessment: Failed to inject styles',e);}})();\n`
                    chunk.code = cssInjection + chunk.code
                }
            }
        },
    }
}

export default defineConfig({
    plugins: [react(), cssInjectedByJsPlugin()],
    css: {
        postcss: {
            plugins: [
                tailwindcss({
                    config: path.resolve(__dirname, './tailwind.config.widget.js'),
                }),
                autoprefixer(),
            ],
        },
    },
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
    define: {
        'process.env.NODE_ENV': JSON.stringify('production'),
        'process.env': JSON.stringify({}),
        'import.meta.env.VITE_API_URL': JSON.stringify(''),
    },
    build: {
        outDir: 'dist-assessment',
        emptyOutDir: true,
        sourcemap: false,
        target: 'es2015',
        lib: {
            entry: path.resolve(__dirname, 'src/assessment-entry.tsx'),
            name: 'SleepReachAssessment',
            formats: ['iife'],
            fileName: () => 'assessment.js',
        },
        rollupOptions: {
            output: {
                format: 'iife',
                inlineDynamicImports: true,
                entryFileNames: 'assessment.js',
                manualChunks: undefined,
            },
        },
        cssCodeSplit: false,
        minify: 'esbuild',
        chunkSizeWarningLimit: 1000,
        reportCompressedSize: true,
    },
})
