"use client";

import { useEffect, useState, useRef } from 'react';
import { documentApi } from '@/lib/api';
import { LoaderIcon, AlertCircle, RefreshCw, ImageIcon } from 'lucide-react';

// 글로벌 캐시로 이미 로드된 Pre-signed URL을 저장
const urlCache = new Map<string, { url: string; timestamp: number; expiration: number }>();

// 다른 컴포넌트에서 접근할 수 있도록 전역에 노출
if (typeof window !== 'undefined') {
  (window as any).__secureImageCache__ = urlCache;
}

const getCacheKey = (s3Uri: string) => `${s3Uri}`;

// Try to extract index_id from common S3 URI pattern: .../indexes/{indexId}/documents/...
const extractIndexIdFromS3Uri = (s3Uri: string | null | undefined): string | null => {
  if (!s3Uri) return null;
  try {
    const match = s3Uri.match(/\/indexes\/([^/]+)\/documents\//);
    return match?.[1] || null;
  } catch {
    return null;
  }
};

const getCachedUrl = (s3Uri: string): string | null => {
  const key = getCacheKey(s3Uri);
  const cached = urlCache.get(key);
  
  if (!cached) return null;
  
  // 만료 시간 체크 (현재 시간 + 1분 여유를 두고 체크)
  const now = Date.now();
  const expirationTime = cached.timestamp + (cached.expiration * 1000) - 60000; // 1분 여유
  
  if (now > expirationTime) {
    urlCache.delete(key);
    return null;
  }
  
  return cached.url;
};

const setCachedUrl = (s3Uri: string, url: string, expiration: number) => {
  const key = getCacheKey(s3Uri);
  urlCache.set(key, {
    url,
    timestamp: Date.now(),
    expiration
  });
};

interface SecureImageProps {
  s3Uri: string | null | undefined;
  projectId?: string; // Now optional for backward compatibility
  alt?: string;
  className?: string;
  width?: number;
  height?: number;
  style?: React.CSSProperties;
  onError?: () => void;
  onLoad?: () => void;
  placeholder?: React.ReactNode;
  errorPlaceholder?: React.ReactNode;
  showRetryButton?: boolean;
  expiration?: number;
}

/**
 * S3 URI를 받아 이미지를 안전하게 로드하는 재사용 가능한 컴포넌트
 * 에러 발생 시 재시도 옵션을 제공하고, 다양한 커스터마이징이 가능합니다.
 */
export const SecureImage = ({
  s3Uri,
  projectId,
  alt = '',
  className = '',
  width,
  height,
  style,
  onError,
  onLoad,
  placeholder,
  errorPlaceholder,
  showRetryButton = true,
  expiration = 3600,
}: SecureImageProps) => {
  const [presignedUrl, setPresignedUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imageError, setImageError] = useState(false);
  const [imageLoaded, setImageLoaded] = useState(false);

  const fetchPresignedUrl = async () => {
    console.log('🖼️ [SecureImage] fetchPresignedUrl called:', { s3Uri });
    
    if (!s3Uri) {
      console.error('🖼️ [SecureImage] Missing S3 URI:', { s3Uri });
      setError('Missing S3 URI');
      setIsLoading(false);
      return;
    }

    if (!s3Uri.startsWith('s3://')) {
      console.error('🖼️ [SecureImage] Invalid S3 URI format:', s3Uri);
      setError('Invalid S3 URI format');
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);
    setImageError(false);

    try {
      console.log('🖼️ [SecureImage] Calling documentApi.getPresignedUrlFromS3Uri...');
      const inferredIndexId = extractIndexIdFromS3Uri(s3Uri);
      const effectiveIndexId = (projectId && projectId.trim()) ? projectId : (inferredIndexId || undefined);
      const response = await documentApi.getPresignedUrlFromS3Uri(s3Uri, expiration, effectiveIndexId);
      console.log('🖼️ [SecureImage] documentApi response:', response);
      setPresignedUrl(response.presigned_url);
      setError(null);
      
      // 캐시에 저장
      setCachedUrl(s3Uri, response.presigned_url, expiration);
    } catch (err) {
      console.error('🖼️ [SecureImage] Failed to fetch presigned URL:', err);
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch presigned URL';
      setError(errorMessage);
      setPresignedUrl(null);
      onError?.();
    } finally {
      setIsLoading(false);
    }
  };

  const handleRetry = () => {
    setImageError(false);
    setImageLoaded(false);
    // 재시도 시에는 캐시를 지우고 새로 요청
    if (s3Uri) {
      const key = getCacheKey(s3Uri);
      urlCache.delete(key);
    }
    fetchPresignedUrl();
  };

  const handleImageError = () => {
    setImageError(true);
    setImageLoaded(false);
    onError?.();
  };

  const handleImageLoad = () => {
    setImageError(false);
    setImageLoaded(true);
    onLoad?.();
  };

  useEffect(() => {
    console.log('🖼️ [SecureImage] useEffect called:', { 
      s3Uri,
      s3UriType: typeof s3Uri,
      s3UriLength: s3Uri?.length,
      isValidS3Uri: s3Uri?.startsWith('s3://')
    });
    
    if (!s3Uri) {
      console.log('🖼️ [SecureImage] useEffect: Missing S3 URI - setting error state');
      setError('Missing S3 URI');
      setIsLoading(false);
      return;
    }

    if (!s3Uri.startsWith('s3://')) {
      console.log('🖼️ [SecureImage] useEffect: Invalid S3 URI format - setting error state:', s3Uri);
      setError('Invalid S3 URI format');
      setIsLoading(false);
      return;
    }
    
    // 먼저 캐시에서 확인
    const cachedUrl = getCachedUrl(s3Uri);
    if (cachedUrl) {
      console.log('🖼️ [SecureImage] Using cached URL:', cachedUrl);
      setPresignedUrl(cachedUrl);
      setError(null);
      setImageError(false);
      setIsLoading(false);
      return;
    }

    console.log('🖼️ [SecureImage] No cached URL found, fetching from API...');
    // 캐시에 없으면 API 요청
    fetchPresignedUrl();
  }, [s3Uri]);

  // 로딩 상태
  if (isLoading) {
    return (
      <div 
        className={`flex items-center justify-center bg-slate-100 border border-slate-200 rounded ${className}`}
        style={{ width, height, ...style }}
      >
        {placeholder || (
          <div className="flex flex-col items-center gap-2 text-slate-500">
            <LoaderIcon className="h-6 w-6 animate-spin" />
            <span className="text-sm">로딩 중...</span>
          </div>
        )}
      </div>
    );
  }

  // 에러 상태
  if (error || imageError || !presignedUrl) {
    return (
      <div 
        className={`flex items-center justify-center bg-slate-50 border border-slate-200 rounded ${className}`}
        style={{ width, height, ...style }}
      >
        {errorPlaceholder || (
          <div className="flex flex-col items-center gap-2 text-slate-400 p-4">
            <AlertCircle className="h-6 w-6" />
            <span className="text-sm text-center">이미지를 불러올 수 없습니다</span>
            {error && <span className="text-xs text-red-500 text-center">{error}</span>}
            {showRetryButton && (
              <button
                onClick={handleRetry}
                className="flex items-center gap-1 px-3 py-1 text-xs bg-blue-500 hover:bg-blue-600 text-white rounded transition-colors"
                title="다시 시도"
              >
                <RefreshCw className="h-3 w-3" />
                새로고침
              </button>
            )}
          </div>
        )}
      </div>
    );
  }

  // 성공 상태 - 이미지 표시
  return (
    <img
      src={presignedUrl}
      alt={alt}
      className={className}
      width={width}
      height={height}
      style={style}
      onError={handleImageError}
      onLoad={handleImageLoad}
    />
  );
};

/**
 * 클릭 시에만 이미지를 로드하는 컴포넌트
 */
interface SecureImageOnDemandProps extends Omit<SecureImageProps, 'placeholder'> {
  buttonText?: string;
  buttonClassName?: string;
}

export const SecureImageOnDemand = ({
  s3Uri,
  projectId,
  buttonText = '이미지 로드',
  buttonClassName = '',
  ...imageProps
}: SecureImageOnDemandProps) => {
  const [shouldLoad, setShouldLoad] = useState(false);

  if (!shouldLoad) {
    return (
      <div className={`flex items-center justify-center bg-slate-50 border border-slate-200 rounded ${imageProps.className}`}>
        <button
          onClick={() => setShouldLoad(true)}
          className={`px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors ${buttonClassName}`}
        >
          <ImageIcon className="h-4 w-4 inline mr-2" />
          {buttonText}
        </button>
      </div>
    );
  }

  return <SecureImage s3Uri={s3Uri} {...imageProps} />;
};