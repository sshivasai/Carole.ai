import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Production releases are embedded in the Python wheel and served by
  // FastAPI. No Node.js process is needed on the user's machine.
  output: "export",
  images: {
    unoptimized: true,
  },
  allowedDevOrigins: ["172.26.112.1"],
};

export default nextConfig;
