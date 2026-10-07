import { defineConfig } from "electron-vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  main: {
    build: { outDir: "dist-electron" },
    // allow Node built-ins (http, path, child_process) in main process
  },
  preload: {
    build: { outDir: "dist-electron" },
  },
  renderer: {
    plugins: [react()],
    build: { outDir: "dist" },
    server: { port: 5173 },
  },
});
