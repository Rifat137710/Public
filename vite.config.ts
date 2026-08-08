import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * The site is served from a project page, so assets resolve under /Public/.
 * Set BASE_PATH in the workflow if the repository is ever renamed.
 */
export default defineConfig({
  base: process.env.BASE_PATH ?? '/Public/',
  plugins: [react()],
  build: { outDir: 'dist', sourcemap: false },
});
