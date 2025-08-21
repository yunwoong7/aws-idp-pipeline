"use client";

import React, { useState, useCallback, useEffect } from "react";
import { FileText } from "lucide-react";
import { DocumentsPageHeader } from "./components/documents-page-header";
import { DocumentList } from "./components/document-list";
import { DocumentLoadingState } from "./components/document-loading-state";
import { UploadZone } from "./components/upload-zone";
import { DocumentDetailDialog } from "./components/document-detail-dialog";
import { PdfViewerDialog } from "@/components/ui/pdf-viewer-dialog";
import { useDocuments } from "@/hooks/use-documents";
import { useDocumentUpload } from "@/hooks/use-document-upload";
import { useDocumentDetail } from "@/hooks/use-document-detail";
import { Document } from "@/types/document.types";
import { searchApi } from "@/lib/api";
import { UploadNotificationContainer } from "@/components/ui/upload-notification";
import { useUploadNotifications } from "@/hooks/use-upload-notifications";
import { useWebSocket, WebSocketMessage } from "@/hooks/use-websocket";

interface DocumentsTabProps {
  indexId: string;
  onSelectDocument?: (fileName: string, documentId: string) => void;
  onAttachToChat?: (pageInfo: {
    document_id: string;
    page_index: number;
    page_number: number;
    file_name: string;
  }) => void;
  onAnalyzeDocument?: (document: Document) => void;
}

export function DocumentsTab({ indexId, onSelectDocument, onAttachToChat, onAnalyzeDocument }: DocumentsTabProps) {
  const { 
    documents, 
    loading, 
    error,
    fetchDocuments, 
    deleteDocument 
  } = useDocuments(indexId);

  // Upload notification management
  const { notifications, removeNotification } = useUploadNotifications({
    maxNotifications: 3,
    autoRemove: true,
    autoRemoveDelay: 6000
  });

  const {
    showUploadZone,
    setShowUploadZone,
    uploadFiles,
    isUploading,
    getRootProps,
    getInputProps,
    isDragActive,
    startUpload,
    removeFile,
    formatFileSize
  } = useDocumentUpload({ 
    onUploadComplete: () => {
      // 업로드 완료 시 문서 목록 갱신 후 업로드 영역 닫기
      fetchDocuments();
      setShowUploadZone(false);
    },
    indexId
  });

  const {
    selectedDocument,
    showDetail,
    analysisData,
    analysisLoading,
    expandedAnalysis,
    showPdfViewer,
    setShowPdfViewer,
    imageLoading,
    selectedSegment,
    imageZoom,
    imageRotation,
    imagePosition,
    isDragging,
    currentPageImageUrl,
    viewDocument,
    closeDetail,
    handleSegmentChange,
    zoomIn,
    zoomOut,
    resetZoom,
    rotateLeft,
    rotateRight,
    resetImage,
    handleMouseDown,
    handleMouseMove,
    handleMouseUp,
    toggleAnalysisExpand,
    handleAnalysisPopup
  } = useDocumentDetail(indexId);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [filteredDocuments, setFilteredDocuments] = useState<Document[]>([]);
  const [searchResults, setSearchResults] = useState<any[]>([]);

  // WebSocket message handler
  const handleWebSocketMessage = useCallback((message: WebSocketMessage) => {
    console.log('WebSocket message received in documents-tab:', message);
    
    switch (message.type) {
      case 'real_time_update':
        if (message.table === 'documents') {
          if (message.event === 'insert') {
            // 새 문서가 추가된 경우
            console.log('New document added:', message.data);
            // 문서 목록 새로고침
            fetchDocuments();
          } else if (message.event === 'modify') {
            // 문서가 수정된 경우 (상태 변경, 분석 완료 등)
            console.log('Document updated:', message.data);
            // 문서 목록 새로고침
            fetchDocuments();
          } else if (message.event === 'remove') {
            // 문서가 삭제된 경우
            console.log('Document removed:', message.data);
            // 문서 목록 새로고침
            fetchDocuments();
          }
        }
        break;
        
      case 'upload_completion':
        // 업로드 완료 알림
        if (message.document_id && message.file_name) {
          console.log('Upload completed:', message.file_name);
          // 문서 목록 새로고침
          fetchDocuments();
        }
        break;
        
      default:
        // 다른 메시지 타입들은 무시
        break;
    }
  }, [fetchDocuments]);

  // WebSocket 연결 (비활성화)
  const {
    isConnected: wsConnected,
    isConnecting: wsConnecting,
    error: wsError,
    lastMessage: wsLastMessage,
    reconnectAttempts: wsReconnectAttempts
  } = useWebSocket({
    indexId,
    autoConnect: true,
    enabled: false, // 웹소켓 비활성화
    onMessage: handleWebSocketMessage,
    onConnect: () => {
      console.log('WebSocket connected in documents-tab');
    },
    onDisconnect: () => {
      console.log('WebSocket disconnected in documents-tab');
    },
    onError: (error) => {
      console.warn('WebSocket error in documents-tab:', error);
    }
  });

  // Search execution function
  const executeSearch = useCallback(async () => {
    if (!searchQuery.trim()) {
      setFilteredDocuments(documents);
      setSearchResults([]);
      return;
    }

    setIsSearching(true);
    try {
      const searchData = await searchApi.hybridSearch({
        index_id: indexId || 'default',
        query: searchQuery,
        size: 100,
      });

      if (searchData.success && searchData.data.results) {
        const sortedResults = searchData.data.results.sort((a: any, b: any) => {
          const scoreA = a._score || a.score || 0;
          const scoreB = b._score || b.score || 0;
          return scoreB - scoreA;
        });
        
        setSearchResults(sortedResults);
        
        const foundDocumentIds = new Set(
          sortedResults.map((result: any) => result.document_id)
        );

        const documentScores = new Map<string, number>();
        sortedResults.forEach((result: any) => {
          const score = result._score || result.score || 0;
          const currentMaxScore = documentScores.get(result.document_id) || 0;
          if (score > currentMaxScore) {
            documentScores.set(result.document_id, score);
          }
        });

        const hybridSearchFiltered = documents
          .filter(doc => foundDocumentIds.has(doc.document_id))
          .sort((a, b) => {
            const scoreA = documentScores.get(a.document_id) || 0;
            const scoreB = documentScores.get(b.document_id) || 0;
            return scoreB - scoreA;
          });

        const localSearchFiltered = documents.filter(doc =>
          !foundDocumentIds.has(doc.document_id) && (
            doc.file_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            doc.description?.toLowerCase().includes(searchQuery.toLowerCase()) ||
            doc.summary?.toLowerCase().includes(searchQuery.toLowerCase())
          )
        );

        const filtered = [...hybridSearchFiltered, ...localSearchFiltered];
        setFilteredDocuments(filtered);
      } else {
        setSearchResults([]);
        const filtered = documents.filter(doc =>
          doc.file_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          doc.description?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          doc.summary?.toLowerCase().includes(searchQuery.toLowerCase())
        );
        setFilteredDocuments(filtered);
      }
    } catch (error) {
      console.error('Search Failed:', error);
      const filtered = documents.filter(doc =>
        doc.file_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        doc.description?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        doc.summary?.toLowerCase().includes(searchQuery.toLowerCase())
      );
      setFilteredDocuments(filtered);
    } finally {
      setIsSearching(false);
    }
  }, [searchQuery, documents, indexId]);

  // Search query change handler
  const handleSearchChange = useCallback((query: string) => {
    setSearchQuery(query);
    
    if (!query.trim()) {
      setFilteredDocuments(documents);
      setSearchResults([]);
    }
  }, [documents]);

  // Update filtering when document list changes
  useEffect(() => {
    if (!searchQuery.trim()) {
      setFilteredDocuments(documents);
    }
  }, [documents, searchQuery]);


  // Perform hybrid search on typing (debounced)
  useEffect(() => {
    const query = searchQuery.trim();
    // Reset when empty
    if (!query) {
      setIsSearching(false);
      setSearchResults([]);
      setFilteredDocuments(documents);
      return;
    }

    const timeoutId = setTimeout(() => {
      executeSearch();
    }, 350); // debounce 350ms

    return () => clearTimeout(timeoutId);
  }, [searchQuery, executeSearch, documents]);

  return (
    <div className="h-full flex flex-col bg-black text-white">
      {/* Enhanced Header */}
      <div className="relative p-6 bg-gradient-to-r from-cyan-500/5 to-sky-500/5">
        {/* Background glow effect */}
        <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/10 via-transparent to-sky-500/10 opacity-30"></div>
        
        <div className="relative flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="relative">
              <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-cyan-500 to-sky-600 flex items-center justify-center shadow-lg shadow-cyan-500/25">
                <FileText className="h-6 w-6 text-white" />
              </div>
              <div className="absolute -inset-1 bg-gradient-to-br from-cyan-500/50 to-sky-600/50 rounded-2xl blur opacity-60"></div>
            </div>
            <div>
              <h2 className="text-xl font-bold text-white bg-gradient-to-r from-cyan-300 to-sky-300 bg-clip-text text-transparent">
                Documents List
              </h2>
              {indexId && (
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-sm text-white/60">Index:</span>
                  <span className="px-2 py-1 bg-cyan-500/20 border border-cyan-400/30 rounded-lg text-cyan-300 text-sm font-medium">
                    {indexId}
                  </span>
                </div>
              )}
            </div>
          </div>
          
          {/* Document count and WebSocket status */}
          <div className="flex items-center gap-3">
            <div className="px-3 py-1.5 bg-white/10 rounded-full backdrop-blur-sm">
              <span className="text-sm text-white/80 font-medium">
                Total {documents.length} documents
              </span>
            </div>
            
            {/* WebSocket Status */}
            <div className="flex items-center gap-2 px-2 py-1 rounded-md bg-black/30" title="실시간 업데이트 (비활성화)">
              <div className="w-2 h-2 bg-gray-400 rounded-full"></div>
              <span className="text-xs text-gray-400">Disabled</span>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {loading && documents.length === 0 ? (
          <DocumentLoadingState />
        ) : (
          <div className="h-full flex flex-col">
            {/* Header with controls */}
            <DocumentsPageHeader 
              onAddDocument={() => setShowUploadZone(true)}
              onRefresh={fetchDocuments}
              isLoading={loading}
              isUploading={isUploading}
              searchQuery={searchQuery}
              onSearchChange={handleSearchChange}
              onSearchExecute={executeSearch}
              isSearching={isSearching}
              searchResultCount={filteredDocuments.length}
              totalDocuments={documents.length}
            />
            
            <div className="flex-1 p-4 space-y-4 overflow-auto">
              {/* Upload Zone */}
              <UploadZone
                showUploadZone={showUploadZone}
                uploadFiles={uploadFiles}
                isUploading={isUploading}
                isDragActive={isDragActive}
                getRootProps={getRootProps}
                getInputProps={getInputProps}
                removeFile={removeFile}
                formatFileSize={formatFileSize}
                startUpload={startUpload}
                onClose={() => setShowUploadZone(false)}
              />
              
              {/* Document List */}
              <DocumentList
                documents={filteredDocuments}
                loading={loading}
                error={error}
                onViewDocument={viewDocument}
                onDeleteDocument={(documentId, targetIndexId) => deleteDocument(documentId, targetIndexId)}
                indexId={indexId}
                searchQuery={searchQuery}
                isSearching={isSearching}
                totalDocuments={documents.length}
                searchResults={searchResults}
                onAnalyzeDocument={onAnalyzeDocument}
              />
            </div>
          </div>
        )}
      </div>

      {/* Document Detail Dialog */}
      <DocumentDetailDialog
        document={selectedDocument}
        open={showDetail}
        onOpenChange={(open) => {
          if (!open) {
            closeDetail();
          }
        }}
        onClose={closeDetail}
        analysisData={analysisData}
        selectedSegment={selectedSegment}
        totalSegments={
          analysisData.length > 0 
            ? Math.max(...analysisData.map((item: any) => 
                (typeof item.segment_index === 'number' ? item.segment_index : 
                 typeof item.page_index === 'number' ? item.page_index : 0)
              ), 0) + 1
            : (typeof selectedDocument?.total_pages === 'number' ? selectedDocument.total_pages : 1)
        }
        imageZoom={imageZoom}
        imagePosition={imagePosition}
        isDragging={isDragging}
        currentPageImageUrl={currentPageImageUrl || undefined}
        analysisLoading={analysisLoading}
        imageLoading={imageLoading}
        indexId={indexId}
        imageRotation={imageRotation}
        onSegmentChange={handleSegmentChange}
        onZoomIn={zoomIn}
        onZoomOut={zoomOut}
        onRotateLeft={rotateLeft}
        onRotateRight={rotateRight}
        onResetImage={resetImage}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onAnalysisPopup={handleAnalysisPopup}
        onShowPdfViewer={() => setShowPdfViewer(true)}
      />

      {/* PDF Viewer Dialog */}
      <PdfViewerDialog 
        isOpen={showPdfViewer} 
        onClose={() => setShowPdfViewer(false)}
        document={selectedDocument}
        indexId={indexId}
      />

      {/* Upload Notifications */}
      <UploadNotificationContainer
        notifications={notifications}
        onDismiss={removeNotification}
        position="top-right"
        maxNotifications={3}
      />
    </div>
  );
}
