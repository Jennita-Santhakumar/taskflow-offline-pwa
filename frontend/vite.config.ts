import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      workbox: {
        // App-shell caching only -- API calls are handled by the app's own IndexedDB-backed sync
        // engine, not the service worker cache, since sync/conflict-resolution logic needs to run
        // in JS anyway (matches the plan's "PWA + IndexedDB" offline-first design).
        globPatterns: ["**/*.{js,css,html,svg,png,ico}"],
        navigateFallback: "/index.html",
      },
      manifest: {
        name: "Offline Task Manager",
        short_name: "Tasks",
        start_url: "/",
        display: "standalone",
        background_color: "#0f172a",
        theme_color: "#0f172a",
        icons: [],
      },
    }),
  ],
  server: { port: 5233 },
  preview: { port: 5233 },
});
