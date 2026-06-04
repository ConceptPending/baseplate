import type { NextConfig } from "next";

// The /api/* proxy is implemented as a Route Handler at
// src/app/api/[...path]/route.ts so the API_URL env var is read at runtime
// (not baked into the build). One Docker image works across environments.

const isDev = process.env.NODE_ENV !== "production";

// Content-Security-Policy.
//
// `'unsafe-inline'` on script-src is required because Next's App Router emits
// inline bootstrap/hydration <script> tags and we are not (yet) running the
// nonce middleware that would let us drop it. `'unsafe-eval'` is added only in
// development for React Fast Refresh. The policy still blocks the high-value
// vectors: no external script/style/object origins, no framing, locked-down
// base-uri and form-action. Hardening path: add a middleware that injects a
// per-request nonce and replace `'unsafe-inline'` with `'nonce-...'`.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  // HTTPS-only; browsers ignore it on plain-HTTP localhost so it's dev-safe.
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
];

const nextConfig: NextConfig = {
  output: "standalone",
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
