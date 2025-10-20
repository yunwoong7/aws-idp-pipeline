

// API Configuration - 빌드타임 환경변수만 사용
const isBrowser = () => typeof window !== 'undefined';

if (isBrowser()) {
  console.log('🚀 API Configuration (env):', {
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
    NEXT_PUBLIC_ECS_BACKEND_URL: process.env.NEXT_PUBLIC_ECS_BACKEND_URL,
  });
}

// Helper functions for backward compatibility
async function getApiBaseUrl(): Promise<string> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  console.log('🔧 getApiBaseUrl() - NEXT_PUBLIC_API_BASE_URL:', apiBaseUrl);
  
  // API Gateway URL이 설정되지 않은 경우 backend URL로 폴백
  if (!apiBaseUrl || apiBaseUrl.trim() === '') {
    console.log('⚠️ NEXT_PUBLIC_API_BASE_URL is empty, falling back to backend URL');
    return await getBackendUrl();
  }
  
  return apiBaseUrl;
}

async function getBackendUrl(): Promise<string> {
  // 클라이언트(브라우저)
  if (isBrowser() && typeof window !== 'undefined' && window.location) {
    const isLocalHost = ['localhost', '127.0.0.1'].includes(window.location.hostname);
    if (isLocalHost) {
      const localEnv = process.env.NEXT_PUBLIC_LOCAL_BACKEND_URL;
      const localBase = (localEnv && localEnv.startsWith('http')) ? localEnv : 'http://localhost:8000';
      console.log('🏠 Using local backend base URL:', localBase);
      return localBase;
    }
    
    const originBase = window.location.origin;
    console.log('🌐 Using runtime origin as backend base URL:', originBase);
    return originBase;
  }

  // 서버 런타임(Next.js Node 서버)
  const ecsUrl = process.env.NEXT_PUBLIC_ECS_BACKEND_URL;
  if (ecsUrl && ecsUrl !== 'http://localhost:8000') {
    console.log('🧰 Using server env backend base URL:', ecsUrl);
    return ecsUrl;
  }
  const localEnv = process.env.NEXT_PUBLIC_LOCAL_BACKEND_URL;
  if (localEnv && localEnv.startsWith('http')) {
    console.log('🧰 Using server local backend base URL:', localEnv);
    return localEnv;
  }

  console.log('🏠 Using default local backend base URL: http://localhost:8000');
  return 'http://localhost:8000';
}

// Project-related interfaces removed as we're moving to index-based architecture

// Documents related types
export interface Document {
  document_id: string;
  upload_id: string;
  index_id: string;
  project_id?: string; // Add project_id for compatibility
  file_name: string;
  file_type: string;
  file_size: number;
  status: string;
  processing_status: string;
  processing_completed_at: string | null;
  created_at: string;
  updated_at: string;
  summary: string;
  total_pages?: string;
  images_generated?: string;
  description?: string;
  download_url?: string;
  file_uri?: string;
  statistics: {
    table_count: string;
    figure_count: string;
    hyperlink_count: string;
    element_count: string;
  };
  bda_metadata_uri: string;
  representation: {
    markdown: string;
  };
  page_images?: Array<{
    page_number: string | number;
    page_index?: string;
    image_url?: string;
    file_uri?: string | null;
    image_file_uri?: string;
    image_s3_path?: string;
    page_status?: string;
    analysis_completed_at?: string;
    analysis_steps_count?: string | number;
  }>;
  analysis_stats?: {
    total_pages: number;
    completed_pages: number;
  };
}

export interface DocumentsResponse {
  index_id: string;
  documents: Document[];
  total_count: number;
}

// Dashboard types (deprecated - moved to index-based architecture)
export interface IndexDashboardData {
  index_id: string;
  index_name: string;
  description: string;
  manager_name?: string;
  status: string;
  created_at: string;
  updated_at: string;
  last_analysis_date: string | null;
  tags: string[];
  metadata: Record<string, any>;
  document_count: string | number;
  total_pages: string | number;
  analyzed_pages: string | number;
  real_time_stats?: {
    total_documents: number;
    analyzing_documents: number;
    completed_documents: number;
    total_pages: number;
    analyzing_pages: number;
    completed_pages: number;
    pending_pages: number;
    analysis_progress: number;
    event_count: number;
  };
}

// Presigned URL types
export interface PresignedUrlRequest {
  file_name: string;
  file_type: string;
  project_id: string;
}

export interface PresignedUrlResponse {
  upload_url: string;
  file_key: string;
  upload_id: string;
  file_uri: string;
}

// Chat types
export interface ChatRequest {
  message: string;
  thread_id?: string;
  files?: File[];
  index_id?: string;
  document_id?: string;
  segment_id?: string | null;
}

// Search types
export interface HybridSearchRequest {
  index_id: string;
  query: string;
  size?: number;
  filter_document_id?: string;
}

export interface HybridSearchResponse {
  success: boolean;
  data: {
    query: string;
    search_type: string;
    total_results: number;
    returned_results: number;
    text_weight: number;
    vector_weight: number;
    results: Array<{
      page_id: string;
      page_index: number;
      project_id: string;
      document_id: string;
      image_uri: string;
      file_uri: string;
      image_presigned_url: string;
      file_presigned_url?: string;
      highlight?: {
        [key: string]: string[];
      };
    }>;
  };
}

// Reinit types
export interface ReinitRequest {
  force?: boolean;
  reload_prompt?: boolean;
  thread_id?: string;
  project_id?: string;
}

export interface ReinitResponse {
  success: boolean;
  message: string;
}

// Project API removed - moving to index-based architecture

export const documentApi = {
  // 문서 목록 조회 (project-independent)
  async getDocuments(simple?: boolean, segments?: boolean, indexId?: string): Promise<DocumentsResponse> {
    const params = new URLSearchParams();
    if (simple) params.append('simple', 'true');
    if (segments) params.append('segments', 'true');
    if (indexId) params.append('index_id', indexId);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    
    const baseUrl = await getApiBaseUrl();
    const response = await fetch(`${baseUrl}/api/documents${queryString}`);
    if (!response.ok) {
      throw new Error('문서 목록을 가져오는데 실패했습니다');
    }
    return response.json();
  },

  // 문서 상세 조회 (segment_images 포함)
  async getDocumentDetail(documentId: string, indexId?: string): Promise<any> {
    const baseUrl = await getApiBaseUrl();
    const url = new URL(`${baseUrl}/api/documents/${documentId}`);
    if (indexId) {
      url.searchParams.append('index_id', indexId);
    }
    const response = await fetch(url.toString());
    if (!response.ok) {
      const text = await response.text().catch(() => '');
      throw new Error(`문서 상세 조회 실패: ${response.status} ${text}`);
    }
    return response.json();
  },

  // 문서 삭제 (project-independent)
  async deleteDocument(documentId: string, indexId?: string): Promise<void> {
    const baseUrl = await getApiBaseUrl();
    const url = new URL(`${baseUrl}/api/documents/${documentId}`);
    if (indexId) {
      url.searchParams.append('index_id', indexId);
    }
    
    const response = await fetch(url.toString(), {
      method: 'DELETE',
    });
    if (!response.ok) {
      throw new Error('문서 삭제에 실패했습니다');
    }
  },

  // 문서 업로드를 위한 presigned URL 생성
  async getPresignedUrl(request: PresignedUrlRequest): Promise<PresignedUrlResponse> {
    const baseUrl = await getApiBaseUrl();
    const response = await fetch(`${baseUrl}/api/get-presigned-url`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });
    
    if (!response.ok) {
      throw new Error('Presigned URL 생성에 실패했습니다');
    }
    
    return response.json();
  },

  // S3에 파일 업로드
  async uploadToS3(uploadUrl: string, file: File): Promise<void> {
    const response = await fetch(uploadUrl, {
      method: 'PUT',
      headers: {
        'Content-Type': file.type,
      },
      body: file,
    });
    
    if (!response.ok) {
      throw new Error('파일 업로드에 실패했습니다');
    }
  },

  // S3 URI를 presigned URL로 변환 (project-independent)
  async getPresignedUrlFromS3Uri(s3Uri: string, expiration: number = 3600, indexId?: string): Promise<{ presigned_url: string }> {
    console.log('🔍 [getPresignedUrlFromS3Uri] Parameters:', { s3Uri, expiration, indexId });
    
    const requestBody = {
      s3_uri: s3Uri,
      expiration: expiration,
      ...(indexId && indexId.trim() && { index_id: indexId }),
    };
    
    console.log('🔍 [getPresignedUrlFromS3Uri] Request body:', requestBody);
    
    const baseUrl = await getApiBaseUrl();
    const response = await fetch(`${baseUrl}/api/get-presigned-url`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody),
    });
    
    if (!response.ok) {
      throw new Error('Presigned URL 변환에 실패했습니다');
    }
    
    return response.json();
  },

  // 문서 업로드 (XMLHttpRequest를 사용하여 업로드 진행률 지원)
  async uploadDocument(formData: FormData, options?: { onUploadProgress?: (progressEvent: any) => void }): Promise<any> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      
      // 업로드 진행률 처리
      if (options?.onUploadProgress) {
        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable) {
            options.onUploadProgress!({
              loaded: event.loaded,
              total: event.total
            });
          }
        });
      }
      
      // 요청 완료 처리
      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const response = JSON.parse(xhr.responseText);
            // 응답이 이미 올바른 구조를 가지고 있으면 그대로 반환
            if (response.success !== undefined) {
              resolve(response);
            } else {
              // 응답을 표준 구조로 래핑
              resolve({ success: true, data: response, message: 'Upload successful' });
            }
          } catch (error) {
            resolve({ success: true, data: null, message: 'Upload successful' });
          }
        } else {
          reject(new Error(`Upload failed: ${xhr.statusText} - ${xhr.responseText}`));
        }
      });
      
      // 에러 처리
      xhr.addEventListener('error', () => {
        reject(new Error('Network error during upload'));
      });
      
      // 요청 전송
      (async () => {
        const baseUrl = await getApiBaseUrl();
        xhr.open('POST', `${baseUrl}/api/documents/upload`);
        xhr.send(formData);
      })();
    });
  },

  // 분석 데이터 조회 (index-based) - 메타데이터만 또는 전체 데이터
  async getAnalysisData(indexId: string, documentId: string, options?: {
    metadataOnly?: boolean,
    size?: number
  }): Promise<any> {
    const params = new URLSearchParams();
    if (indexId) {
      params.append('index_id', indexId);
    }

    // 메타데이터만 요청하는 경우 더 많은 세그먼트를 가져오고 크기 최적화
    if (options?.metadataOnly) {
      params.append('metadata_only', 'true');
      params.append('size', String(options.size || 5000)); // 기본 5000개
    } else {
      params.append('size', String(options?.size || 100)); // 전체 데이터는 기본 100개
    }

    const queryString = params.toString() ? `?${params.toString()}` : '';

    const baseUrl = await getApiBaseUrl();
    const response = await fetch(`${baseUrl}/api/opensearch/documents/${documentId}${queryString}`);

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Failed to fetch analysis data. (${response.status}): ${errorText}`);
    }

    return response.json();
  },

  // 개별 세그먼트 상세 조회
  async getSegmentDetail(indexId: string, documentId: string, segmentId: string): Promise<any> {
    const baseUrl = await getApiBaseUrl();
    // 백엔드 API 경로: /api/documents/{document_id}/segments/{segment_id}?index_id={index_id}&filter_final=false
    const response = await fetch(`${baseUrl}/api/documents/${documentId}/segments/${segmentId}?index_id=${indexId}&filter_final=false`);

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Failed to fetch segment detail. (${response.status}): ${errorText}`);
    }

    return response.json();
  },

  // 대용량 파일 업로드용 Pre-signed URL 생성 (deprecated - use generateUnifiedUploadUrl)
  async generateLargeFileUploadUrl(indexId: string, fileInfo: {
    file_name: string;
    file_size: number;
    file_type?: string;
    description?: string;
  }): Promise<{
    document_id: string;
    upload_url: string;
    completion_callback_url: string;
    file_uri: string;
    upload_method: string;
    content_type: string;
    expiration_hours: number;
  }> {
    const baseUrl = await getApiBaseUrl();
    const response = await fetch(`${baseUrl}/api/indexes/${indexId}/documents/upload-large`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(fileInfo),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(`Large file upload URL 생성 실패: ${response.status} - ${errorData.message || response.statusText}`);
    }

    const result = await response.json();
    // Handle different response formats
    if (result.data) {
      return result.data;
    } else if (result.upload_url) {
      // Direct response format
      return result;
    } else {
      throw new Error('Invalid response format: missing upload_url');
    }
  },

  // 백엔드를 통한 직접 파일 업로드 (CORS 문제 해결)
  async uploadDocumentViaBackend(file: File, indexId: string, description?: string): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('index_id', indexId);
    if (description) {
      formData.append('description', description);
    }

    const backendUrl = await getBackendUrl();
    const response = await fetch(`${backendUrl}/api/documents/backend-upload`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(`Backend upload 실패: ${response.status} - ${errorData.detail || response.statusText}`);
    }

    return response.json();
  },

  // 대용량 파일을 위한 청킹 업로드 (백엔드)
  async uploadLargeDocumentViaBackend(file: File, indexId: string, onProgress?: (progress: number) => void): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('index_id', indexId);

    const backendUrl = await getBackendUrl();
    
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable && onProgress) {
          const progress = Math.round((e.loaded / e.total) * 100);
          onProgress(progress);
        }
      });

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const response = JSON.parse(xhr.responseText);
            resolve(response);
          } catch (e) {
            reject(new Error('Failed to parse response'));
          }
        } else {
          try {
            const errorResponse = JSON.parse(xhr.responseText);
            reject(new Error(`Upload failed: ${xhr.status} - ${errorResponse.detail || xhr.statusText}`));
          } catch (e) {
            reject(new Error(`Upload failed: ${xhr.status} - ${xhr.statusText}`));
          }
        }
      };

      xhr.onerror = () => {
        reject(new Error('Network error during upload'));
      };

      xhr.open('POST', `${backendUrl}/api/documents/backend-upload-chunked`);
      xhr.send(formData);
    });
  },

  // 통일된 Presigned URL 생성 (모든 파일 크기) - project-independent
  async generateUnifiedUploadUrl(fileInfo: {
    file_name: string;
    file_size: number;
    file_type?: string;
    description?: string;
    index_id?: string;
  }, indexId?: string): Promise<{
    document_id: string;
    upload_url: string;
    completion_callback_url: string;
    file_uri: string;
    upload_method: string;
    content_type: string;
    expiration_hours: number;
  }> {
    const baseUrl = await getApiBaseUrl();
    const response = await fetch(`${baseUrl}/api/documents/upload-large`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ...fileInfo, index_id: indexId || fileInfo.index_id }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(`Unified upload URL 생성 실패: ${response.status} - ${errorData.message || response.statusText}`);
    }

    const result = await response.json();
    // Handle different response formats
    if (result.data) {
      return result.data;
    } else if (result.upload_url) {
      // Direct response format
      return result;
    } else {
      throw new Error('Invalid response format: missing upload_url');
    }
  },

  // 대용량 파일 업로드 완료 알림 (project-independent)
  async completeLargeFileUpload(documentId: string): Promise<any> {
    const baseUrl = await getApiBaseUrl();
    const response = await fetch(`${baseUrl}/api/documents/${documentId}/upload-complete`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => '');
      let errorData = {};
      try {
        errorData = JSON.parse(errorText);
      } catch (e) {
        console.log('Non-JSON error response:', errorText);
      }
      console.error('Completion callback error details:', {
        status: response.status,
        statusText: response.statusText,
        errorData,
        errorText
      });
      throw new Error(`Upload completion 실패: ${response.status} - ${(errorData as any)?.message || errorText || response.statusText}`);
    }

    const result = await response.json();
    // Handle different response formats
    if (result.data) {
      return result.data;
    } else {
      // Return the whole result if no data wrapper
      return result;
    }
  },

  // S3에 직접 파일 업로드 - CORS 문제 해결을 위해 헤더 제거
  async uploadFileToS3(uploadUrl: string, file: File, contentType: string, onProgress?: (progress: number) => void): Promise<void> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable && onProgress) {
          const progress = Math.round((e.loaded / e.total) * 100);
          onProgress(progress);
        }
      });

      xhr.onload = () => {
        console.log('S3 upload response:', {
          status: xhr.status,
          statusText: xhr.statusText,
          responseHeaders: xhr.getAllResponseHeaders(),
          responseText: xhr.responseText
        });
        
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve();
        } else {
          reject(new Error(`S3 upload failed: ${xhr.status} ${xhr.statusText} - ${xhr.responseText}`));
        }
      };

      xhr.onerror = () => {
        reject(new Error('S3 upload failed'));
      };

      xhr.open('PUT', uploadUrl);
      // DO NOT SET ANY HEADERS - S3 presigned URL already has everything
      // Setting Content-Type causes CORS preflight which fails with S3
      xhr.send(file);
    });
  }
};

// Indices API
export interface IndexItem {
  index_id: string;
  description?: string;
  owner_id?: string;
  owner_name?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
  total_documents?: number;
}

export interface IndexCreateRequest {
  index_id?: string;
  description?: string;
  owner_name?: string;
  owner_id?: string;
}

export const indicesApi = {
  async list(): Promise<IndexItem[]> {
    const baseUrl = await getApiBaseUrl();
    const url = `${baseUrl}/api/indices`;
    console.log('🔍 indicesApi.list() calling URL:', url);
    console.log('🔍 API_BASE_URL value:', baseUrl);
    const res = await fetch(url);
    console.log('🔍 fetch response URL:', res.url);
    if (!res.ok) throw new Error(`Failed to fetch indices: ${res.status}`);
    const json = await res.json();
    if (json?.success && json?.data?.items) return json.data.items as IndexItem[];
    if (Array.isArray(json?.items)) return json.items as IndexItem[];
    if (Array.isArray(json)) return json as IndexItem[];
    return [];
  },

  async create(payload: IndexCreateRequest): Promise<IndexItem> {
    const baseUrl = await getApiBaseUrl();
    const res = await fetch(`${baseUrl}/api/indices`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...payload,
        owner_id: payload.owner_id || '00001',
      }),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`Failed to create index: ${res.status} ${text}`);
    }
    const json = await res.json().catch(() => ({}));
    const item = json?.data?.item || json?.item || {};
    if (item?.index_id) return item as IndexItem;
    return {
      index_id: payload.index_id || `idx_${Date.now()}`,
      description: payload.description,
      owner_name: payload.owner_name,
      owner_id: payload.owner_id || '00001',
      status: 'creating',
      created_at: new Date().toISOString(),
    } as IndexItem;
  },

  async deepDelete(indexId: string): Promise<{ deleted: boolean } | any> {
    const baseUrl = await getApiBaseUrl();
    const res = await fetch(`${baseUrl}/api/indices/${indexId}/deep-delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`Failed to deep-delete index: ${res.status} ${text}`);
    }
    return res.json().catch(() => ({ deleted: true }));
  },
};

export const hybridSearchApi = {
  // 하이브리드 검색
  async hybridSearch(request: HybridSearchRequest): Promise<HybridSearchResponse> {
    const baseUrl = await getApiBaseUrl();
    const response = await fetch(`${baseUrl}/api/opensearch/search/hybrid`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      // 백엔드 이전 버전 호환을 위해 project_id도 함께 전송
      body: JSON.stringify({ ...request, project_id: request.index_id }),
    });
    
    if (!response.ok) {
      throw new Error('검색에 실패했습니다');
    }
    
    return response.json();
  },
};

export const systemApi = {
  // 시스템 재초기화 - 로컬 Python 백엔드로 직접 호출
  async reinitialize(request: ReinitRequest = {}): Promise<ReinitResponse> {
    const backendUrl = await getBackendUrl();
    const response = await fetch(`${backendUrl}/api/analysis/reinit`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error('재초기화에 실패했습니다');
    }

    return response.json();
  },

  // SearchAgent 재초기화
  async reinitializeSearchAgent(request: { model_id?: string } = {}): Promise<any> {
    const backendUrl = await getBackendUrl();
    const formData = new FormData();
    if (request.model_id) {
      formData.append('model_id', request.model_id);
    }
    
    const response = await fetch(`${backendUrl}/api/search/reinit`, {
      method: 'POST',
      body: formData,
    });
    
    if (!response.ok) {
      throw new Error('SearchAgent 재초기화에 실패했습니다');
    }
    
    return response.json();
  },
}; 

export const analysisAgentApi = {
  // 채팅 스트림 (FormData 또는 JSON) - Analysis Agent 호출
  async sendMessage(request: ChatRequest): Promise<Response> {
    const backendUrl = await getBackendUrl();
    const hasFiles = request.files && request.files.length > 0;

    if (hasFiles) {
      // FormData로 전송 (파일 포함)
      const formData = new FormData();
      formData.append('message', request.message);
      if (request.thread_id) {
        formData.append('thread_id', request.thread_id);
      }
      if (request.index_id) {
        formData.append('index_id', request.index_id);
      }
      if (request.document_id) {
        formData.append('document_id', request.document_id);
      }
      if (request.segment_id) {
        formData.append('segment_id', request.segment_id);
      }

      request.files!.forEach(file => {
        formData.append('files', file);
      });

      // Analysis agent 엔드포인트 사용
      return fetch(`${backendUrl}/api/analysis/chat`, {
        method: 'POST',
        body: formData,
      });
    } else {
      // JSON으로 전송
      return fetch(`${backendUrl}/api/analysis/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: request.message,
          thread_id: request.thread_id,
          index_id: request.index_id,
          document_id: request.document_id,
          segment_id: request.segment_id,
        }),
      });
    }
  },

  // Analysis agent 재초기화
  async reinitialize(model_id?: string): Promise<any> {
    const backendUrl = await getBackendUrl();

    const response = await fetch(`${backendUrl}/api/analysis/reinit`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model_id: model_id,
        reload_prompt: true
      }),
    });

    if (!response.ok) {
      throw new Error('Analysis agent 재초기화에 실패했습니다');
    }

    return response.json();
  },
};

// Pre-signed URL 생성 API
export interface PresignedUrlRequest {
  s3_uri: string;
  project_id: string;
  expiration?: number;
}

export interface PresignedUrlResponse {
  s3_uri: string;
  presigned_url: string;
  expiration_seconds: number;
  expires_at: number;
  generated_at: string;
}

export const presignedUrlApi = {
  // S3 URI로 Pre-signed URL 생성
  async getPresignedUrl(s3Uri: string, projectId: string, expiration: number = 3600): Promise<PresignedUrlResponse> {
    const baseUrl = await getApiBaseUrl();
    const response = await fetch(`${baseUrl}/api/get-presigned-url`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        s3_uri: s3Uri,
        project_id: projectId,
        expiration: expiration,
      }),
    });

    if (!response.ok) {
      throw new Error(`Pre-signed URL 생성 실패: ${response.statusText}`);
    }

    return response.json();
  },
};

// Branding API types
export interface BrandingSettings {
  companyName: string;
  logoUrl: string;
  description: string;
  version?: string;
}

export const brandingApi = {
  // 브랜딩 설정 조회
  async getSettings(): Promise<BrandingSettings> {
    const backendUrl = await getBackendUrl();
    const response = await fetch(`${backendUrl}/api/branding/settings`);
    if (!response.ok) {
      throw new Error('브랜딩 설정을 가져오는데 실패했습니다');
    }
    const result = await response.json();
    const data: BrandingSettings = result.data || result;
    // 상대 경로 로고 URL을 백엔드 절대 경로로 보정
    // 사용자 로고(API 경로)인 경우에만 백엔드 절대 경로로 보정
    if (data.logoUrl && data.logoUrl.startsWith('/api/')) {
      data.logoUrl = `${backendUrl}${data.logoUrl}`;
    }
    return data;
  },

  // 브랜딩 설정 업데이트 (FormData 지원)
  async updateSettings(formData: FormData): Promise<BrandingSettings> {
    const backendUrl = await getBackendUrl();
    const response = await fetch(`${backendUrl}/api/branding/settings`, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      throw new Error('브랜딩 설정 업데이트에 실패했습니다');
    }
    const result = await response.json();
    return result.data || result;
  },

  // 브랜딩 설정 초기화
  async resetSettings(): Promise<BrandingSettings> {
    const backendUrl = await getBackendUrl();
    const response = await fetch(`${backendUrl}/api/branding/settings`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      throw new Error('브랜딩 설정 초기화에 실패했습니다');
    }
    const result = await response.json();
    return result.data || result;
  },
};

// SearchAgent API types
export interface SearchRequest {
  message: string;
  model_id?: string;
  index_id?: string;
  document_id?: string;
  segment_id?: string;
}

// Strands SearchAgent API types
export interface StrandsSearchRequest {
  message: string;
  stream?: boolean;
  model_id?: string;
  index_id?: string;
  document_id?: string;
  segment_id?: string;
  thread_id?: string;
}

export interface SearchHealthResponse {
  search_agent: boolean;
  mcp_service: boolean;
  model: boolean;
  available_tools: number;
  timestamp: string;
  mcp_error?: string;
  model_error?: string;
}

export const searchAgentApi = {
  // SearchAgent 검색 스트림
  async searchStream(request: SearchRequest): Promise<Response> {
    const backendUrl = await getBackendUrl();
    
    // FormData로 전송
    const formData = new FormData();
    formData.append('message', request.message);
    if (request.model_id) {
      formData.append('model_id', request.model_id);
    }
    if (request.index_id) {
      formData.append('index_id', request.index_id);
    }
    if (request.document_id) {
      formData.append('document_id', request.document_id);
    }
    if (request.segment_id) {
      formData.append('segment_id', request.segment_id);
    }
    
    return fetch(`${backendUrl}/api/search`, {
      method: 'POST',
      body: formData,
    });
  },

  // SearchAgent 헬스체크
  async healthCheck(): Promise<SearchHealthResponse> {
    const backendUrl = await getBackendUrl();
    const response = await fetch(`${backendUrl}/api/search/health`);
    
    if (!response.ok) {
      throw new Error('SearchAgent 헬스체크에 실패했습니다');
    }
    
    return response.json();
  },
};

// Search API types
export interface SearchRequest {
  message: string;
  stream?: boolean;
  model_id?: string;
  index_id?: string;
  document_id?: string;
  segment_id?: string;
  thread_id?: string;
  files?: File[];
}

export interface SearchHealthResponse {
  status: string;
  agent: boolean;
  model: boolean;
  mcp_available: boolean;
  mcp_healthy: boolean;
  mcp_tools_count?: number;
  timestamp: string;
  mcp_error?: string;
}

export const searchApi = {
  // 하이브리드 검색
  async hybridSearch(request: HybridSearchRequest): Promise<HybridSearchResponse> {
    const baseUrl = await getApiBaseUrl();
    const response = await fetch(`${baseUrl}/api/opensearch/search/hybrid`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      // 백엔드 이전 버전 호환을 위해 project_id도 함께 전송
      body: JSON.stringify({ ...request, project_id: request.index_id }),
    });
    
    if (!response.ok) {
      throw new Error('검색에 실패했습니다');
    }
    
    return response.json();
  },

  // Search 채팅 스트림
  async chatStream(request: SearchRequest): Promise<Response> {
    const backendUrl = await getBackendUrl();

    // FormData로 전송
    const formData = new FormData();
    formData.append('message', request.message);
    formData.append('stream', 'true');
    if (request.model_id) {
      formData.append('model_id', request.model_id);
    }
    if (request.index_id) {
      formData.append('index_id', request.index_id);
    }
    if (request.document_id) {
      formData.append('document_id', request.document_id);
    }
    if (request.segment_id) {
      formData.append('segment_id', request.segment_id);
    }
    if (request.thread_id) {
      formData.append('thread_id', request.thread_id);
    }

    // Append files if present
    if (request.files && request.files.length > 0) {
      request.files.forEach((file) => {
        formData.append('files', file);
      });
    }

    return fetch(`${backendUrl}/api/search`, {
      method: 'POST',
      body: formData,
    });
  },

  // Search 헬스체크
  async healthCheck(): Promise<SearchHealthResponse> {
    const backendUrl = await getBackendUrl();
    const response = await fetch(`${backendUrl}/api/search/health`);
    
    if (!response.ok) {
      throw new Error('Search 헬스체크에 실패했습니다');
    }
    
    return response.json();
  },

  // ChatAgent 재초기화
  async reinitialize(model_id?: string): Promise<any> {
    const backendUrl = await getBackendUrl();
    const formData = new FormData();
    if (model_id) {
      formData.append('model_id', model_id);
    }
    
    const response = await fetch(`${backendUrl}/api/search/reinit`, {
      method: 'POST',
      body: formData,
    });
    
    if (!response.ok) {
      throw new Error('ChatAgent 재초기화에 실패했습니다');
    }
    
    return response.json();
  },
};

// Verification API types
export interface VerificationRequest {
  source_document_ids: string[];
  target_document_id: string;
  index_id?: string;
  model_id?: string;
}

export interface VerificationClaim {
  id: string;
  claim: string;
  status: "VERIFIED" | "CONTRADICTED" | "NOT_FOUND";
  evidence?: string;
  source_document_id?: string;
  confidence?: number;
  page_number?: number;
}

export interface VerificationResponse {
  success: boolean;
  claims: VerificationClaim[];
  summary: {
    total_claims: number;
    verified: number;
    contradicted: number;
    not_found: number;
  };
  message: string;
}

export const verificationApi = {
  // Content verification streaming
  async verifyContentStream(request: VerificationRequest): Promise<Response> {
    const backendUrl = await getBackendUrl();
    
    // FormData로 전송
    const formData = new FormData();
    formData.append('source_document_ids', request.source_document_ids.join(','));
    formData.append('target_document_id', request.target_document_id);
    if (request.index_id) {
      formData.append('index_id', request.index_id);
    }
    if (request.model_id) {
      formData.append('model_id', request.model_id);
    }
    
    return fetch(`${backendUrl}/api/verification/stream`, {
      method: 'POST',
      body: formData,
    });
  },

  // Content verification (non-streaming)
  async verifyContent(request: VerificationRequest): Promise<VerificationResponse> {
    const backendUrl = await getBackendUrl();
    const response = await fetch(`${backendUrl}/api/verification`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });
    
    if (!response.ok) {
      throw new Error('Content verification failed');
    }
    
    return response.json();
  },

  // Verification health check
  async healthCheck(): Promise<any> {
    const backendUrl = await getBackendUrl();
    const response = await fetch(`${backendUrl}/api/verification/health`);
    
    if (!response.ok) {
      throw new Error('Verification health check failed');
    }
    
    return response.json();
  },
};

// Strands Search Agent API - Enhanced for AgentsAsToolsSearchAgent
export const strandsSearchApi = {
  // Strands Search 스트리밍 (AgentsAsToolsSearchAgent)
  async searchStream(request: StrandsSearchRequest): Promise<Response> {
    const backendUrl = await getBackendUrl();
    
    // FormData로 전송 - AgentsAsToolsSearchAgent 전용 엔드포인트
    const formData = new FormData();
    formData.append('message', request.message);
    formData.append('stream', 'true');
    if (request.model_id) {
      formData.append('model_id', request.model_id);
    }
    if (request.index_id) {
      formData.append('index_id', request.index_id);
    }
    if (request.document_id) {
      formData.append('document_id', request.document_id);
    }
    if (request.segment_id) {
      formData.append('segment_id', request.segment_id);
    }
    if (request.thread_id) {
      formData.append('thread_id', request.thread_id);
    }
    
    return fetch(`${backendUrl}/api/strands-search/chat`, {
      method: 'POST',
      body: formData,
    });
  },

  // Strands Search 논스트리밍 (AgentsAsToolsSearchAgent)
  async search(request: StrandsSearchRequest): Promise<any> {
    const backendUrl = await getBackendUrl();
    
    // FormData for non-streaming as well to maintain consistency
    const formData = new FormData();
    formData.append('message', request.message);
    formData.append('stream', 'false');
    if (request.model_id) {
      formData.append('model_id', request.model_id);
    }
    if (request.index_id) {
      formData.append('index_id', request.index_id);
    }
    if (request.document_id) {
      formData.append('document_id', request.document_id);
    }
    if (request.segment_id) {
      formData.append('segment_id', request.segment_id);
    }
    if (request.thread_id) {
      formData.append('thread_id', request.thread_id);
    }
    
    const response = await fetch(`${backendUrl}/api/strands-search/chat`, {
      method: 'POST',
      body: formData,
    });
    
    if (!response.ok) {
      throw new Error('Strands search failed');
    }
    
    return response.json();
  },

  // Strands Search 헬스체크 (AgentsAsToolsSearchAgent)
  async healthCheck(): Promise<any> {
    const backendUrl = await getBackendUrl();
    const response = await fetch(`${backendUrl}/api/strands-search/health`);
    
    if (!response.ok) {
      throw new Error('Strands search health check failed');
    }
    
    return response.json();
  },

  // Strands Search 시스템 재초기화 (AgentsAsToolsSearchAgent)
  async reinitialize(model_id?: string): Promise<any> {
    const backendUrl = await getBackendUrl();
    const formData = new FormData();
    if (model_id) {
      formData.append('model_id', model_id);
    }

    const response = await fetch(`${backendUrl}/api/strands-search/reinit`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error('Strands search system 재초기화에 실패했습니다');
    }

    return response.json();
  },
};

// Users API (RBAC)
export interface UserPermissions {
  can_create_index: boolean;
  can_delete_index: boolean;
  can_upload_documents: boolean;
  can_delete_documents: boolean;
  accessible_indexes: string[] | "*";
  available_tabs: string[];
}

export interface UserData {
  user_id: string;
  email: string;
  name?: string;
  role: "admin" | "user";
  permissions: UserPermissions;
  status: string;
  created_at?: string;
  updated_at?: string;
  last_login_at?: string;
}

export const usersApi = {
  // 현재 사용자 정보 조회
  async getCurrentUser(): Promise<UserData> {
    // Step 1: Get user info from ALB (via backend FastAPI)
    const backendUrl = await getBackendUrl();
    const authResponse = await fetch(`${backendUrl}/api/auth/user`, {
      credentials: 'include', // Include ALB Cognito cookies
    });

    if (!authResponse.ok) {
      throw new Error('Failed to get user from auth endpoint');
    }

    const authUser = await authResponse.json();
    console.log('Auth user from ALB:', authUser);

    // Step 2: Call user management API with user info as parameters
    const apiBaseUrl = await getApiBaseUrl();
    const params = new URLSearchParams({
      user_id: authUser.email, // Use email as user_id
      email: authUser.email,
      name: authUser.name || '',
      groups: authUser.groups?.join(',') || '',
    });

    const response = await fetch(`${apiBaseUrl}/api/users/me?${params}`);
    if (!response.ok) {
      throw new Error('Failed to fetch current user permissions');
    }
    return response.json();
  },

  // 모든 사용자 조회 (admin only)
  async listUsers(): Promise<UserData[]> {
    const apiBaseUrl = await getApiBaseUrl();
    const response = await fetch(`${apiBaseUrl}/api/users`);
    if (!response.ok) {
      throw new Error('Failed to fetch users');
    }
    return response.json();
  },

  // 사용자 권한 업데이트 (admin only)
  async updatePermissions(userId: string, permissions: UserPermissions, role?: string): Promise<void> {
    const apiBaseUrl = await getApiBaseUrl();
    const response = await fetch(`${apiBaseUrl}/api/users/${userId}/permissions`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ permissions, role }),
    });
    if (!response.ok) {
      throw new Error('Failed to update permissions');
    }
  },

  // 사용자 상태 업데이트 (admin only)
  async updateStatus(userId: string, status: string): Promise<void> {
    const apiBaseUrl = await getApiBaseUrl();
    const response = await fetch(`${apiBaseUrl}/api/users/${userId}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    if (!response.ok) {
      throw new Error('Failed to update status');
    }
  },
};