import type { NextConfig } from 'next';
import { config } from 'dotenv';
import { resolve } from 'path';

// 루트 .env 파일 로드
config({ path: resolve(__dirname, '../../.env') });

// API Base URL 설정 (환경변수 또는 기본값)
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.API_BASE_URL || 'http://localhost:8000';
console.log('🔧 Next.js rewrites using API_BASE_URL:', API_BASE_URL);

const nextConfig: NextConfig = {
  distDir: '.next',
  devIndicators: false,
  output: 'standalone', // Docker를 위한 standalone 모드
  eslint: {
    // 프로덕션 빌드에서 ESLint 무시
    ignoreDuringBuilds: true,
  },
  typescript: {
    // 프로덕션 빌드에서 TypeScript 에러 무시 (필요한 경우)
    ignoreBuildErrors: false,
  },
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'assets.aceternity.com',
        pathname: '/**', // 모든 경로 허용
      },
    ],
  },

  webpack: (config, { isServer }) => {
    // PDF.js를 위한 설정
    config.resolve.alias = {
      ...config.resolve.alias,
      canvas: false,
    };
    
    config.externals = config.externals || [];
    config.externals.push({
      canvas: 'canvas',
    });

    // 클라이언트 사이드에서 Node.js 전용 모듈들을 제외
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        child_process: false,
        fs: false,
        net: false,
        tls: false,
        crypto: false,
      };
    }

    return config;
  },

  // API rewrites - 로컬 개발 시 backend로 프록시
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${API_BASE_URL}/api/:path*`,
      },
      {
        source: '/proxy/s3/:path*',
        destination: 'https://aws-idp-ai-documents-057336397075-us-west-2-dev.s3.amazonaws.com/:path*',
      },
    ];
  },
};

export default nextConfig;