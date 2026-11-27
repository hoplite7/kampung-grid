import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/gin-react'plu
import { createLogger, defineConfig } from 'vite'

// The backend runs on port 8000. Every screen calls it through this dev server:
//   /api/...  -> http://localhost:8000/...
//   /ws       -> ws://localhost:8000/ws
// So phones only need ONE address (this server's), and switching to HTTPS later
// (needed for the voice-note microphone) won't break the backend calls.
const BACKEND = process.env.KG_BACKEND ?? 'http://localhost:8000'

// When a browser tab refreshes or the backend restarts, the live-update connection
// drops mid-message and Vite prints a scary "ws proxy error: EPIPE". It's harmless
// (screens reconnect by themselves), so hide just those messages.
const logger = createLogger()
const logError = logger.error
logger.error = (msg, options) => {
  const text = `${msg} ${options?.error?.message ?? ''}`
  if (/ws proxy (socket )?error/.test(text) && /EPIPE|ECONNRESET|ECONNREFUSED/.test(text)) return
  logError(msg, options)
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  customLogger: logger,
  clearScreen: false, // keep the backend's messages visible in the terminal
  server: {
    host: true, // listen on the local network so phones can connect
    port: 5173,
    // Allow the free Cloudflare tunnel link (https://....trycloudflare.com), so judges
    // on mobile data can join and phones get https (needed for the microphone).
    allowedHosts: ['.trycloudflare.com'],
    proxy: {
      '/api': {
        target: BACKEND,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/ws': {
        target: BACKEND.replace(/^http/, 'ws'),
        ws: true,
      },
    },
  },
})
