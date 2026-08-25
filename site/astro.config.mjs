import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  site: "https://badgerpolitics.org",
  output: "static",
  // Astro 7 defaults this to 'jsx', which drops the whitespace between a
  // text node and an inline element ("committee.<a>See every..."). Our
  // prose relies on HTML collapsing rules, so keep them.
  compressHTML: true,
  redirects: {
    // hearings folded into the calendar page; old links keep working
    "/hearings": "/calendar/#hearings",
  },
  vite: {
    plugins: [tailwindcss()],
  },
});
