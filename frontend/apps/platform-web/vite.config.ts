import { defineConfig } from 'vite';
export default defineConfig({
  server: {
    fs: { allow: ['../..'] },
    proxy: { '/api': 'http://127.0.0.1:4300', '/ready': 'http://127.0.0.1:4300' },
  },
  build: { outDir: 'dist', emptyOutDir: true },
});
