import basicSsl from "@vitejs/plugin-basic-ssl";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

/**
 * `npm run dev:lan` (mode "lan"): HTTPS with a self-signed certificate, so a phone on the
 * same Wi-Fi can use the microphone (browsers require a secure context). The backend is
 * reached through this server's proxy, so the page and the API share one HTTPS origin.
 */
export default defineConfig(({ mode }) => {
  const lan = mode === "lan";
  // VITE_PROXY_TARGET (env var or env file) points the proxy elsewhere, e.g. inside Docker.
  const backend = loadEnv(mode, ".", "VITE_").VITE_PROXY_TARGET || "http://localhost:8000";
  return {
    plugins: [react(), tailwindcss(), ...(lan ? [basicSsl()] : [])],
    server: {
      // Listen on the LAN too, so the app can be opened from a phone during development.
      host: true,
      port: 5173,
      proxy: lan
        ? {
            "/ws": { target: backend.replace(/^http/, "ws"), ws: true },
            "/me": { target: backend },
            "/flashcards": { target: backend },
            "/health": { target: backend },
          }
        : undefined,
    },
  };
});
