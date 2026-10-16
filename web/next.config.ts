import type { NextConfig } from "next";

// The browser reaches Django through this same origin (/api/* -> Django), so the session
// cookie is first-party and no CORS is needed. In production a reverse proxy does the same.
const API_ORIGIN = process.env.FSA_API_ORIGIN ?? "http://127.0.0.1:8210";

const nextConfig: NextConfig = {
  // Development-only indicator: keep it clear of the sidebar's Sign Out button.
  devIndicators: { position: "bottom-right" },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
  async headers() {
    return [
      {
        // Every page refuses to be framed, except a certificate PDF or a marked assessment, which the hub shows inside itself.
        source: "/((?!api/fsa/certificates/|api/fsa/results/|api/fsa/placements/).*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "same-origin" },
        ],
      },
      {
        source: "/api/fsa/certificates/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "Referrer-Policy", value: "same-origin" },
        ],
      },
      {
        source: "/api/fsa/placements/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "Referrer-Policy", value: "same-origin" },
        ],
      },
      {
        source: "/api/fsa/results/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "Referrer-Policy", value: "same-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
