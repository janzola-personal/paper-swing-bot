import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // Python serverless lives beside the Next app at repo root (api/*.py).
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      "@": path.resolve(__dirname),
    };
    return config;
  },
};

export default nextConfig;
