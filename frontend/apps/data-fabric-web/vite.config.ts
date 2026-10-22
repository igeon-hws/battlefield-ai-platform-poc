import { defineConfig } from 'vite';
export default defineConfig({
  server: { fs: { allow: ['../..'] }, proxy: { '/v1': 'http://127.0.0.1:4400' } },
  build: { outDir: 'dist', emptyOutDir: true },
});
