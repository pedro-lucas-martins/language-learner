import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Listen on the LAN too, so the app can be opened from a phone during development.
    host: true,
    port: 5173,
  },
});
