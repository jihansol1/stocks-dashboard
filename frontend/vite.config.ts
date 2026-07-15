import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    // Backend runs on :8000; proxying avoids CORS entirely in dev.
    proxy: {
      "/stocks": "http://127.0.0.1:8000",
      "/search": "http://127.0.0.1:8000",
      "/symbols": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
})
