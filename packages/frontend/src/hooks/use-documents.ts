import { useState, useCallback, useEffect } from "react";
import { useDocumentUpdates } from "@/contexts/websocket-context";
import { documentApi } from "@/lib/api";
import { Document } from "@/types/document.types";

export interface UseDocumentsReturn {
    documents: Document[];
    loading: boolean;
    error: string | null;
    fetchDocuments: (showLoading?: boolean) => Promise<void>;
    deleteDocument: (documentId: string, indexId?: string) => Promise<void>;
}

export const useDocuments = (indexId: string): UseDocumentsReturn => {
    const [documents, setDocuments] = useState<Document[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    
    // WebSocket을 통한 실시간 문서 업데이트 구독
    const subscribeToDocumentUpdates = useDocumentUpdates();

    // 문서 목록 조회 (index-based)
    const fetchDocuments = useCallback(async (showLoading = true) => {
        try {
            console.log('Document list fetch started (index-based)');
            if (showLoading) {
                setLoading(true);
            }
            setError(null);
            
            if (!indexId) {
                throw new Error('indexId is required');
            }
            
            const responseData = await documentApi.getDocuments(true, false, indexId); // simple=true, segments=false
            console.log('Document list fetch success:', responseData);
            
            // API 응답 구조에 맞게 데이터 추출
            if (responseData.documents) {
                setDocuments(responseData.documents as Document[]);
            } else {
                setDocuments([]);
            }
        } catch (error) {
            console.error('Document list fetch error:', error);
            const errorMessage = error instanceof Error ? error.message : 'Unknown error';
            setError(errorMessage);
            if (showLoading) {
                throw error; // 상위에서 에러 처리하도록 throw
            }
        } finally {
            if (showLoading) {
                setLoading(false);
            }
        }
    }, [indexId]);

    // 문서 삭제 (index-based)
    const deleteDocument = useCallback(async (documentId: string, targetIndexId?: string) => {
        if (!documentId) return;

        try {
            // indexId 우선순위: 파라미터 > 훅 인자
            const actualIndexId = targetIndexId || indexId;
            if (!actualIndexId) {
                throw new Error('indexId is required for document deletion');
            }
            
            await documentApi.deleteDocument(documentId, actualIndexId);

            // 목록에서 제거
            setDocuments(prev => prev.filter(doc => doc.document_id !== documentId));
        } catch (error) {
            console.error('Document delete error:', error);
            throw error; // 상위에서 에러 처리하도록 throw
        }
    }, [indexId]);

    // WebSocket 실시간 업데이트 구독
    useEffect(() => {
        const unsubscribe = subscribeToDocumentUpdates((update, event) => {
            console.log('Document update received, refreshing document list:', { update, event });
            
            // WebSocket 업데이트 시 API 호출로 최신 데이터 가져오기
            fetchDocuments(false); // 백그라운드에서 갱신
        });
        
        return unsubscribe;
    }, [subscribeToDocumentUpdates, fetchDocuments]);

    // 초기 문서 목록 조회 (index-based)
    useEffect(() => {
        if (indexId) {
            fetchDocuments();
        }
    }, [fetchDocuments, indexId]);

    return {
        documents,
        loading,
        error,
        fetchDocuments,
        deleteDocument
    };
}; 