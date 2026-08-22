import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  site: "https://badgerpolitics.org",
  output: "static",
  redirects: {
    // hearings folded into the calendar page; old links keep working
    "/hearings": "/calendar/#hearings",
  },
  vite: {
    plugins: [tailwindcss()],
  },
});
