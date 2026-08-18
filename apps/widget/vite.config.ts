import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

const root = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  build: {
    lib: {
      entry: resolve(root, 'src/main.ts'),
      name: 'GeemWidget',
      formats: ['iife'],
      fileName: () => 'geem-widget.js',
    },
    outDir: resolve(root, 'dist'),
    emptyOutDir: true,
    minify: true,
    sourcemap: false,
  },
});
