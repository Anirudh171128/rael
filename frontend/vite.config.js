import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy API + WebSocket to the FastAPI backend so the frontend uses same-origin
// relative URLs (no CORS juggling in dev).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 127.0.0.1 (not "localhost") so Node uses IPv4 and matches uvicorn's
      // default 127.0.0.1 bind — avoids IPv6 ::1 proxy ECONNRESET errors.
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
});
