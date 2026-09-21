import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The front end is self-contained: it talks to the governed API over HTTP only, so this
// folder can be lifted into its own repository without touching the Python service.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
