import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import tailwindcss from "@tailwindcss/vite";
import tsConfigPaths from "vite-tsconfig-paths";

// Hosted build (Render, see Dockerfile): CHECKOUTPILOT_STATIC=1 builds a static single-page
// app (dist/client + _shell.html) that the FastAPI backend serves from the same URL.
// Local `npm run dev` is unchanged.
const STATIC_BUILD = process.env.CHECKOUTPILOT_STATIC === "1";

// https://vitejs.dev/config/
// tanstackStart() already includes the TanStack router plugin (route tree + code
// splitting). Adding tanstackRouter() as well ran it twice and broke `npm run dev`
// with "TSRSplitComponent is not defined".
export default defineConfig({
  plugins: [
    tanstackStart({
      server: { entry: "server" },
      // Every page (/, /audit, /recommendations, /fix, /proof) is pre-drawn to its own HTML file.
      ...(STATIC_BUILD ? { spa: { enabled: true }, prerender: { enabled: true, crawlLinks: true } } : {}),
    }),
    tailwindcss(),
    react(),
    tsConfigPaths({ projects: ["./tsconfig.json"] }),
  ],
  // The static build pre-draws pages through a short-lived preview server. Pin it to 127.0.0.1:
  // inside Docker "localhost" can resolve to a different address than the one it listens on
  // (the build then fails with ECONNREFUSED 127.0.0.1).
  ...(STATIC_BUILD ? { preview: { host: "127.0.0.1" } } : {}),
});
