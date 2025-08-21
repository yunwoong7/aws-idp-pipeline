import { documentApi } from "@/lib/api";

// 간단한 URL 정리 함수 - 잘못된 접두사만 제거
export const cleanImageUrl = (url: string | undefined, componentName: string = 'unknown'): string => {
    if (!url) {
        console.log(`🧹 [cleanImageUrl:${componentName}] URL이 비어있음`);
        return '';
    }
    
    console.log(`🧹 [cleanImageUrl:${componentName}] 입력:`, url.substring(0, 100));
    
    let cleanedUrl = url.trim();
    
    // "title : url" 형태에서 URL만 추출
    if (cleanedUrl.includes(' : ')) {
        const parts = cleanedUrl.split(' : ');
        if (parts.length >= 2) {
            cleanedUrl = parts[1].trim();
            console.log(`🧹 [cleanImageUrl:${componentName}] "title : url" 형태에서 URL 추출`);
        }
    }
    
    // 잘못된 data:image/ 접두사 제거 (https:// URL 앞에 붙은 경우만)
    if (cleanedUrl.startsWith('data:image/') && cleanedUrl.includes('https://')) {
        // data:image/xxx;base64,https://... 형태에서 https://... 부분만 추출
        const match = cleanedUrl.match(/https:\/\/.+/);
        if (match) {
            cleanedUrl = match[0];
            console.log(`🔧 [cleanImageUrl:${componentName}] 잘못된 data:image/ 접두사 제거됨`);
        }
    }
    
    console.log(`🧹 [cleanImageUrl:${componentName}] 결과:`, cleanedUrl.substring(0, 100));
    
    return cleanedUrl;
};

// 이미지 URL인지 확인하는 함수
export const isImageUrl = (url: string): boolean => {
    const imageExtensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'];
    const urlLower = url.toLowerCase();
    return imageExtensions.some(ext => urlLower.includes(ext));
};

// 파일 크기 포맷팅 함수
export const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

// 날짜 포맷팅 함수
export const formatDate = (dateString: string): string => {
    return new Date(dateString).toLocaleDateString('ko-KR', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    });
};

// S3 URL에서 project_id 추출하는 함수
export const extractProjectIdFromS3Url = (s3Url: string): string | null => {
    try {
        // s3://bucket-name/projects/project-id/... 형태에서 project_id 추출
        const match = s3Url.match(/s3:\/\/[^\/]+\/projects\/([^\/]+)/);
        return match ? match[1] : null;
    } catch (error) {
        console.error('Project ID 추출 오류:', error);
        return null;
    }
};

// S3 URL을 presigned URL로 변환하는 함수
export const getPresignedUrl = async (s3Url: string): Promise<string> => {
    if (!s3Url.startsWith('s3://')) {
        return s3Url; // 이미 HTTP URL이거나 다른 형태
    }

    try {
        const projectId = extractProjectIdFromS3Url(s3Url);
        if (!projectId) {
            throw new Error('Project ID를 추출할 수 없습니다');
        }

        const data = await documentApi.getPresignedUrlFromS3Uri(s3Url, 3600, projectId);
        return data.presigned_url;
    } catch (error) {
        console.error('Presigned URL 생성 오류:', error);
        return s3Url; // 실패하면 원본 URL 반환
    }
};