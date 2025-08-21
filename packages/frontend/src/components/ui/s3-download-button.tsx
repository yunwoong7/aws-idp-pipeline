"use client";

import React, { useState } from 'react';
import { usePresignedUrlOnDemand } from '@/hooks/use-presigned-url';
import { Download, LoaderIcon, AlertCircle } from 'lucide-react';

interface S3DownloadButtonProps {
  s3Uri: string | null | undefined;
  projectId: string | null | undefined;
  fileName?: string;
  children?: React.ReactNode;
  className?: string;
  disabled?: boolean;
  expiration?: number;
  onDownloadStart?: () => void;
  onDownloadComplete?: () => void;
  onError?: (error: string) => void;
}

/**
 * S3 URI에서 파일을 다운로드하는 버튼 컴포넌트
 * 클릭 시 동적으로 Pre-signed URL을 생성하여 다운로드를 시작합니다.
 */
export function S3DownloadButton({
  s3Uri,
  projectId,
  fileName,
  children,
  className = '',
  disabled = false,
  expiration = 3600,
  onDownloadStart,
  onDownloadComplete,
  onError,
}: S3DownloadButtonProps) {
  const [isDownloading, setIsDownloading] = useState(false);
  const { presignedUrl, isLoading, error, refetch } = usePresignedUrlOnDemand(
    s3Uri,
    projectId,
    expiration
  );

  const extractFileName = (s3Uri: string): string => {
    try {
      const parts = s3Uri.split('/');
      return parts[parts.length - 1] || 'download';
    } catch {
      return 'download';
    }
  };

  const handleDownload = async () => {
    if (!s3Uri || !projectId || disabled || isLoading) return;

    try {
      setIsDownloading(true);
      onDownloadStart?.();

      // Pre-signed URL이 없으면 생성
      if (!presignedUrl) {
        await refetch();
        return; // refetch 후 effect에서 자동으로 다운로드 처리
      }

      // 다운로드 실행
      const link = document.createElement('a');
      link.href = presignedUrl;
      link.download = fileName || extractFileName(s3Uri);
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      onDownloadComplete?.();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Download failed';
      console.error('Download error:', errorMessage);
      onError?.(errorMessage);
    } finally {
      setIsDownloading(false);
    }
  };

  // Pre-signed URL이 생성되면 자동으로 다운로드 실행
  React.useEffect(() => {
    if (presignedUrl && isDownloading) {
      const link = document.createElement('a');
      link.href = presignedUrl;
      link.download = fileName || extractFileName(s3Uri || '');
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      onDownloadComplete?.();
      setIsDownloading(false);
    }
  }, [presignedUrl, isDownloading, fileName, s3Uri, onDownloadComplete]);

  // 에러 처리
  React.useEffect(() => {
    if (error) {
      onError?.(error);
      setIsDownloading(false);
    }
  }, [error, onError]);

  const isButtonDisabled = disabled || !s3Uri || !projectId;
  const showLoading = isLoading || isDownloading;

  return (
    <button
      onClick={handleDownload}
      disabled={isButtonDisabled || showLoading}
      className={`
        inline-flex items-center gap-2 px-4 py-2 rounded-md font-medium text-sm
        transition-all duration-200
        ${isButtonDisabled || showLoading
          ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
          : 'bg-blue-500 text-white hover:bg-blue-600 focus:ring-2 focus:ring-blue-500 focus:ring-offset-1'
        }
        ${className}
      `}
      title={error ? `Error: ${error}` : undefined}
    >
      {showLoading ? (
        <>
          <LoaderIcon className="h-4 w-4 animate-spin" />
          {isLoading ? 'Preparing...' : 'Downloading...'}
        </>
      ) : error ? (
        <>
          <AlertCircle className="h-4 w-4" />
          Download Error
        </>
      ) : (
        <>
          <Download className="h-4 w-4" />
          {children || 'Download'}
        </>
      )}
    </button>
  );
}

