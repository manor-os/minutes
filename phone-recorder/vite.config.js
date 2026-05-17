import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'apple-touch-icon.png'],
      manifest: {
        name: 'Minutes — AI Meeting Notes',
        short_name: 'Minutes',
        description: 'AI-powered meeting recorder — transcribe, summarize, extract action items',
        theme_color: '#2196F3',
        icons: [
          {
            src: 'pwa-192x192.png',
            sizes: '192x192',
            type: 'image/png'
          },
          {
            src: 'pwa-512x512.png',
            sizes: '512x512',
            type: 'image/png'
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

