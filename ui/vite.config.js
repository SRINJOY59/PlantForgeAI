import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    headers: {
      "Cache-Control": "no-store",
    },
  },
  optimizeDeps: {
    include: ["plotly.js-basic-dist-min"],
  },
});
