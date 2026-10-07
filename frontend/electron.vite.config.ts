import { defineConfig } from "electron-vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  main: { build: { outDir: "dist-electron" } },
  preload: { build: { outDir: "dist-electron" } },
  renderer: {
    plugins: [react()],
    build: { outDir: "dist" },
  },
});
