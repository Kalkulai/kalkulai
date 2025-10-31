import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
    proxy: mode === "development"
      ? {
          "/api": {
            target: process.env.VITE_DEV_BACKEND_ORIGIN ?? "http://localhost:8000",
            changeOrigin: true,
          },
          "/wizard": {
            target: process.env.VITE_DEV_BACKEND_ORIGIN ?? "http://localhost:8000",
            changeOrigin: true,
          },
          "/revenue-guard": {
            target: process.env.VITE_DEV_BACKEND_ORIGIN ?? "http://localhost:8000",
            changeOrigin: true,
          },
          "/outputs": {
            target: process.env.VITE_DEV_BACKEND_ORIGIN ?? "http://localhost:8000",
            changeOrigin: true,
          },
        }
      : undefined,
  },
  plugins: [react(), mode === "development" && componentTagger()].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setupTests.ts"],
    coverage: {
      reports: ["text", "lcov"],
    },
  },
}));
