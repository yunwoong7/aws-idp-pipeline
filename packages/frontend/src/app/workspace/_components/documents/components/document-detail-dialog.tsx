"use client";

import React, { useState, useCallback } from "react";
import ReactDOM from "react-dom";
import { FileText, Play, Loader2, X, ZoomIn, ZoomOut, RotateCw, RotateCcw, ChevronDown, ChevronUp, Calendar, Database, Download, Eye, ChevronLeft, ChevronRight, AlertCircle } from "lucide-react";
import { AnalysisPopup } from "@/components/common/analysis-popup";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Label } from "@/components/ui/label";
import { Document } from "@/types/document.types";
import { SecureImage } from "@/components/ui/secure-image";
import { motion, AnimatePresence } from "framer-motion";
import { documentApi } from "@/lib/api";

// SecureVideo 컴포넌트
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
        console.log('🎥 [SecureVideo] Fetching presigned URL for:', s3Uri, 'with indexId:', indexId);
        const response = await documentApi.getPresignedUrlFromS3Uri(s3Uri, 3600, indexId);
        console.log('🎥 [SecureVideo] Got presigned URL:', response.presigned_url);
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
          <p className="text-white/60 text-sm">비디오 로딩 중...</p>
        </div>
      </div>
    );
  }

  if (error || !presignedUrl) {
    return (
      <div className={`flex items-center justify-center ${className}`} style={style}>
        <div className="flex flex-col items-center gap-3">
          <Play className="h-12 w-12 text-white/40" />
          <p className="text-white/60 text-sm">비디오를 불러올 수 없습니다</p>
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
      비디오를 재생할 수 없습니다.
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
                <span>접기</span>
                <ChevronUp className="h-3 w-3 transition-transform" />
              </>
            ) : (
              <>
                <span>펼치기</span>
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

  // Get analysis counts for current segment
  const getAllCounts = (data: any[]) => {
    if (!Array.isArray(data) || data.length === 0) {
      return { bda: 0, pdf: 0, ai: 0 };
    }
    
    let counts = { bda: 0, pdf: 0, ai: 0 };
    data.forEach((item: any) => {
      if (item.tool_name === 'bda_indexer') counts.bda++;
      else if (item.tool_name === 'pdf_text_extractor') counts.pdf++;
      else if (item.tool_name === 'ai_analysis') counts.ai++;
    });
    return counts;
  };

  const getSegmentCounts = (data: any[], segmentIndex: number) => {
    if (!Array.isArray(data) || data.length === 0) {
      return { bda: 0, pdf: 0, ai: 0 };
    }
    
    let counts = { bda: 0, pdf: 0, ai: 0 };
    data.forEach((item: any) => {
      const itemSegmentIndex = (typeof item.segment_index === 'number' ? item.segment_index : undefined) ??
                             (typeof item.page_index === 'number' ? item.page_index : undefined);
      
      if (itemSegmentIndex === segmentIndex) {
        if (item.tool_name === 'bda_indexer') counts.bda++;
        else if (item.tool_name === 'pdf_text_extractor') counts.pdf++;
        else if (item.tool_name === 'ai_analysis') counts.ai++;
      }
    });
    return counts;
  };

  const allCounts = getAllCounts(analysisData);
  const currentSegmentCounts = getSegmentCounts(analysisData, selectedSegment);

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
      className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center"
      style={{ zIndex: 9998 }}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onOpenChange(false);
        }
      }}
    >
      <div className="flex h-[90vh] w-[90vw] from-gray-900/95 via-gray-800/95 to-gray-900/95 backdrop-blur-xl border border-white/20 rounded-xl overflow-hidden shadow-[0_8px_32px_rgb(0_0_0/0.4)]">
        
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
                onClick={onClose}
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
                      {document.file_type.toUpperCase()}
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
                    <p className="text-white/80 mt-1">{totalSegments}</p>
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
            {analysisData.length > 0 && (
              <div className="space-y-3">
                <h3 className="text-white font-medium text-base">Analysis Summary</h3>
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-white/60">Total Results:</span>
                    <span className="text-white">{allCounts.bda + allCounts.pdf + allCounts.ai}</span>
                  </div>
                  
                  <div className="grid grid-cols-3 gap-2">
                    <button
                      onClick={() => {
                        console.log('BDA analysis clicked', { currentSegmentCounts, bda: currentSegmentCounts.bda });
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
                      onClick={() => {
                        console.log('PDF analysis clicked', { currentSegmentCounts, pdf: currentSegmentCounts.pdf });
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
                      onClick={() => {
                        console.log('AI analysis clicked', { currentSegmentCounts, ai: currentSegmentCounts.ai });
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
                  {Array.from({ length: totalSegments }, (_, i) => (
                    <option key={i} value={i} className="bg-gray-800">
                      Segment {i + 1}
                    </option>
                  ))}
                </select>
                
                <span className="text-white/60 text-sm whitespace-nowrap">
                  {(selectedSegment || 0) + 1}/{totalSegments}
                </span>
                
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
                  title="초기화"
                >
                  <X className="h-4 w-4" />
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
                    <p className="text-white/60 text-sm">미리보기 로딩 중...</p>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-3">
                    <FileText className="h-12 w-12 text-white/40" />
                    <p className="text-white/60 text-sm">미리보기를 사용할 수 없습니다</p>
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
        analysisData={analysisData}
        onClose={() => setAnalysisPopup({ type: null, isOpen: false })}
      />
    </div>,
    portalRoot
  );
}