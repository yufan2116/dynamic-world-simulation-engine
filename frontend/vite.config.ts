import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backend = env.VITE_API_URL || "http://127.0.0.1:8002";

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": { target: backend, changeOrigin: true },
        "/game": { target: backend, changeOrigin: true },
        "/health": { target: backend, changeOrigin: true },
        "/static": { target: backend, changeOrigin: true },
        "/ws": { target: backend, ws: true, changeOrigin: true },
      },
    },
  };
});
