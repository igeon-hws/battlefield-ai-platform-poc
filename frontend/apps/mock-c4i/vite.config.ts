import { defineConfig } from 'vite';
export default defineConfig({
  server: {
    fs: { allow: ['../..'] },
    proxy: { '/api': 'http://127.0.0.1:4100', '/health': 'http://127.0.0.1:4100' },
  },
  build: { outDir: 'dist', emptyOutDir: true },
});
