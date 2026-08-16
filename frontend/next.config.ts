import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // @ts-ignore - To fix the Next.js dev resource cross-origin blocking
  allowedDevOrigins: ['172.26.112.1'],
  /* config options here */
};

export default nextConfig;
