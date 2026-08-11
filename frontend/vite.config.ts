import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxy = {
  "/api": {
    target: process.env.SHOPMIND_BACKEND_URL ?? "http://127.0.0.1:8000",
    changeOrigin: false,
  },
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    proxy: apiProxy,
  },
  preview: {
    port: 5173,
    strictPort: false,
    proxy: apiProxy,
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
    globals: true,
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
  },
});
