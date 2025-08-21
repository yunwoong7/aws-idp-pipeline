"use client";

import { useState } from 'react';
import { usePresignedUrl } from '@/hooks/use-presigned-url';
import { LoaderIcon, AlertCircle, ImageIcon } from 'lucide-react';

interface S3ImageProps {
  s3Uri: string | null | undefined;
  projectId: string | null | undefined;
  alt?: string;
  className?: string;
  width?: number;
  height?: number;
  style?: React.CSSProperties;
  onError?: () => void;
  onLoad?: () => void;
  placeholder?: React.ReactNode;
  errorPlaceholder?: React.ReactNode;
}

/**
 * S3 URI를 사용하여 동적으로 Pre-signed URL을 생성하고 이미지를 표시하는 컴포넌트
 * 보안 강화를 위해 실제 이미지가 필요한 시점에 URL을 생성합니다.
 */
export function S3Image({
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
}: S3ImageProps) {
  const [imageError, setImageError] = useState(false);
  
  // S3 URI인지 확인하고 Pre-signed URL 생성 여부 결정
  const isS3Uri = s3Uri?.startsWith('s3://');
  const isHttpUrl = s3Uri?.startsWith('http://') || s3Uri?.startsWith('https://');
  
  // S3 URI인 경우에만 usePresignedUrl 훅 사용
  const { presignedUrl, isLoading, error } = usePresignedUrl(
    isS3Uri ? s3Uri : null, 
    projectId
  );

  const handleImageError = () => {
    setImageError(true);
    onError?.();
  };

  const handleImageLoad = () => {
    setImageError(false);
    onLoad?.();
  };

  // 최종 이미지 URL 결정
  const finalImageUrl = isS3Uri ? presignedUrl : (isHttpUrl ? s3Uri : null);

  // S3 URI이지만 아직 Pre-signed URL이 로딩중인 경우
  if (isS3Uri && isLoading) {
    return (
      <div 
        className={`flex items-center justify-center bg-slate-100 border border-slate-200 rounded ${className}`}
        style={{ width, height, ...style }}
      >
        {placeholder || (
          <div className="flex flex-col items-center gap-2 text-slate-500">
            <LoaderIcon className="h-6 w-6 animate-spin" />
            <span className="text-sm">Loading...</span>
          </div>
        )}
      </div>
    );
  }

  // 에러 상태 또는 이미지 URL이 없는 경우
  if (error || imageError || !finalImageUrl) {
    return (
      <div 
        className={`flex items-center justify-center bg-slate-50 border border-slate-200 rounded ${className}`}
        style={{ width, height, ...style }}
      >
        {errorPlaceholder || (
          <div className="flex flex-col items-center gap-2 text-slate-400">
            <AlertCircle className="h-6 w-6" />
            <span className="text-sm">Image not available</span>
            {error && <span className="text-xs text-red-500">{error}</span>}
            {!s3Uri && <span className="text-xs text-gray-400">No image URI provided</span>}
            {s3Uri && !isS3Uri && !isHttpUrl && <span className="text-xs text-gray-400">Invalid URI format: {s3Uri}</span>}
          </div>
        )}
      </div>
    );
  }

  // 성공 상태 - 이미지 표시
  return (
    <img
      src={finalImageUrl}
      alt={alt}
      className={className}
      width={width}
      height={height}
      style={style}
      onError={handleImageError}
      onLoad={handleImageLoad}
    />
  );
}

/**
 * 버튼 클릭 시에만 이미지를 로드하는 컴포넌트
 */
interface S3ImageOnDemandProps extends Omit<S3ImageProps, 'placeholder'> {
  buttonText?: string;
  buttonClassName?: string;
}

export function S3ImageOnDemand({
  s3Uri,
  projectId,
  buttonText = 'Load Image',
  buttonClassName = '',
  ...imageProps
}: S3ImageOnDemandProps) {
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

  return <S3Image s3Uri={s3Uri} projectId={projectId} {...imageProps} />;
}