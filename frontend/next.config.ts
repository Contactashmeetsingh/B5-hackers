import type { NextConfig } from "next";

// GITHUB_PAGES=true builds a static site (frontend/out) served from
// https://<owner>.github.io/B5-hackers/, so every URL needs the /B5-hackers prefix.
// Local `npm run dev` / `npm run build` are unchanged.
const pages = process.env.GITHUB_PAGES === "true";
const basePath = pages ? (process.env.PAGES_BASE_PATH ?? "/B5-hackers") : "";

const config: NextConfig = {
  devIndicators: false,
  agentRules: false,
  ...(pages && {
    output: "export",
    basePath,
    trailingSlash: true,
    images: { unoptimized: true },
  }),
  env: { NEXT_PUBLIC_BASE_PATH: basePath },
};

export default config;
