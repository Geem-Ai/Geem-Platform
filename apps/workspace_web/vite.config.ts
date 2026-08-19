import { fileURLToPath, URL } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const tunnelHost = process.env.VITE_TUNNEL_HOST?.trim();

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
    // Local geem.dm + Cloudflare Tunnel (hub.geem.ai)
    allowedHosts: ['.geem.dm', '.geem.ai', 'localhost'],
    ...(tunnelHost
      ? {
          hmr: {
            host: tunnelHost,
            protocol: 'wss',
            clientPort: 443,
          },
        }
      : {}),
  },
  build: {
    chunkSizeWarningLimit: 2000,
  },
});
