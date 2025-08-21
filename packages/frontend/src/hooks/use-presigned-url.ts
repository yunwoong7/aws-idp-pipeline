import { useState, useEffect, useCallback } from 'react';
import { presignedUrlApi } from '@/lib/api';

// 글로벌 캐시 (SecureImage와 동일한 캐시 사용)
const urlCache = new Map<string, { url: string; timestamp: number; expiration: number }>();

const getCacheKey = (s3Uri: string, projectId: string) => `${s3Uri}::${projectId}`;

const getCachedUrl = (s3Uri: string, projectId: string): string | null => {
  const key = getCacheKey(s3Uri, projectId);
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

const setCachedUrl = (s3Uri: string, projectId: string, url: string, expiration: number) => {
  const key = getCacheKey(s3Uri, projectId);
  urlCache.set(key, {
    url,
    timestamp: Date.now(),
    expiration
  });
};

interface UsePresignedUrlResult {
  presignedUrl: string | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

/**
 * S3 URI를 Pre-signed URL로 변환하는 커스텀 훅
 * 보안 강화를 위해 실제 필요한 시점에 동적으로 URL을 생성합니다.
 */
export function usePresignedUrl(
  s3Uri: string | null | undefined,
  projectId: string | null | undefined,
  options: {
    expiration?: number;
    immediate?: boolean; // 즉시 로드할지 여부
  } = {}
): UsePresignedUrlResult {
  const { expiration = 3600, immediate = true } = options;
  
  const [presignedUrl, setPresignedUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPresignedUrl = useCallback(async () => {
    if (!s3Uri || !projectId) {
      setPresignedUrl(null);
      setError(null);
      return;
    }

    if (!s3Uri.startsWith('s3://')) {
      setPresignedUrl(null);
      setError('Invalid S3 URI format');
      return;
    }

    // 먼저 캐시에서 확인
    const cachedUrl = getCachedUrl(s3Uri, projectId);
    if (cachedUrl) {
      setPresignedUrl(cachedUrl);
      setError(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await presignedUrlApi.getPresignedUrl(s3Uri, projectId, expiration);
      setPresignedUrl(response.presigned_url);
      setError(null);
      
      // 캐시에 저장
      setCachedUrl(s3Uri, projectId, response.presigned_url, expiration);
    } catch (err) {
      console.error('Failed to get presigned URL:', err);
      setError(err instanceof Error ? err.message : 'Failed to get presigned URL');
      setPresignedUrl(null);
    } finally {
      setIsLoading(false);
    }
  }, [s3Uri, projectId, expiration]);

  const refetch = useCallback(async () => {
    // refetch 시에는 캐시를 지우고 새로 요청
    if (s3Uri && projectId) {
      const key = getCacheKey(s3Uri, projectId);
      urlCache.delete(key);
    }
    await fetchPresignedUrl();
  }, [fetchPresignedUrl, s3Uri, projectId]);

  useEffect(() => {
    if (!immediate || !s3Uri || !projectId) {
      return;
    }

    if (!s3Uri.startsWith('s3://')) {
      setError('Invalid S3 URI format');
      return;
    }

    // 먼저 캐시에서 확인
    const cachedUrl = getCachedUrl(s3Uri, projectId);
    if (cachedUrl) {
      setPresignedUrl(cachedUrl);
      setError(null);
      setIsLoading(false);
      return;
    }

    // 캐시에 없으면 API 요청
    fetchPresignedUrl();
  }, [s3Uri, projectId, immediate]);

  return {
    presignedUrl,
    isLoading,
    error,
    refetch,
  };
}

/**
 * 버튼 클릭 시 Pre-signed URL을 가져오는 훅
 * 사용자 액션에 따라 URL을 생성할 때 사용합니다.
 */
export function usePresignedUrlOnDemand(
  s3Uri: string | null | undefined,
  projectId: string | null | undefined,
  expiration: number = 3600
): UsePresignedUrlResult {
  return usePresignedUrl(s3Uri, projectId, { 
    expiration, 
    immediate: false 
  });
}