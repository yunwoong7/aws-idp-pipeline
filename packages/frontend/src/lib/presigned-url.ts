const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export interface PresignedUrlRequest {
  s3_uri: string;
  expiration?: number;
  project_id: string;
}

export interface PresignedUrlResponse {
  s3_uri: string;
  presigned_url: string;
  expiration_seconds: number;
  expires_at: number;
  generated_at: string;
}

export async function getPresignedUrl(request: PresignedUrlRequest): Promise<PresignedUrlResponse> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/get-presigned-url`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`Failed to get presigned URL: ${response.status} ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error getting presigned URL:', error);
    throw error;
  }
}

// S3 URI에서 presigned URL을 가져오는 유틸리티 함수
export async function getImageUrl(s3Uri: string, projectId: string): Promise<string> {
  try {
    const response = await getPresignedUrl({
      s3_uri: s3Uri,
      project_id: projectId,
      expiration: 3600
    });
    return response.presigned_url;
  } catch (error) {
    console.error('Failed to get image URL:', error);
    return s3Uri; // fallback to original URI
  }
}