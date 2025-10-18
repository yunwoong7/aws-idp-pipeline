"use client";

import React, { useState, useCallback, useEffect } from "react";
import ReactDOM from "react-dom";
import { FileText, Play, Loader2, X, ZoomIn, ZoomOut, RotateCw, RotateCcw, ChevronDown, ChevronUp, Calendar, Database, Download, Eye, ChevronLeft, ChevronRight, AlertCircle, CheckCircle, Clock, RefreshCw } from "lucide-react";
import { AnalysisPopup } from "@/components/common/analysis-popup";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Label } from "@/components/ui/label";
import { Document } from "@/types/document.types";
import { SecureImage } from "@/components/ui/secure-image";
import { motion, AnimatePresence } from "framer-motion";
import { documentApi } from "@/lib/api";

// SecureVideo component
interface SecureVideoProps {
  s3Uri: string | null | undefined;
  indexId?: string;
  className?: string;
  style?: React.CSSProperties;
  seekToSeconds?: number;
}

const SecureVideo = ({ s3Uri, indexId, className = '', style, seekToSeconds }: SecureVideoProps) => {
  const [presignedUrl, setPresignedUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const videoRef = React.useRef<HTMLVideoElement | null>(null);

  React.useEffect(() => {
    const fetchPresignedUrl = async () => {
      if (!s3Uri) {
        setError('Missing S3 URI');
        return;
      }

      if (!s3Uri.startsWith('s3://')) {
        setError('Invalid S3 URI format');
        return;
      }

      setIsLoading(true);
      setError(null);

      try {
        const response = await documentApi.getPresignedUrlFromS3Uri(s3Uri, 3600, indexId);
        setPresignedUrl(response.presigned_url);
        setError(null);
      } catch (err) {
        console.error('🎥 [SecureVideo] Failed to fetch presigned URL:', err);
        setError('Failed to load video');
        setPresignedUrl(null);
      } finally {
        setIsLoading(false);
      }
    };

    fetchPresignedUrl();
  }, [s3Uri, indexId]);

  React.useEffect(() => {
    if (!presignedUrl || seekToSeconds == null || Number.isNaN(seekToSeconds)) return;
    const el = videoRef.current;
    if (!el) return;

    const applySeek = () => {
      try {
        el.currentTime = Math.max(0, seekToSeconds);
      } catch (_) {
        // no-op
      }
    };

    if (el.readyState >= 1) {
      applySeek();
    } else {
      const onLoaded = () => {
        applySeek();
        el.removeEventListener('loadedmetadata', onLoaded);
      };
      el.addEventListener('loadedmetadata', onLoaded);
      return () => el.removeEventListener('loadedmetadata', onLoaded);
    }
  }, [presignedUrl, seekToSeconds]);

  if (isLoading) {
    return (
      <div className={`flex items-center justify-center ${className}`} style={style}>
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-purple-400" />
          <p className="text-white/60 text-sm">Loading video...</p>
        </div>
      </div>
    );
  }

  if (error || !presignedUrl) {
    return (
      <div className={`flex items-center justify-center ${className}`} style={style}>
        <div className="flex flex-col items-center gap-3">
          <Play className="h-12 w-12 text-white/40" />
          <p className="text-white/60 text-sm">Failed to load video</p>
          {error && <p className="text-red-400 text-xs">{error}</p>}
        </div>
      </div>
    );
  }

  return (
    <video
      ref={videoRef}
      controls
      className={className}
      style={style}
      preload="metadata"
    >
      <source src={presignedUrl} type="video/mp4" />
      <source src={presignedUrl} type="video/webm" />
      <source src={presignedUrl} type="video/ogg" />
      Failed to play video.
    </video>
  );
};

// Summary Section Component
interface SummarySectionProps {
  summary: string;
}

const SummarySection: React.FC<SummarySectionProps> = ({ summary }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  
  const previewText = summary.length > 100 ? summary.substring(0, 100) + '...' : summary;
  const shouldShowToggle = summary.length > 100;
  
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-emerald-200 text-xs">Description:</span>
        {shouldShowToggle && (
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center gap-1 text-emerald-300/60 hover:text-emerald-300/80 transition-colors text-xs hover:bg-emerald-500/10 rounded px-2 py-1"
          >
            {isExpanded ? (
              <>
                <span>Collapse</span>
                <ChevronUp className="h-3 w-3 transition-transform" />
              </>
            ) : (
              <>
                <span>Expand</span>
                <ChevronDown className="h-3 w-3 transition-transform" />
              </>
            )}
          </button>
        )}
      </div>
      <motion.div 
        className="text-emerald-100 text-sm leading-relaxed overflow-hidden"
        initial={false}
        animate={{
          height: 'auto',
          opacity: 1
        }}
        transition={{
          duration: 0.3,
          ease: "easeInOut"
        }}
      >
        <AnimatePresence mode="wait">
          <motion.div
            key={isExpanded ? 'expanded' : 'collapsed'}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            {isExpanded ? summary : previewText}
          </motion.div>
        </AnimatePresence>
      </motion.div>
    </div>
  );
};

interface ZoomedImageState {
  isOpen: boolean;
  imageData: string;
  mimeType: string;
}

interface DocumentDetailDialogProps {
  document: Document | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onClose: () => void;
  indexId?: string;
  
  // Image state
  imageZoom?: number;
  imageRotation?: number;
  imagePosition?: { x: number; y: number };
  currentPageImageUrl?: string | null;
  imageLoading?: boolean;
  isDragging?: boolean;
  dragStart?: { x: number; y: number };
  
  // Segment state
  selectedSegment?: number;
  totalSegments?: number;
  
  // Analysis data
  analysisData?: any[];
  analysisLoading?: boolean;
  
  // Zoomed image state
  zoomedImage?: ZoomedImageState;
  
  // Event handlers
  onZoomIn?: () => void;
  onZoomOut?: () => void;
  onRotateLeft?: () => void;
  onRotateRight?: () => void;
  onResetImage?: () => void;
  onMouseDown?: (e: React.MouseEvent) => void;
  onMouseMove?: (e: React.MouseEvent) => void;
  onMouseUp?: () => void;
  onSegmentChange?: (segment: number) => void;
  onAnalysisPopup?: (popup: { type: 'bda' | 'pdf' | 'ai' | null; isOpen: boolean }) => void;
  onSetZoomedImage?: (state: ZoomedImageState) => void;
  onShowPdfViewer?: () => void;
  
  // Chat actions
  onAddDocument?: () => void;
  onAddPage?: () => void;
  canAddDocument?: boolean;
  canAddPage?: boolean;
  // Optional segment start timecodes for video seeking
  segmentStartTimecodes?: string[];
}

export function DocumentDetailDialog({
  document,
  open,
  onOpenChange,
  onClose,
  indexId,
  imageZoom = 1,
  imageRotation = 0,
  imagePosition = { x: 0, y: 0 },
  currentPageImageUrl,
  imageLoading = false,
  isDragging = false,
  dragStart = { x: 0, y: 0 },
  selectedSegment = 0,
  totalSegments = 0,
  analysisData = [],
  analysisLoading = false,
  zoomedImage = { isOpen: false, imageData: '', mimeType: '' },
  onZoomIn,
  onZoomOut,
  onRotateLeft,
  onRotateRight,
  onResetImage,
  onMouseDown,
  onMouseMove,
  onMouseUp,
  onSegmentChange,
  onAnalysisPopup,
  onSetZoomedImage,
  onShowPdfViewer,
  onAddDocument,
  onAddPage,
  canAddDocument = false,
  canAddPage = false,
  segmentStartTimecodes
}: DocumentDetailDialogProps) {
  // 세그먼트 메타데이터 상태
  const [segmentMetadata, setSegmentMetadata] = useState<any[]>([]);
  const [segmentMetadataLoading, setSegmentMetadataLoading] = useState(false);

  // 개별 세그먼트 상세 데이터 캐시
  const [segmentDetailsCache, setSegmentDetailsCache] = useState<Record<number, any>>({});
  const [currentSegmentDetail, setCurrentSegmentDetail] = useState<any>(null);
  const [segmentDetailLoading, setSegmentDetailLoading] = useState(false);

  // 문서 변경 시 캐시 초기화
  useEffect(() => {
    // 문서가 변경되거나 Dialog가 열릴 때 캐시 초기화
    setSegmentDetailsCache({});
    setCurrentSegmentDetail(null);
  }, [document?.document_id, open]);

  // 초기 로딩 시 analysisData에서 segment 메타데이터 추출
  useEffect(() => {
    if (!open || !analysisData || analysisData.length === 0) {
      setSegmentMetadata([]);
      return;
    }

    // analysisData를 segment metadata 형식으로 변환
    const segments = analysisData.map((item: any) => ({
      segment_id: item.segment_id,
      segment_index: item.segment_index ?? item.page_index,
      status: item.status || 'completed',
      image_uri: item.image_file_uri || item.image_path,
      file_uri: item.file_uri || item.file_path,
      start_timecode_smpte: item.start_timecode_smpte,
    }));

    setSegmentMetadata(segments);
    setSegmentMetadataLoading(false);
  }, [open, analysisData]);

  // 선택된 세그먼트 변경 시 상세 데이터 로딩
  useEffect(() => {
    const shouldLoad = open && indexId && document?.document_id && typeof selectedSegment === 'number';
    if (!shouldLoad) return;

    // 캐시에 이미 있는지 확인
    if (segmentDetailsCache[selectedSegment]) {
      setCurrentSegmentDetail(segmentDetailsCache[selectedSegment]);
      return;
    }

    // 선택된 segment의 segment_id 찾기
    const selectedSegmentData = segmentMetadata.find(
      (seg: any) => (seg?.segment_index ?? seg?.page_index) === selectedSegment
    );

    if (!selectedSegmentData?.segment_id) {
      console.warn(`No segment_id found for segment index ${selectedSegment}`);
      setCurrentSegmentDetail(null);
      return;
    }

    (async () => {
      setSegmentDetailLoading(true);
      try {
        const segmentDetail = await documentApi.getSegmentDetail(
          indexId as string,
          document!.document_id,
          selectedSegmentData.segment_id
        );

        console.log('📊 Segment detail fetched:', {
          segment_id: selectedSegmentData.segment_id,
          analysis_results_count: segmentDetail?.analysis_results?.length || 0,
          total_analysis_results: segmentDetail?.total_analysis_results,
          first_result: segmentDetail?.analysis_results?.[0]
        });

        // 캐시에 저장
        setSegmentDetailsCache(prev => ({
          ...prev,
          [selectedSegment]: segmentDetail
        }));

        setCurrentSegmentDetail(segmentDetail);
      } catch (error) {
        console.error(`Failed to fetch segment ${selectedSegment} detail:`, error);
        setCurrentSegmentDetail(null);
      } finally {
        setSegmentDetailLoading(false);
      }
    })();
  }, [open, indexId, document?.document_id, selectedSegment, segmentMetadata]);
  
  // Analysis popup state
  const [analysisPopup, setAnalysisPopup] = useState<{ type: 'bda' | 'pdf' | 'ai' | null; isOpen: boolean }>({
    type: null,
    isOpen: false
  });
  
  // Helper functions
  const formatDate = useCallback((dateString: string) => {
    return new Date(dateString).toLocaleDateString('ko-KR', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }, []);

  const formatFileSize = useCallback((bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }, []);

  const formatFileName = (fileName: string, maxLength: number = 30) => {
    if (fileName.length <= maxLength) return fileName;
    
    const extension = fileName.split('.').pop();
    const nameWithoutExt = fileName.substring(0, fileName.lastIndexOf('.'));
    
    if (extension) {
      const availableLength = maxLength - extension.length - 4;
      if (availableLength > 0) {
        return `${nameWithoutExt.substring(0, availableLength)}...${extension}`;
      }
    }
    
    return `${fileName.substring(0, maxLength - 3)}...`;
  };

  const formatFileType = (fileType: string) => {
    const typeMap: { [key: string]: string } = {
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'DOCX',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'XLSX', 
      'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'PPTX',
      'application/vnd.ms-excel': 'XLS',
      'application/vnd.ms-powerpoint': 'PPT',
      'application/msword': 'DOC',
      'application/pdf': 'PDF',
      'text/plain': 'TXT',
      'text/csv': 'CSV',
      'image/jpeg': 'JPG',
      'image/png': 'PNG',
      'image/gif': 'GIF',
      'video/mp4': 'MP4',
      'video/avi': 'AVI',
      'video/quicktime': 'MOV'
    };
    
    return typeMap[fileType.toLowerCase()] || fileType.split('/').pop()?.toUpperCase() || fileType.toUpperCase();
  };

  // Get analysis counts from current segment detail
  const getCurrentSegmentCounts = (segmentDetail: any) => {
    if (!segmentDetail?.analysis_results) {
      return { bda: 0, pdf: 0, ai: 0 };
    }

    const analysisResults = segmentDetail.analysis_results || [];
    let counts = { bda: 0, pdf: 0, ai: 0 };

    analysisResults.forEach((result: any) => {
      const toolName = result.tool_name;
      if (toolName === 'bda_indexer') counts.bda++;
      else if (toolName === 'pdf_text_extractor') counts.pdf++;
      else if (toolName === 'ai_analysis') counts.ai++;
    });

    return counts;
  };

  // Get total counts from segment metadata
  const getTotalCounts = (metadata: any[]) => {
    let totalCounts = { bda: 0, pdf: 0, ai: 0 };
    metadata.forEach((segment: any) => {
      const toolsCount = segment.tools_count || {};
      totalCounts.bda += toolsCount.bda_indexer || 0;
      totalCounts.pdf += toolsCount.pdf_text_extractor || 0;
      totalCounts.ai += toolsCount.ai_analysis || 0;
    });
    return totalCounts;
  };

  const allCounts = getTotalCounts(segmentMetadata);
  const currentSegmentCounts = getCurrentSegmentCounts(currentSegmentDetail);

  // Debug: 세그먼트 네비게이션 표시 조건 확인
  // console.log('🔍 [DocumentDetailDialog] Segment navigation debug:', {
  //   totalSegments,
  //   document: !!document,
  //   showNavigation: totalSegments > 1,
  //   analysisDataLength: analysisData.length,
  //   selectedSegment
  // });

  if (!document || !open) return null;

  // Portal을 사용해서 body에 직접 렌더링하여 쌓임 맥락 문제 해결
  const portalRoot = typeof window !== 'undefined' && typeof window.document !== 'undefined' ? window.document.body : null;
  
  if (!portalRoot) return null;

  const isVideoFile = document && (
    document.file_type.includes('video') || 
    ['mp4', 'avi', 'mov', 'wmv', 'mkv', 'webm'].some(ext => 
      document.file_name.toLowerCase().endsWith(ext)
    )
  );

  const smpteToSeconds = (smpte?: string): number | undefined => {
    if (!smpte) return undefined;
    const norm = smpte.trim();
    let m = norm.match(/^(\d{1,2}):(\d{2}):(\d{2})(?:[;:\.](\d{1,2}))?$/);
    let h = 0, mnt = 0, sec = 0, frames = 0;
    if (m) {
      h = parseInt(m[1], 10);
      mnt = parseInt(m[2], 10);
      sec = parseInt(m[3], 10);
      frames = m[4] != null ? parseInt(m[4], 10) : 0;
    } else {
      m = norm.match(/^(\d{1,2}):(\d{2})$/);
      if (!m) return undefined;
      mnt = parseInt(m[1], 10);
      sec = parseInt(m[2], 10);
    }
    const DEFAULT_FPS = 30;
    return h * 3600 + mnt * 60 + sec + (frames / DEFAULT_FPS);
  };

  const seekSeconds = (() => {
    if (!isVideoFile) return undefined;
    const smpte = segmentStartTimecodes && selectedSegment != null ? segmentStartTimecodes[selectedSegment] : undefined;
    return smpteToSeconds(smpte);
  })();

  return ReactDOM.createPortal(
    <div 
      className="fixed inset-0 bg-black/60 backdrop-blur-md flex items-center justify-center"
      style={{ zIndex: 10000 }}
      onClick={(e) => {
        e.stopPropagation();
        if (e.target === e.currentTarget) {
          onOpenChange(false);
          onClose();
        }
      }}
    >
      <div 
        className="flex h-[90vh] w-[90vw] from-gray-900/95 via-gray-800/95 to-gray-900/95 backdrop-blur-xl border border-white/20 rounded-xl overflow-hidden shadow-[0_8px_32px_rgb(0_0_0/0.4)]"
        onClick={(e) => e.stopPropagation()}
      >
        
        {/* Left Panel - Document Info */}
        <div className="w-1/3 backdrop-blur-sm border-r border-white/10 flex flex-col">
          {/* Header */}
          <div className="p-6 border-b border-white/10">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-lg bg-white/5 backdrop-blur-sm border border-white/10 flex items-center justify-center">
                  <FileText className="h-6 w-6 text-gray-300" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-white">Document Details</h2>
                  <p className="text-sm text-white/60">Complete document information</p>
                </div>
              </div>
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => {
                  onOpenChange(false);
                  onClose();
                }}
                className="text-white/70 hover:text-white hover:bg-white/10 border border-white/10 hover:border-white/30"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Document Information */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {/* Basic Information */}
            <div className="space-y-4">
              <h3 className="text-white font-medium text-base flex items-center gap-2">
                <Database className="h-4 w-4 text-gray-300" />
                Basic Information
              </h3>
              
              <div className="space-y-3 text-sm">
                {/* File Name - Full Width */}
                <div>
                  <Label className="text-white/60 text-xs">File Name</Label>
                  <p className="text-white font-medium mt-1 break-all" title={document.file_name}>
                    {formatFileName(document.file_name)}
                  </p>
                </div>
                
                {/* File Type & File Size - Same Row */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-white/60 text-xs">File Type</Label>
                    <Badge className={`mt-1 bg-white/5 text-gray-200 border-white/20`}>
                      {formatFileType(document.file_type)}
                    </Badge>
                  </div>
                  <div>
                    <Label className="text-white/60 text-xs">File Size</Label>
                    <p className="text-white/80 mt-1">{formatFileSize(document.file_size)}</p>
                  </div>
                </div>
                
                {/* Status & Total Segments - Same Row */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-white/60 text-xs">Status</Label>
                    <div className="flex items-center gap-2 mt-1">
                      <div className={`size-2 rounded-full ${
                        document.status === 'completed' ? 'bg-emerald-500' : 'bg-yellow-500'
                      }`} />
                      <span className="text-white/80 text-sm">{document.status}</span>
                    </div>
                  </div>
                  <div>
                    <Label className="text-white/60 text-xs">Total Segments</Label>
                    <p className="text-white/80 mt-1">
                      {(() => {
                        const docStatus = String((document as any)?.status || '').toLowerCase();
                        const beforeIndexingComplete = ['pending_upload','uploading','uploaded','bda_analyzing'].includes(docStatus);
                        return beforeIndexingComplete ? 'Analyzing...' : totalSegments;
                      })()}
                    </p>
                  </div>
                </div>
                
                {/* Created Date - Full Width */}
                <div>
                  <Label className="text-white/60 text-xs">Created</Label>
                  <p className="text-white/80 mt-1 flex items-center gap-2">
                    <Calendar className="h-3 w-3 text-white/60" />
                    {formatDate(document.created_at)}
                  </p>
                </div>
              </div>
            </div>

            <Separator className="border-white/10" />

            {/* Description */}
            {document.description && (
              <SummarySection 
                summary={document.description}
              />
            )}



            <Separator className="border-white/10" />

            {/* Analysis Results Summary */}
            {segmentMetadata.length > 0 && (
              <div className="space-y-3">
                <h3 className="text-white font-medium text-base">Analysis Summary</h3>
                <div className="space-y-2">
                  {segmentDetailLoading ? (
                    <div className="text-center py-4">
                      <Loader2 className="h-4 w-4 animate-spin text-purple-400 mx-auto" />
                      <p className="text-white/60 text-xs mt-1">Loading segment details...</p>
                    </div>
                  ) : (
                    <div className="grid grid-cols-3 gap-2">
                      <button
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          console.log('BDA analysis clicked', {
                            currentSegmentCounts,
                            bda: currentSegmentCounts.bda,
                            currentSegmentDetail,
                            analysis_results: currentSegmentDetail?.analysis_results
                          });
                          if (currentSegmentCounts.bda > 0) {
                            setAnalysisPopup({ type: 'bda', isOpen: true });
                          }
                        }}
                        disabled={currentSegmentCounts.bda === 0}
                        className={`flex items-center justify-between px-2 py-1.5 rounded border transition-all duration-200 group ${
                          currentSegmentCounts.bda > 0
                            ? 'bg-white/5 border-white/10 hover:bg-white/10 hover:border-white/20 cursor-pointer'
                            : 'bg-white/2 border-white/5 opacity-50 cursor-not-allowed'
                        }`}
                      >
                        <span className={`text-xs font-medium ${
                          currentSegmentCounts.bda > 0 ? 'text-white/80' : 'text-white/40'
                        }`}>BDA</span>
                        <span className={`text-sm font-bold ${
                          currentSegmentCounts.bda > 0 ? 'text-white' : 'text-white/40'
                        }`}>
                          {currentSegmentCounts.bda}
                        </span>
                      </button>

                      <button
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          console.log('PDF analysis clicked', {
                            currentSegmentCounts,
                            pdf: currentSegmentCounts.pdf,
                            currentSegmentDetail,
                            analysis_results: currentSegmentDetail?.analysis_results
                          });
                          if (currentSegmentCounts.pdf > 0) {
                            setAnalysisPopup({ type: 'pdf', isOpen: true });
                          }
                        }}
                        disabled={currentSegmentCounts.pdf === 0}
                        className={`flex items-center justify-between px-2 py-1.5 rounded border transition-all duration-200 group ${
                          currentSegmentCounts.pdf > 0
                            ? 'bg-white/5 border-white/10 hover:bg-white/10 hover:border-white/20 cursor-pointer'
                            : 'bg-white/2 border-white/5 opacity-50 cursor-not-allowed'
                        }`}
                      >
                        <span className={`text-xs font-medium ${
                          currentSegmentCounts.pdf > 0 ? 'text-white/80' : 'text-white/40'
                        }`}>PDF</span>
                        <span className={`text-sm font-bold ${
                          currentSegmentCounts.pdf > 0 ? 'text-white' : 'text-white/40'
                        }`}>
                          {currentSegmentCounts.pdf}
                        </span>
                      </button>

                      <button
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          console.log('AI analysis clicked', {
                            currentSegmentCounts,
                            ai: currentSegmentCounts.ai,
                            currentSegmentDetail,
                            analysis_results: currentSegmentDetail?.analysis_results
                          });
                          if (currentSegmentCounts.ai > 0) {
                            setAnalysisPopup({ type: 'ai', isOpen: true });
                          }
                        }}
                        disabled={currentSegmentCounts.ai === 0}
                        className={`flex items-center justify-between px-2 py-1.5 rounded border transition-all duration-200 group ${
                          currentSegmentCounts.ai > 0
                            ? 'bg-white/5 border-white/10 hover:bg-white/10 hover:border-white/20 cursor-pointer'
                            : 'bg-white/2 border-white/5 opacity-50 cursor-not-allowed'
                        }`}
                      >
                        <span className={`text-xs font-medium ${
                          currentSegmentCounts.ai > 0 ? 'text-white/80' : 'text-white/40'
                        }`}>AI</span>
                        <span className={`text-sm font-bold ${
                          currentSegmentCounts.ai > 0 ? 'text-white' : 'text-white/40'
                        }`}>
                          {currentSegmentCounts.ai}
                        </span>
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Footer Actions */}
          <div className="p-6 border-t border-white/10 space-y-3">
            {(document.file_type === 'pdf' || document.file_type === 'application/pdf') && (
              <Button 
                onClick={onShowPdfViewer}
                className="w-full bg-white/10 hover:bg-white/20 text-white border border-white/10"
              >
                <Eye className="h-4 w-4 mr-2" />
                Open PDF Viewer
              </Button>
            )}
            
          </div>
        </div>

        {/* Right Panel - Preview */}
        <div className="flex-1 flex flex-col backdrop-blur-sm">
          
          {/* Controls Header */}
          <div className="p-4 border-b border-white/10 flex items-center justify-between">
            {/* Segment Navigation */}
            {totalSegments > 1 && (
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onSegmentChange?.(selectedSegment - 1)}
                  disabled={selectedSegment <= 0}
                  className="h-8 w-8 p-0 border-white/10 text-white/80 hover:text-white hover:bg-white/10"
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                
                <select
                  value={selectedSegment || 0}
                  onChange={(e) => {
                    const newSegment = parseInt(e.target.value);
                    onSegmentChange?.(newSegment);
                  }}
                  className="bg-white/10 border border-white/10 rounded px-3 py-1 text-white text-sm focus:outline-none focus:border-white/40"
                >
                  {(() => {
                    if (segmentMetadataLoading) {
                      return (
                        <option value={selectedSegment || 0} className="bg-gray-800">
                          Loading segments...
                        </option>
                      );
                    }

                    const statusByIndex: Record<number, string> = {};

                    // Get status from segment metadata
                    segmentMetadata.forEach((segment: any) => {
                      const segmentIndex = segment?.segment_index ?? segment?.page_index;
                      if (typeof segmentIndex === 'number') {
                        const status = String(segment?.status || '').toLowerCase();
                        statusByIndex[segmentIndex] = status;
                      }
                    });

                    // Also check document's page_images for compatibility
                    const docSegs: any[] = (document as any)?.page_images || (document as any)?.segment_images || [];
                    docSegs.forEach((s) => {
                      const segmentIndex = s?.page_index ?? s?.segment_index;
                      if (typeof segmentIndex === 'number') {
                        const status = String(s.page_status || s.status || '').toLowerCase();
                        if (status) statusByIndex[segmentIndex] = status;
                      }
                    });

                    const indices = Array.from({ length: totalSegments }, (_, i) => i);
                    const isCompleted = (st: string) => st === 'completed';
                    const isFailed = (st: string) => st.includes('failed') || st === 'error';
                    const isAnalyzing = (st: string) => st.includes('analyz') || st.includes('process') || st.includes('extract');

                    const completed = indices.filter(i => isCompleted(statusByIndex[i] || ''));
                    const failed = indices.filter(i => isFailed(statusByIndex[i] || ''));
                    const analyzing = indices.filter(i => isAnalyzing(statusByIndex[i] || ''));
                    const inprogress = indices.filter(i => {
                      const status = statusByIndex[i] || '';
                      return status && !isCompleted(status) && !isFailed(status) && !isAnalyzing(status);
                    });
                    const pending = indices.filter(i => !statusByIndex[i]);

                    // Combine analyzing, inprogress, and pending into a single "In progress" group
                    const allInProgress = [...analyzing, ...inprogress, ...pending];

                    return (
                      <>
                        {allInProgress.length > 0 && (
                          <optgroup label={`In progress (${allInProgress.length})`}>
                            {allInProgress.map(i => (
                              <option key={`ip-${i}`} value={i} className="bg-gray-800">
                                Segment {i + 1} - {statusByIndex[i] || 'in progress'}
                              </option>
                            ))}
                          </optgroup>
                        )}
                        {completed.length > 0 && (
                          <optgroup label={`Completed (${completed.length})`}>
                            {completed.map(i => (
                              <option key={`ok-${i}`} value={i} className="bg-gray-800">
                                Segment {i + 1}
                              </option>
                            ))}
                          </optgroup>
                        )}
                        {failed.length > 0 && (
                          <optgroup label={`Failed (${failed.length})`}>
                            {failed.map(i => (
                              <option key={`failed-${i}`} value={i} className="bg-gray-800">
                                Segment {i + 1} - {statusByIndex[i] || 'failed'}
                              </option>
                            ))}
                          </optgroup>
                        )}
                        {/* Fallback: show all if no status info available */}
                        {allInProgress.length === 0 && completed.length === 0 && failed.length === 0 && (
                          indices.map(i => (
                            <option key={`all-${i}`} value={i} className="bg-gray-800">
                              Segment {i + 1}
                            </option>
                          ))
                        )}
                      </>
                    );
                  })()}
                </select>
                
                <span className="text-white/60 text-sm whitespace-nowrap">
                  {(selectedSegment || 0) + 1}/{totalSegments}
                </span>
                {/* 현재 선택 세그먼트 상태 배지 */}
                {(() => {
                  const currentSegmentIndex = selectedSegment || 0;
                  let segStatus = '';

                  // Get status from segment metadata
                  const currentSegmentMeta = segmentMetadata.find((s: any) =>
                    (s?.segment_index ?? s?.page_index) === currentSegmentIndex
                  );

                  // Fallback to document page_images
                  const docSegs = (document as any)?.page_images || (document as any)?.segment_images || [];
                  const currentDocSegment = docSegs.find((s: any) =>
                    (s?.page_index ?? s?.segment_index) === currentSegmentIndex
                  );

                  segStatus = String(
                    currentSegmentMeta?.status ||
                    currentDocSegment?.page_status ||
                    currentDocSegment?.status ||
                    ''
                  ).toLowerCase();

                  if (!segStatus && segmentMetadataLoading) {
                    return (
                      <Badge className="text-xs border bg-white/10 text-white/70 border-white/20 flex items-center gap-1">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        Loading
                      </Badge>
                    );
                  }

                  if (!segStatus) return null;

                  // Status-specific styling
                  const getStatusInfo = (status: string) => {
                    if (status === 'completed') {
                      return {
                        badgeClass: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
                        icon: <CheckCircle className="h-3 w-3" />,
                        label: 'Completed'
                      };
                    } else if (status.includes('analyz')) {
                      return {
                        badgeClass: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
                        icon: <Clock className="h-3 w-3 animate-pulse" />,
                        label: 'In progress'
                      };
                    } else if (status.includes('failed') || status === 'error') {
                      return {
                        badgeClass: 'bg-red-500/20 text-red-300 border-red-500/30',
                        icon: <AlertCircle className="h-3 w-3" />,
                        label: 'Failed'
                      };
                    } else if (status.includes('process') || status.includes('extract')) {
                      return {
                        badgeClass: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
                        icon: <RefreshCw className="h-3 w-3 animate-spin" />,
                        label: 'In progress'
                      };
                    } else if (status) {
                      return {
                        badgeClass: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
                        icon: <Clock className="h-3 w-3" />,
                        label: 'In progress'
                      };
                    } else {
                      return {
                        badgeClass: 'bg-white/10 text-white/70 border-white/20',
                        icon: <Clock className="h-3 w-3" />,
                        label: 'In progress'
                      };
                    }
                  };

                  const statusInfo = getStatusInfo(segStatus);

                  return (
                    <Badge className={`text-xs border ${statusInfo.badgeClass} flex items-center gap-1`}>
                      {statusInfo.icon}
                      {statusInfo.label}
                    </Badge>
                  );
                })()}
                
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onSegmentChange?.(selectedSegment + 1)}
                  disabled={selectedSegment >= totalSegments - 1}
                  className="h-8 w-8 p-0 border-white/10 text-white/80 hover:text-white hover:bg-white/10"
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            )}
            
            {/* Image Controls */}
            {!isVideoFile && (
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onZoomOut}
                  disabled={imageZoom <= 0.25}
                  className="h-8 w-8 p-0 border-white/10 text-white/80 hover:text-white hover:bg-white/10"
                >
                  <ZoomOut className="h-4 w-4" />
                </Button>
                <span className="text-white/80 text-sm px-2 font-mono">
                  {Math.round(imageZoom * 100)}%
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onZoomIn}
                  disabled={imageZoom >= 3}
                  className="h-8 w-8 p-0 border-white/10 text-white/80 hover:text-white hover:bg-white/10"
                >
                  <ZoomIn className="h-4 w-4" />
                </Button>
                <div className="w-px bg-white/10 mx-1 h-4"></div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    console.log('Rotate left clicked');
                    onRotateLeft?.();
                  }}
                  className="h-8 w-8 p-0 border-white/10 text-white/80 hover:text-white hover:bg-white/10"
                >
                  <RotateCcw className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    console.log('Rotate right clicked');
                    onRotateRight?.();
                  }}
                  className="h-8 w-8 p-0 border-white/10 text-white/80 hover:text-white hover:bg-white/10"
                >
                  <RotateCw className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    console.log('Reset image clicked');
                    onResetImage?.();
                  }}
                  className="h-8 w-8 p-0 border-white/10 text-white/80 hover:text-white hover:bg-white/10"
                  title="Reset"
                >
                  <RefreshCw className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>

          {/* Preview Content */}
          <div className="flex-1 bg-white/5 rounded-lg border border-white/10 m-4 overflow-hidden relative">
            {isVideoFile ? (
              // Video player
              <div className="h-full flex items-center justify-center relative">
                <SecureVideo
                  s3Uri={document.file_uri}
                  indexId={indexId}
                  className="max-h-full max-w-full rounded-lg shadow-lg"
                  seekToSeconds={seekSeconds}
                />
              </div>
            ) : currentPageImageUrl && !imageLoading ? (
              // Image preview
              <div className="h-full flex items-center justify-center overflow-hidden">
                <div
                  className="relative"
                  onMouseDown={onMouseDown}
                  style={{
                    transform: `scale(${imageZoom}) rotate(${imageRotation}deg) translate(${imagePosition.x}px, ${imagePosition.y}px)`,
                    cursor: imageZoom > 1 ? (isDragging ? 'grabbing' : 'grab') : 'pointer',
                    transition: isDragging ? 'none' : 'transform 0.2s ease-out'
                  }}
                  onMouseMove={onMouseMove}
                  onMouseUp={onMouseUp}
                  onMouseLeave={onMouseUp}
                >
                  <div
                    className="cursor-pointer"
                    onClick={() => {
                      if (imageZoom === 1) {
                        onSetZoomedImage?.({
                          isOpen: true,
                          imageData: currentPageImageUrl,
                          mimeType: 'image/png'
                        });
                      }
                    }}
                  >
                    <SecureImage
                      s3Uri={currentPageImageUrl}
                      alt={`${document.file_name} - Segment ${selectedSegment + 1}`}
                      className="max-h-[600px] max-w-[800px] object-contain rounded-lg shadow-lg"
                      projectId={indexId || ''}
                    />
                  </div>
                </div>
              </div>
            ) : (
              // Loading or no preview
              <div className="h-full flex items-center justify-center">
                {imageLoading ? (
                  <div className="flex flex-col items-center gap-3">
                    <Loader2 className="h-8 w-8 animate-spin text-purple-400" />
                    <p className="text-white/60 text-sm">Loading preview...</p>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-3">
                    <FileText className="h-12 w-12 text-white/40" />
                    <p className="text-white/60 text-sm">Preview is not available for this file</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Analysis Popup */}
      <AnalysisPopup
        isOpen={analysisPopup.isOpen}
        type={analysisPopup.type}
        selectedSegment={selectedSegment}
        analysisData={currentSegmentDetail ? currentSegmentDetail.analysis_results || [] : []}
        onClose={() => setAnalysisPopup({ type: null, isOpen: false })}
      />
    </div>,
    portalRoot
  );
}