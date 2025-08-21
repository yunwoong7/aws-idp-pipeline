"use client";

import React, { useState } from 'react';
import { presignedUrlApi } from '@/lib/api';
import { Download, LoaderIcon, AlertCircle, ExternalLink, FileText } from 'lucide-react';

interface SecureLinkProps {
  s3Uri: string | null | undefined;
  projectId: string;
  fileName?: string;
  children?: React.ReactNode;
  className?: string;
  disabled?: boolean;
  expiration?: number;
  onSuccess?: (url: string) => void;
  onError?: (error: string) => void;
  openInNewTab?: boolean; // true면 새 탭에서 열기, false면 다운로드
  variant?: 'download' | 'view' | 'link';
}

/**
 * S3 URI를 받아 클릭 시점에 Pre-signed URL을 생성하고 파일을 열거나 다운로드하는 컴포넌트
 */
export const SecureLink = ({
  s3Uri,
  projectId,
  fileName,
  children,
  className = '',
  disabled = false,
  expiration = 3600,
  onSuccess,
  onError,
  openInNewTab = true,
  variant = 'download',
}: SecureLinkProps) => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const extractFileName = (s3Uri: string): string => {
    try {
      const parts = s3Uri.split('/');
      return parts[parts.length - 1] || 'download';
    } catch {
      return 'download';
    }
  };

  const handleClick = async (e: React.MouseEvent) => {
    e.preventDefault();
    
    if (!s3Uri || !projectId || disabled || isLoading) return;

    if (!s3Uri.startsWith('s3://')) {
      const errorMessage = 'Invalid S3 URI format';
      setError(errorMessage);
      onError?.(errorMessage);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await presignedUrlApi.getPresignedUrl(s3Uri, projectId, expiration);
      const presignedUrl = response.presigned_url;
      
      onSuccess?.(presignedUrl);

      if (openInNewTab || variant === 'view') {
        // 새 탭에서 열기 (PDF 뷰어 등)
        window.open(presignedUrl, '_blank', 'noopener,noreferrer');
      } else {
        // 다운로드
        const link = document.createElement('a');
        link.href = presignedUrl;
        link.download = fileName || extractFileName(s3Uri);
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to get file URL';
      console.error('SecureLink error:', errorMessage);
      setError(errorMessage);
      onError?.(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const getIcon = () => {
    if (isLoading) return <LoaderIcon className="h-4 w-4 animate-spin" />;
    if (error) return <AlertCircle className="h-4 w-4" />;
    
    switch (variant) {
      case 'download':
        return <Download className="h-4 w-4" />;
      case 'view':
        return <ExternalLink className="h-4 w-4" />;
      case 'link':
        return <FileText className="h-4 w-4" />;
      default:
        return <Download className="h-4 w-4" />;
    }
  };

  const getDefaultText = () => {
    if (isLoading) return '로딩 중...';
    if (error) return '오류 발생';
    
    switch (variant) {
      case 'download':
        return '다운로드';
      case 'view':
        return '보기';
      case 'link':
        return fileName || '파일';
      default:
        return '다운로드';
    }
  };

  const isButtonDisabled = disabled || !s3Uri || !projectId;

  return (
    <button
      onClick={handleClick}
      disabled={isButtonDisabled || isLoading}
      className={`
        inline-flex items-center gap-2 px-3 py-2 rounded-md font-medium text-sm
        transition-all duration-200
        ${isButtonDisabled || isLoading
          ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
          : error
          ? 'bg-red-100 text-red-600 hover:bg-red-200'
          : 'bg-blue-500 text-white hover:bg-blue-600 focus:ring-2 focus:ring-blue-500 focus:ring-offset-1'
        }
        ${className}
      `}
      title={error ? `Error: ${error}` : undefined}
    >
      {getIcon()}
      {children || getDefaultText()}
    </button>
  );
};

/**
 * 간단한 파일 클릭 핸들러 (컴포넌트 외부에서 사용)
 */
export const handleSecureFileClick = async (
  s3Uri: string, 
  projectId: string, 
  options: {
    expiration?: number;
    openInNewTab?: boolean;
    fileName?: string;
  } = {}
) => {
  const { expiration = 3600, openInNewTab = true, fileName } = options;

  if (!s3Uri || !projectId) {
    throw new Error('Missing S3 URI or project ID');
  }

  if (!s3Uri.startsWith('s3://')) {
    throw new Error('Invalid S3 URI format');
  }

  try {
    const response = await presignedUrlApi.getPresignedUrl(s3Uri, projectId, expiration);
    const presignedUrl = response.presigned_url;

    if (openInNewTab) {
      window.open(presignedUrl, '_blank', 'noopener,noreferrer');
    } else {
      const extractFileName = (s3Uri: string): string => {
        try {
          const parts = s3Uri.split('/');
          return parts[parts.length - 1] || 'download';
        } catch {
          return 'download';
        }
      };

      const link = document.createElement('a');
      link.href = presignedUrl;
      link.download = fileName || extractFileName(s3Uri);
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }

    return presignedUrl;
  } catch (error) {
    console.error('Could not get file URL:', error);
    throw error;
  }
};