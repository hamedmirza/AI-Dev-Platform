import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/ui/assets/",
  build: {
    outDir: "../app/ui/static",
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: "index.html"
    }
  }
});
