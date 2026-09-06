import { fileURLToPath, URL } from "node:url";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const webRoot = fileURLToPath(new URL("./web", import.meta.url));

export default defineConfig({
  root: webRoot,
  plugins: [
    tanstackRouter({
      target: "react",
      autoCodeSplitting: true,
      routesDirectory: fileURLToPath(
        new URL("./web/src/app/routes", import.meta.url),
      ),
      generatedRouteTree: fileURLToPath(
        new URL("./web/src/app/routeTree.gen.ts", import.meta.url),
      ),
    }),
    react(),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./web/src", import.meta.url)),
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
