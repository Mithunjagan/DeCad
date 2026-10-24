const nextConfig = {
  output: 'standalone',
  devIndicators: false,
  experimental: {proxyTimeout: 900000, cpus: 1, webpackBuildWorker: false},
  async rewrites() {
    return [{source:'/api/:path*',destination:`${process.env.INTERNAL_API_URL || 'http://localhost:8100'}/:path*`}];
  }
};
export default nextConfig;
