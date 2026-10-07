import { defineConfig } from "electron-vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  main: {
    build: {
      outDir: "dist-electron",
      emptyOutDir: false,
      lib: { entry: resolve(__dirname, "electron/main.ts"), formats: ["cjs"], fileName: () => "main.js" },
    },
  },
  preload: {
    build: {
      outDir: "dist-electron",
      emptyOutDir: false,
      lib: { entry: resolve(__dirname, "electron/preload.ts"), formats: ["cjs"], fileName: () => "preload.js" },
    },
  },
  renderer: {
    root: __dirname,
    plugins: [react()],
    server: { port: 5173 },
    build: {
      outDir: "dist",
      rollupOptions: { input: resolve(__dirname, "index.html") },
    },
  },
});
