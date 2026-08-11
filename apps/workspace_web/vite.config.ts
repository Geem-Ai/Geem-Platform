import { fileURLToPath, URL } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: true,
    port: 5174,
    // Local geem.dm / *.geem.dm Host headers (dnsmasq / /etc/hosts)
    allowedHosts: ['.geem.dm', 'localhost'],
  },
  build: {
    chunkSizeWarningLimit: 2000,
  },
});
