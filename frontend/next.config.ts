import type { NextConfig } from "next";

// The browser talks only to this app's origin; /api/* is proxied to FastAPI. Keeping one origin lets the
// session cookie stay HttpOnly + SameSite=Strict and removes the need for CORS.
const API_URL = process.env.API_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
