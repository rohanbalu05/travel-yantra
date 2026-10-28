// Firebase's sign-in handler is served from our own host, so authDomain can be ty-web's host:
// Android Chrome drops redirect sign-in when the handler is on another site (third-party storage).
const firebaseProject = process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? "";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  trailingSlash: true,
  images: { unoptimized: true },
  // Firebase's handler URLs have no trailing slash; keep them as they are.
  skipTrailingSlashRedirect: true,
  async rewrites() {
    if (!firebaseProject) return [];
    const target = `https://${firebaseProject}.firebaseapp.com`;
    return [
      { source: "/__/auth/:path*", destination: `${target}/__/auth/:path*` },
      { source: "/__/firebase/:path*", destination: `${target}/__/firebase/:path*` },
    ];
  },
};

export default nextConfig;
