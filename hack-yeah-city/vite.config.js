import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // pre-bundling psuje ścieżkę do workera maplibre-gl ("Worker failed to load")
  optimizeDeps: { exclude: ['maplibre-gl'] },
})
