import { useState, useCallback, useMemo, useEffect, useRef } from "react";
import { documentApi } from "@/lib/api";
import { Document, AnalysisDocument } from "@/types/document.types";

interface PageAnalysis {
    page_id: string;
    page_index: number;
    index_id: string;
    document_id: string;
    page_uri: string;
    file_uri: string;
    content_combined: string;
    vector_content_available: boolean;
    tools_detail: {
        [toolName: string]: Array<{
            content: string;
            analysis_query: string;
            metadata?: {
                analysis_steps: string;
                model_version: string;
            };
            created_at: string;
        }>;
    };
    tools_count: {
        [toolName: string]: number;
    };
    created_at: string;
    updated_at: string;
    _opensearch_doc_id: string;
    _score: number | null;
}

interface NewAnalysisResponse {
    success: boolean;
    data: {
        index_id: string;
        document_id: string;
        total_pages: number;
        returned_pages: number;
        pages: PageAnalysis[];
        query_params: {
            size: number;
        };
        timestamp: string;
    };
}

export interface UseDocumentDetailReturn {
    // Detail view state
    selectedDocument: Document | null;
    showDetail: boolean;
    
    // Segment navigation
    selectedSegment: number;
    selectedSegmentId: string | null;
    setSelectedSegment: (segmentIndex: number) => void;
    
    // Image viewer state
    imageZoom: number;
    imageRotation: number;
    imageLoading: boolean;
    imagePosition: { x: number; y: number };
    isDragging: boolean;
    currentPageImageUrl: string | null; // 현재 선택된 페이지의 이미지 URL 직접 제공
    
    // Analysis data
    analysisData: AnalysisDocument[];
    analysisLoading: boolean;
    expandedAnalysis: Record<string, boolean>;
    // Segment timecodes
    segmentStartTimecodes: string[];
    
    // PDF viewer
    showPdfViewer: boolean;
    setShowPdfViewer: (show: boolean) => void;
    
    // Actions
    viewDocument: (document: Document, updateExternalDocument?: (updates: any) => void, initialSegment?: number) => void;
    closeDetail: () => void;
    handleSegmentChange: (newSegmentIndex: number) => void;
    
    // Image viewer actions
    zoomIn: () => void;
    zoomOut: () => void;
    resetZoom: () => void;
    rotateLeft: () => void;
    rotateRight: () => void;
    resetImage: () => void;
    handleMouseDown: (e: React.MouseEvent) => void;
    handleMouseMove: (e: React.MouseEvent) => void;
    handleMouseUp: () => void;
    
    // Analysis actions
    toggleAnalysisExpand: (analysisId: string) => void;
    handleAnalysisPopup: (popup: { type: 'bda' | 'pdf' | 'ai' | null; isOpen: boolean }) => void;
    
    // Utility functions
    getPageImageUrl: (document: Document, pageNumber: number) => string | null;
    formatDate: (dateString: string) => string;
    formatDocumentFileSize: (bytes: string | undefined) => string;
}

export const useDocumentDetail = (indexId: string, externalSelectedDocument?: Document | null, externalSelectedSegment?: number): UseDocumentDetailReturn => {
    
    // Detail view state
    const [selectedDocument, setSelectedDocument] = useState<Document | null>(null);
    const [showDetail, setShowDetail] = useState(false);
    
    // Segment navigation
    const [selectedSegment, setSelectedSegment] = useState<number>(0);
    
    // Image viewer state
    const [imageZoom, setImageZoom] = useState<number>(1);
    const [imageRotation, setImageRotation] = useState<number>(0);
    const [imageLoading, setImageLoading] = useState<boolean>(false);
    const [imagePosition, setImagePosition] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
    const [isDragging, setIsDragging] = useState<boolean>(false);
    const [dragStart, setDragStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
    
    // Analysis data
    const [analysisData, setAnalysisData] = useState<AnalysisDocument[]>([]);
    const [segmentStartTimecodes, setSegmentStartTimecodes] = useState<string[]>([]);
    const [analysisLoading, setAnalysisLoading] = useState<boolean>(false);
    const [expandedAnalysis, setExpandedAnalysis] = useState<Record<string, boolean>>({});
    
    // PDF viewer
    const [showPdfViewer, setShowPdfViewer] = useState(false);

    // Retry/polling state for analysis data fetching
    const retryCountRef = useRef(0);
    const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const fetchAnalysisDataRef = useRef<((docId: string, updateExternalDocument?: (updates: any) => void) => Promise<void>) | null>(null);

    const clearRetryTimer = useCallback(() => {
        if (retryTimerRef.current) {
            clearTimeout(retryTimerRef.current);
            retryTimerRef.current = null;
        }
    }, []);

    const scheduleRetry = useCallback((docId: string): void => {
        const maxRetries = 20; // ~ progressively up to ~90s total with backoff
        if (retryCountRef.current >= maxRetries) {
            console.warn('⛔ Reached max analysis re-fetch attempts');
            return;
        }
        retryCountRef.current += 1;
        // Exponential backoff with cap: 1500ms * (2^n), max 10s
        const base = 1500;
        const delay = Math.min(base * Math.pow(2, Math.max(0, retryCountRef.current - 1)), 10000);
        console.log(`⏳ Scheduling analysis re-fetch attempt ${retryCountRef.current} in ${delay}ms (docId=${docId})`);
        clearRetryTimer();
        retryTimerRef.current = setTimeout(() => {
            if (fetchAnalysisDataRef.current) {
                fetchAnalysisDataRef.current(docId).catch(() => {});
            }
        }, delay);
    }, [clearRetryTimer]);

    // Use external state if provided, otherwise use internal state
    const effectiveSelectedDocument = externalSelectedDocument || selectedDocument;
    const effectiveSelectedSegment = externalSelectedSegment ?? selectedSegment;

    // Calculate selectedSegmentId based on analysisData
    const selectedSegmentId = useMemo(() => {
        if (Array.isArray(analysisData) && analysisData.length > 0) {
            const match = analysisData.find(item => {
                const segmentIdx = (typeof item.segment_index === 'number' ? item.segment_index : undefined) ??
                                (typeof item.page_index === 'number' ? item.page_index : undefined);
                return segmentIdx === effectiveSelectedSegment;
            });
            return match?.segment_id || null;
        }
        return null;
    }, [analysisData, effectiveSelectedSegment]);

    // 현재 선택된 세그먼트의 이미지 URL을 계산 (이미 로드된 것을 재사용)
    const currentPageImageUrl = useMemo(() => {
        // console.log('🖼️ [useDocumentDetail] Calculating currentSegmentImageUrl:', {
        //     selectedSegment: effectiveSelectedSegment,
        //     hasPageImages: !!effectiveSelectedDocument?.page_images,
        //     pageImagesLength: effectiveSelectedDocument?.page_images?.length,
        //     pageImages: effectiveSelectedDocument?.page_images,
        //     analysisDataLength: analysisData?.length,
        // });

        // 1) Try from selectedDocument.page_images (for backward compatibility with page-based documents)
        if (effectiveSelectedDocument?.page_images && effectiveSelectedDocument.page_images.length > 0) {
            const pageImage = effectiveSelectedDocument.page_images.find(img => {
                const imgPageNum = typeof img.page_number === 'string' ? parseInt(img.page_number) : img.page_number;
                return imgPageNum === effectiveSelectedSegment + 1; // Convert 0-based segment to 1-based page
            });
            if (pageImage) {
                const finalUrl = pageImage.image_uri || pageImage.image_url || pageImage.file_uri || pageImage.image_file_uri || null;
                // console.log('🖼️ [useDocumentDetail] Final currentSegmentImageUrl(from page_images):', finalUrl);
                return finalUrl;
            }
        }

        // 2) Fallback: derive from analysisData (segment based)
        if (Array.isArray(analysisData) && analysisData.length > 0) {
            const match = analysisData.find(item => {
                const segmentIdx = (typeof item.segment_index === 'number' ? item.segment_index : undefined) ??
                                (typeof item.page_index === 'number' ? item.page_index : undefined);
                return segmentIdx === effectiveSelectedSegment;
            });
            if (match) {
                const finalUrl = (match as any).image_file_uri || (match as any).image_path || match.file_uri || null;
                // console.log('🖼️ [useDocumentDetail] Final currentSegmentImageUrl(from analysisData):', finalUrl);
                return finalUrl;
            }
        }

        // console.log('🖼️ [useDocumentDetail] No matching image found for segment:', effectiveSelectedSegment);
        return null;
    }, [effectiveSelectedDocument?.page_images, effectiveSelectedSegment, analysisData]);

    // 페이지 이미지 URL 생성 함수
    const getPageImageUrl = useCallback((document: Document, pageNumber: number) => {
        if (document.page_images && document.page_images.length > 0) {
            const pageImage = document.page_images.find(img => {
                const imgPageNum = typeof img.page_number === 'string' ? parseInt(img.page_number) : img.page_number;
                return imgPageNum === pageNumber;
            });
            
            if (pageImage) {
                return pageImage.image_url || pageImage.file_uri || pageImage.image_file_uri || null;
            }
        }
        
        return null;
    }, []);

    // 분석 데이터 조회 - external callback for updating external document state
    const [externalUpdateCallback, setExternalUpdateCallback] = useState<((updates: any) => void) | null>(null);

    // 분석 데이터 조회
    const fetchAnalysisData = useCallback(async (docId: string, updateExternalDocument?: (updates: any) => void) => {
        // Store the callback for later use
        if (updateExternalDocument) {
            setExternalUpdateCallback(() => updateExternalDocument);
        }

        if (!indexId) {
            console.error('indexId is required for fetching analysis data');
            return;
        }
        
        // console.log('🔍 [useDocumentDetail] fetchAnalysisData started:', {
        //     indexId,
        //     docId,
        //     timestamp: new Date().toISOString()
        // });

        try {
            setAnalysisLoading(true);
            const data = await documentApi.getDocumentDetail(docId, indexId);
            // console.log('Document detail fetch success:', data);
            // console.log('API response structure check (segments expected):', {
            //     hasSegments: !!(data?.segments),
            //     segmentCount: (data?.segments || []).length,
            // });

            // 새 segment 기반 구조로 변환
            const convertedAnalysisData: AnalysisDocument[] = [];
            const segments = data?.segments || [];

            // console.log('🔍 [DEBUG] Segments data from API:', segments);
            // console.log('🔍 [DEBUG] First segment status:', segments?.[0]?.status);

            if (Array.isArray(segments)) {
                // Extract start_timecode_smpte list for seeking
                try {
                    const startCodes = segments
                        .sort((a: any, b: any) => (a.segment_index ?? 0) - (b.segment_index ?? 0))
                        .map((s: any) => (s?.start_timecode_smpte ?? ''));
                    setSegmentStartTimecodes(startCodes);
                } catch {
                    setSegmentStartTimecodes([]);
                }

                // 기본 segment 정보만으로 분석 데이터 생성 (상세 분석은 개별 조회시 처리)
                segments.forEach((segment: any) => {
                    convertedAnalysisData.push({
                        opensearch_doc_id: segment.segment_id || `segment_${segment.segment_index}`,
                        score: null,
                        index_id: segment.index_id || indexId,
                        document_id: segment.document_id || docId,
                        segment_id: segment.segment_id,
                        segment_index: segment.segment_index,
                        page_number: typeof segment.segment_index === 'number' ? segment.segment_index + 1 : undefined,
                        page_index: segment.segment_index,
                        tool_name: 'segment_info',
                        content: `Segment ${typeof segment.segment_index === 'number' ? segment.segment_index + 1 : ''} - Status: ${segment.status || 'pending'}`,
                        analysis_query: '세그먼트 기본 정보',
                        vector_dimensions: 0,
                        file_uri: segment.file_uri || '',
                        file_path: segment.file_uri || '',
                        image_file_uri: segment.image_uri || '',
                        image_path: segment.image_uri || '',
                        execution_time: null,
                        created_at: segment.created_at,
                        data_structure: 'segment_unit',
                    } as any);
                });
            }

            // console.log('Converted analysis data (segments):', convertedAnalysisData);
            setAnalysisData(convertedAnalysisData);

            // Auto polling if no analysis data yet
            if (!Array.isArray(segments) || segments.length === 0) {
                scheduleRetry(docId);
            } else {
                // Data available, reset retry state
                retryCountRef.current = 0;
                clearRetryTimer();
            }

            // Update document with API response data
            if (data) {
                const updatedDocumentFields = {
                    file_size: data.file_size,
                    file_name: data.file_name,
                    file_type: data.file_type,
                    status: data.status,
                    processing_status: data.processing_status,
                    created_at: data.created_at,
                    updated_at: data.updated_at,
                    total_pages: data.total_pages,
                    summary: data.summary,
                    description: data.description,
                    file_uri: data.file_uri,
                    download_url: data.file_presigned_url || data.download_url,
                };

                // console.log('📝 [useDocumentDetail] Updating document with API data:', {
                //     file_size: updatedDocumentFields.file_size,
                //     file_name: updatedDocumentFields.file_name,
                //     selectedDocument: selectedDocument?.document_id,
                // });

                // Always update internal document state (even if selectedDocument is still null from timing)
                setSelectedDocument(prev => prev ? { ...prev, ...updatedDocumentFields } : prev);

                // Update external document state if callback is provided
                if (updateExternalDocument && externalSelectedDocument) {
                    updateExternalDocument({
                        selectedDocument: { ...externalSelectedDocument, ...updatedDocumentFields }
                    });
                }
            }

            // Update page images for both internal and external document state
            if (Array.isArray(segments)) {
                const pageImages = segments.map((segment: any) => ({
                    page_number: typeof segment.segment_index === 'number' ? segment.segment_index + 1 : 1,
                    page_index: segment.segment_index,
                    image_uri: segment.image_uri,
                    image_url: segment.image_uri,
                    file_uri: segment.file_uri,
                    image_file_uri: segment.image_uri,
                    page_status: segment.status,
                }));

                // console.log('🔍 [DEBUG] Raw segments from API:', segments.slice(0, 3).map(s => ({
                //     segment_index: s.segment_index,
                //     status: s.status
                // })));
                // console.log('🔍 [DEBUG] Generated pageImages with status:', pageImages.slice(0, 3).map(p => ({
                //     page_index: p.page_index,
                //     page_status: p.page_status
                // })));

                // Update internal document state with page images
                if (selectedDocument) {
                    setSelectedDocument(prev => prev ? { ...prev, page_images: pageImages } : prev);
                }

                // Update external document state with page images if callback is provided
                if (updateExternalDocument && externalSelectedDocument) {
                    updateExternalDocument({
                        selectedDocument: { ...externalSelectedDocument, page_images: pageImages }
                    });
                }
            }
        } catch (error) {
            console.error('❌ [useDocumentDetail] Analysis data fetch error:', error);
            console.error('❌ Error details:', {
                message: error instanceof Error ? error.message : String(error),
                stack: error instanceof Error ? error.stack : undefined,
                docId,
                indexId
            });
            setAnalysisData([]);
            // Retry on transient errors
            scheduleRetry(docId);
        } finally {
            setAnalysisLoading(false);
        }
    }, [indexId, selectedDocument, externalSelectedDocument, scheduleRetry]);

    // keep ref updated to break circular dependency with scheduleRetry
    useEffect(() => {
        fetchAnalysisDataRef.current = fetchAnalysisData;
        return () => {
            if (fetchAnalysisDataRef.current === fetchAnalysisData) {
                fetchAnalysisDataRef.current = null;
            }
        };
    }, [fetchAnalysisData]);

    // 문서 상세 보기 - accepts external update callback and optional initial segment
    const viewDocument = useCallback((document: Document, updateExternalDocument?: (updates: any) => void, initialSegment?: number) => {
        const currentDocId = effectiveSelectedDocument?.document_id;
        const documentId = document.document_id;

        if (currentDocId === documentId && showDetail) {
            // 같은 문서의 상세 보기를 다시 클릭하면 닫기
            setShowDetail(false);
            setSelectedDocument(null);
            setAnalysisData([]);
            if (updateExternalDocument) {
                updateExternalDocument({ selectedDocument: null });
            }
        } else {
            // 새 문서 선택 또는 상세 보기 열기
            const targetSegment = initialSegment ?? 0;
            setSelectedDocument(document);
            setShowDetail(true);
            setSelectedSegment(targetSegment); // Use provided segment or default to 0
            setImageZoom(1); // 확대/축소 초기화
            setImagePosition({ x: 0, y: 0 }); // 이미지 위치 초기화
            // reset polling for new document
            retryCountRef.current = 0;
            clearRetryTimer();

            // Update external state if callback provided
            if (updateExternalDocument) {
                updateExternalDocument({
                    selectedDocument: document,
                    selectedSegment: targetSegment,
                    imageZoom: 1,
                    imageRotation: 0,
                    imagePosition: { x: 0, y: 0 }
                });
            }

            // 분석 데이터 조회 (getDocumentDetail이 segment 정보도 함께 반환)
            if (documentId) {
                fetchAnalysisData(documentId, updateExternalDocument);
            }
        }
    }, [effectiveSelectedDocument?.document_id, showDetail, fetchAnalysisData, clearRetryTimer]);

    // 상세 보기 닫기
    const closeDetail = useCallback(() => {
        setShowDetail(false);
        setSelectedDocument(null);
        setAnalysisData([]);
        retryCountRef.current = 0;
        clearRetryTimer();
    }, []);

    // 세그먼트 변경 시 로딩 상태와 확대/축소 초기화
    const handleSegmentChange = useCallback((newSegmentIndex: number) => {
        setImageLoading(true);
        setSelectedSegment(newSegmentIndex);
        setImageZoom(1); // 세그먼트 변경시 확대/축소 초기화
        setImagePosition({ x: 0, y: 0 }); // 이미지 위치 초기화
        setExpandedAnalysis({}); // 분석 결과 접기 상태 초기화
        
        // 이미지 로딩 완료를 기다린 후 로딩 상태 해제
        setTimeout(() => {
            setImageLoading(false);
        }, 500); // 500ms 후 로딩 해제
    }, []);

    // 확대/축소 제어
    const handleZoomIn = useCallback(() => {
        setImageZoom(prev => Math.min(prev + 0.25, 3)); // 최대 3배
    }, []);

    const handleZoomOut = useCallback(() => {
        setImageZoom(prev => Math.max(prev - 0.25, 0.25)); // 최소 0.25배
    }, []);

    const handleZoomReset = useCallback(() => {
        setImageZoom(1);
        setImagePosition({ x: 0, y: 0 }); // 이미지 위치도 초기화
    }, []);

    // 이미지 회전 함수들
    const rotateLeft = useCallback(() => {
        setImageRotation(prev => prev - 90);
        console.log('🔄 Rotate left - new rotation:', imageRotation - 90);
    }, [imageRotation]);

    const rotateRight = useCallback(() => {
        setImageRotation(prev => prev + 90);
        console.log('🔄 Rotate right - new rotation:', imageRotation + 90);
    }, [imageRotation]);

    const resetImage = useCallback(() => {
        setImageZoom(1);
        setImageRotation(0);
        setImagePosition({ x: 0, y: 0 });
        console.log('🔄 Reset image - zoom: 1, rotation: 0, position: {x: 0, y: 0}');
    }, []);

    // 분석 팝업 핸들러
    const handleAnalysisPopup = useCallback((popup: { type: 'bda' | 'pdf' | 'ai' | null; isOpen: boolean }) => {
        console.log('📊 Analysis popup handler called:', popup);
        // TODO: 실제 분석 팝업 로직 구현 필요
        if (popup.isOpen && popup.type) {
            alert(`${popup.type.toUpperCase()} 분석 결과를 표시합니다.`);
        }
    }, []);

    // 분석 결과 접기/펼치기
    const toggleAnalysisExpand = useCallback((analysisId: string) => {
        setExpandedAnalysis(prev => ({
            ...prev,
            [analysisId]: !prev[analysisId]
        }));
    }, []);

    // 드래그 시작
    const handleMouseDown = useCallback((e: React.MouseEvent) => {
        if (imageZoom > 1) { // 확대된 상태에서만 드래그 가능
            setIsDragging(true);
            setDragStart({ 
                x: e.clientX - imagePosition.x, 
                y: e.clientY - imagePosition.y 
            });
            e.preventDefault();
        }
    }, [imageZoom, imagePosition]);

    // 드래그 중
    const handleMouseMove = useCallback((e: React.MouseEvent) => {
        if (isDragging && imageZoom > 1) {
            e.preventDefault();
            
            // Calculate movement delta with sensitivity reduction
            const sensitivity = 0.5; // Reduce movement sensitivity
            const deltaX = (e.clientX - dragStart.x) * sensitivity;
            const deltaY = (e.clientY - dragStart.y) * sensitivity;
            
            // Convert rotation to radians and adjust for drag direction
            const rotationRad = (imageRotation * Math.PI) / 180;
            
            // Apply inverse rotation to drag vector
            const adjustedX = deltaX * Math.cos(-rotationRad) - deltaY * Math.sin(-rotationRad);
            const adjustedY = deltaX * Math.sin(-rotationRad) + deltaY * Math.cos(-rotationRad);
            
            setImagePosition({
                x: adjustedX,
                y: adjustedY
            });
        }
    }, [isDragging, imageZoom, dragStart, imageRotation]);

    // 드래그 종료
    const handleMouseUp = useCallback(() => {
        setIsDragging(false);
    }, []);

    // Clear retry timer on unmount or when selected document changes
    useEffect(() => {
        return () => {
            clearRetryTimer();
        };
    }, [clearRetryTimer]);

    // 날짜 포맷팅
    const formatDate = useCallback((dateString: string) => {
        return new Date(dateString).toLocaleString('ko-KR');
    }, []);

    // 파일 크기 포맷팅 (string용)
    const formatDocumentFileSize = useCallback((bytes: string | undefined) => {
        if (!bytes) return '-';
        const size = parseInt(bytes);
        if (size === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(size) / Math.log(k));
        return parseFloat((size / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }, []);

    return {
        // Detail view state
        selectedDocument,
        showDetail,
        
        // Segment navigation
        selectedSegment,
        selectedSegmentId,
        setSelectedSegment,
        
        // Image viewer state
        imageZoom,
        imageRotation,
        imageLoading,
        imagePosition,
        isDragging,
        currentPageImageUrl, // 현재 페이지의 이미지 URL 직접 제공
        
        // Analysis data
        analysisData,
        analysisLoading,
        expandedAnalysis,
        segmentStartTimecodes,
        
        // PDF viewer
        showPdfViewer,
        setShowPdfViewer,
        
        // Actions
        viewDocument,
        closeDetail,
        handleSegmentChange,
        
        // Image viewer actions
        zoomIn: handleZoomIn,
        zoomOut: handleZoomOut,
        resetZoom: handleZoomReset,
        rotateLeft,
        rotateRight,
        resetImage,
        handleMouseDown,
        handleMouseMove,
        handleMouseUp,
        
        // Analysis actions
        toggleAnalysisExpand,
        handleAnalysisPopup,
        
        // Utility functions
        getPageImageUrl,
        formatDate,
        formatDocumentFileSize
    };
}; 