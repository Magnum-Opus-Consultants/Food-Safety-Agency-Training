import type { NextConfig } from "next";

// The browser reaches Django through this same origin (/api/* -> Django), so the session
// cookie is first-party and no CORS is needed. In production a reverse proxy does the same.
const API_ORIGIN = process.env.FSA_API_ORIGIN ?? "http://127.0.0.1:8210";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "same-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
