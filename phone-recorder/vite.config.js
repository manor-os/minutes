import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      injectRegister: false,
      registerType: 'autoUpdate',
      workbox: {
        skipWaiting: true,
        clientsClaim: true,
        cleanupOutdatedCaches: true,
        navigateFallbackDenylist: [/^\/api\//, /^\/ws/]
      },
      includeAssets: ['minutes-product-mark.svg', 'minutes-app-icon.svg', 'minutes-app-touch-180.png'],
      manifest: {
        name: 'Minutes — AI Meeting Notes',
        short_name: 'Minutes',
        description: 'AI-powered meeting recorder — transcribe, summarize, extract action items',
        theme_color: '#18181b',
        icons: [
          {
            src: 'minutes-app-icon-192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'any'
          },
          {
            src: 'minutes-app-icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any'
          }
        ]
      }
    })
  ],
  server: {
    port: 3001,
    host: true,
    allowedHosts: true,
    hmr: {
      overlay: false  // Disable error overlay to prevent URI malformed errors from blocking the UI
    },
    middlewareMode: false,
    // Add middleware to handle malformed URIs gracefully
    fs: {
      strict: false  // Allow serving files outside of root to handle edge cases
    }
  }
});
