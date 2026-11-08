import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import tailwindcss from "@tailwindcss/vite";
import tsConfigPaths from "vite-tsconfig-paths";

// https://vitejs.dev/config/
// tanstackStart() already includes the TanStack router plugin (route tree + code
// splitting). Adding tanstackRouter() as well ran it twice and broke `npm run dev`
// with "TSRSplitComponent is not defined".
export default defineConfig({
  plugins: [
    tanstackStart({
      server: { entry: "server" },
    }),
    tailwindcss(),
    react(),
    tsConfigPaths({ projects: ["./tsconfig.json"] }),
  ],
});
