import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Vite config. The dev server proxies /api to the backend so the dashboard can
// call the REST API without CORS headaches during local development. Supabase
// calls go directly to the Supabase URL from the browser.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || process.env.VITE_API_URL || 'http://localhost:3000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    css: false,
  },
});
