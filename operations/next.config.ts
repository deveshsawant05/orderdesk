import type { NextConfig } from 'next';
const apiOrigin = (process.env.API_INTERNAL_URL || 'http://localhost:8000').replace(/\/$/, '');
const config: NextConfig = {
  output: 'standalone',
  poweredByHeader: false,
  devIndicators: false,
  async rewrites() {
    return {
      beforeFiles: [{source:'/api/:path*', destination:apiOrigin+'/:path*'}],
      afterFiles: [],
      fallback: [],
    };
  },
};
export default config;
