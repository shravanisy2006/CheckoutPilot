import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import tailwindcss from "@tailwindcss/vite";
import tsConfigPaths from "vite-tsconfig-paths";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    tanstackRouter({
      targets: ["src/routes/*.tsx", "src/routes/**/*.tsx"],
      autoCodeSplitting: true,
      routeTreeGenOptions: {
        routeTree: "./src/routeTree.gen.ts",
      },
    }),
    tanstackStart({
      server: { entry: "server" },
    }),
    tailwindcss(),
    react(),
    tsConfigPaths({ projects: ["./tsconfig.json"] }),
  ],
});
