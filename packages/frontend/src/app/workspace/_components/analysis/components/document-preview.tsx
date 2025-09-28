"use client";

import React, { useState, useCallback, useRef } from "react";
import { FileText, Play, Loader2, X, ZoomIn, ZoomOut, RotateCw, RotateCcw, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PinContainer } from "@/components/ui/3d-pin";
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

// Simple in-memory cache to avoid repeated presign calls per key (s3Uri|indexId)
const presignedVideoCache = new Map<string, string>();

const SecureVideo = ({ s3Uri, indexId, className = '', style, seekToSeconds }: SecureVideoProps) => {
  const [presignedUrl, setPresignedUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlightKeyRef = useRef<string | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

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

      const cacheKey = `${s3Uri}|${indexId || ''}`;

      // Serve from cache if available
      if (presignedVideoCache.has(cacheKey)) {
        setPresignedUrl(presignedVideoCache.get(cacheKey) || null);
        setError(null);
        return;
      }

      // Prevent duplicate concurrent requests for the same key
      if (inFlightKeyRef.current === cacheKey) {
        return;
      }

      inFlightKeyRef.current = cacheKey;
      setIsLoading(true);
      setError(null);

      try {
        console.log('🎥 [SecureVideo] Fetching presigned URL for:', s3Uri, 'with indexId:', indexId);
        const response = await documentApi.getPresignedUrlFromS3Uri(s3Uri, 3600, indexId);
        console.log('🎥 [SecureVideo] Got presigned URL:', response.presigned_url);
        setPresignedUrl(response.presigned_url);
        presignedVideoCache.set(cacheKey, response.presigned_url);
        setError(null);
      } catch (err) {
        console.error('🎥 [SecureVideo] Failed to fetch presigned URL:', err);
        setError('Failed to load video');
        setPresignedUrl(null);
      } finally {
        setIsLoading(false);
        inFlightKeyRef.current = null;
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

// Summary Section Component with expand/collapse
interface SummarySectionProps {
  summary: string;
}

const SummarySection: React.FC<SummarySectionProps> = ({ summary }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  
  // Show first 100 characters as preview
  const previewText = summary.length > 100 ? summary.substring(0, 100) + '...' : summary;
  const shouldShowToggle = summary.length > 100;
  
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-white/60 text-sm">Description:</span>
        {shouldShowToggle && (
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center gap-1 text-white/60 hover:text-white/80 transition-colors text-xs hover:bg-white/5 rounded px-2 py-1"
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
        className="text-white text-sm leading-relaxed overflow-hidden"
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

interface DocumentPreviewProps {
  // Document related
  selectedDocument: Document | null;
  indexId?: string;

  // Image state
  imageZoom: number;
  imageRotation: number;
  imagePosition: { x: number; y: number };
  currentPageImageUrl: string | null;
  imageLoading: boolean;
  isDragging: boolean;
  dragStart: { x: number; y: number };

  // Segment state
  selectedSegment: number;
  totalSegments: number;

  // Analysis data - now expecting segment detail format
  analysisData: any[];
  analysisLoading: boolean;
  currentSegmentDetail?: any; // Current segment's detailed analysis data

  // Zoomed image state
  zoomedImage: ZoomedImageState;
  
  // Event handlers
  onDocumentSelect: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onRotateLeft: () => void;
  onRotateRight: () => void;
  onResetImage: () => void;
  onMouseDown: (e: React.MouseEvent) => void;
  onMouseMove: (e: React.MouseEvent) => void;
  onMouseUp: () => void;
  onSegmentChange: (segment: number) => void;
  onAnalysisPopup: (popup: { type: 'bda' | 'pdf' | 'ai' | null; isOpen: boolean }) => void;
  onSetZoomedImage: (state: ZoomedImageState) => void;
  setIsDragging: (dragging: boolean) => void;
  setDragStart: (start: { x: number; y: number }) => void;
  segmentStartTimecodes?: string[];
}

export function DocumentPreview({
  selectedDocument,
  indexId,
  imageZoom,
  imageRotation,
  imagePosition,
  currentPageImageUrl,
  imageLoading,
  isDragging,
  dragStart,
  selectedSegment,
  totalSegments,
  analysisData,
  analysisLoading,
  currentSegmentDetail,
  zoomedImage,
  onDocumentSelect,
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
  setIsDragging,
  setDragStart,
  segmentStartTimecodes
}: DocumentPreviewProps) {
  
  // Format file size
  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  // Format file name for display
  const formatFileName = (fileName: string, maxLength: number = 30) => {
    if (fileName.length <= maxLength) return fileName;
    
    const extension = fileName.split('.').pop();
    const nameWithoutExt = fileName.substring(0, fileName.lastIndexOf('.'));
    
    if (extension) {
      const availableLength = maxLength - extension.length - 4; // 4 for "..." and "."
      if (availableLength > 0) {
        return `${nameWithoutExt.substring(0, availableLength)}...${extension}`;
      }
    }
    
    return `${fileName.substring(0, maxLength - 3)}...`;
  };

  // Format date
  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('ko-KR', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Get analysis counts for all segments and current segment
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

  // Get current segment counts from segment detail
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

  const allCounts = getAllCounts(analysisData);
  const currentSegmentCounts = getCurrentSegmentCounts(currentSegmentDetail);

  const isVideo = !!selectedDocument && (selectedDocument.file_type.includes('video') || ['mp4', 'avi', 'mov', 'wmv', 'mkv', 'webm'].some(ext => selectedDocument.file_name.toLowerCase().endsWith(ext)));

  const smpteToSeconds = (smpte?: string): number | undefined => {
    if (!smpte) return undefined;
    // Normalize separators (support HH:MM:SS, MM:SS, optional frame ; or : or .)
    const norm = smpte.trim();
    // HH:MM:SS[;|:|.]FF
    let m = norm.match(/^(\d{1,2}):(\d{2}):(\d{2})(?:[;:\.](\d{1,2}))?$/);
    let h = 0, mnt = 0, sec = 0, frames = 0;
    if (m) {
      h = parseInt(m[1], 10);
      mnt = parseInt(m[2], 10);
      sec = parseInt(m[3], 10);
      frames = m[4] != null ? parseInt(m[4], 10) : 0;
    } else {
      // MM:SS
      m = norm.match(/^(\d{1,2}):(\d{2})$/);
      if (!m) return undefined;
      mnt = parseInt(m[1], 10);
      sec = parseInt(m[2], 10);
    }
    const DEFAULT_FPS = 30;
    return h * 3600 + mnt * 60 + sec + (frames / DEFAULT_FPS);
    };

  const seekSeconds = React.useMemo(() => {
    if (!isVideo) return undefined;
    const smpte = segmentStartTimecodes && selectedSegment != null ? segmentStartTimecodes[selectedSegment] : undefined;
    return smpteToSeconds(smpte);
  }, [isVideo, segmentStartTimecodes, selectedSegment]);

  return (
    <div className="relative h-full">
      <div className="absolute inset-0 overflow-y-auto">
        {/* Document Preview */}
        {!selectedDocument ? (
          <div className="h-full flex items-center justify-center p-6">
            <div
              onClick={onDocumentSelect}
              className="cursor-pointer transform transition-all duration-300 hover:scale-[1.02]"
            >
              <PinContainer 
                title="Select Document" 
                href="#" 
                containerClassName="h-64"
                onClick={(e) => e.preventDefault()}
              >
                <div className="flex flex-col p-6 tracking-tight text-slate-100/80 w-[18rem] h-[18rem] bg-gradient-to-b from-slate-800/50 to-slate-800/0 backdrop-blur-sm border border-slate-700/50 rounded-2xl items-center justify-center hover:border-purple-400/50 transition-all duration-300">
                  <div className="w-16 h-16 rounded-full border-2 border-dashed border-purple-400/50 flex items-center justify-center mb-6">
                    <FileText className="w-8 h-8 text-purple-400/70" />
                  </div>
                  <div className="text-xl font-semibold text-white mb-3">Select Document</div>
                  <div className="text-sm text-white/60 text-center max-w-[200px]">Select the document to analyze</div>
                  <div className="mt-4 text-xs text-purple-400/80">Click to select</div>
                </div>
              </PinContainer>
            </div>
          </div>
        ) : (
          <div className="flex flex-col p-4">
            {/* Document Header */}
            <div className="flex items-center justify-between mb-4 flex-shrink-0">
              <div className="flex items-center gap-3">
                <div className={`size-3 rounded-full ${
                  selectedDocument.status === 'completed' ? 'bg-emerald-500' : 'bg-yellow-500'
                }`} />
                <h3 className="text-lg font-semibold text-white" title={selectedDocument.file_name}>
                  {formatFileName(selectedDocument.file_name)}
                </h3>
                <Badge className={`text-xs ${
                  selectedDocument.file_type === 'pdf' 
                    ? 'bg-red-500/20 text-red-400 border-red-500/30'
                    : 'bg-blue-500/20 text-blue-400 border-blue-500/30'
                }`}>
                  {selectedDocument.file_type.toUpperCase()}
                </Badge>
              </div>
              <Button
                size="sm"
                variant="ghost"
                onClick={onDocumentSelect}
                className="text-white/70 hover:text-white hover:bg-white/10"
              >
                Change
              </Button>
            </div>

            {/* Document Preview Area */}
            <div className="flex-1 bg-white/5 rounded-xl border border-white/10 p-3 mb-3 overflow-auto max-h-[calc(100vh-400px)] relative">
              {isVideo ? (
                // Video player for video files
                <div className="flex flex-col h-full">
                  <div className="flex-1 flex items-center justify-center">
                    <SecureVideo
                      s3Uri={selectedDocument.file_uri}
                      indexId={indexId}
                      className="max-h-[30rem] max-w-[26rem] rounded-lg shadow-lg"
                      seekToSeconds={seekSeconds}
                    />
                  </div>
                  {/* Analysis Results Summary for Video - Compact with integrated buttons */}
                  <div className="w-full pt-1 mt-2">
                    <div className="px-3 py-2 bg-gradient-to-r from-slate-800/50 to-slate-700/50 rounded-md border border-white/10 space-y-3">
                      {/* Compact Analysis Type Buttons */}
                      <div className="grid grid-cols-3 gap-1.5">
                        <button
                          onClick={() => {
                            console.log('🔍 [DocumentPreview] BDA analysis clicked (video)', {
                              currentSegmentCounts,
                              bda: currentSegmentCounts.bda,
                              currentSegmentDetail,
                              analysis_results: currentSegmentDetail?.analysis_results
                            });
                            if (currentSegmentCounts.bda > 0) {
                              onAnalysisPopup({ type: 'bda', isOpen: true });
                            }
                          }}
                          disabled={currentSegmentCounts.bda === 0}
                          className={`flex items-center justify-between px-2 py-1.5 rounded border transition-all duration-200 group ${
                            currentSegmentCounts.bda > 0
                              ? 'bg-white/5 border-white/10 hover:bg-white/10 hover:border-white/20 cursor-pointer'
                              : 'bg-white/2 border-white/5 opacity-50 cursor-not-allowed'
                          }`}
                        >
                          <div className="flex items-center gap-1">
                            <div className={`w-1.5 h-1.5 rounded-full ${
                              currentSegmentCounts.bda > 0
                                ? 'bg-slate-400 group-hover:animate-pulse'
                                : 'bg-slate-600'
                            }`}></div>
                            <span className={`text-xs font-medium ${
                              currentSegmentCounts.bda > 0 ? 'text-slate-300' : 'text-slate-500'
                            }`}>BDA</span>
                          </div>
                          <span className={`text-sm font-bold transition-transform ${
                            currentSegmentCounts.bda > 0
                              ? 'text-white group-hover:scale-110'
                              : 'text-slate-600'
                          }`}>
                            {currentSegmentCounts.bda}
                          </span>
                        </button>

                        <button
                          onClick={() => {
                            console.log('🔍 [DocumentPreview] PDF analysis clicked (video)', {
                              currentSegmentCounts,
                              pdf: currentSegmentCounts.pdf,
                              currentSegmentDetail,
                              analysis_results: currentSegmentDetail?.analysis_results
                            });
                            if (currentSegmentCounts.pdf > 0) {
                              onAnalysisPopup({ type: 'pdf', isOpen: true });
                            }
                          }}
                          disabled={currentSegmentCounts.pdf === 0}
                          className={`flex items-center justify-between px-2 py-1.5 rounded border transition-all duration-200 group ${
                            currentSegmentCounts.pdf > 0
                              ? 'bg-white/5 border-white/10 hover:bg-white/10 hover:border-white/20 cursor-pointer'
                              : 'bg-white/2 border-white/5 opacity-50 cursor-not-allowed'
                          }`}
                        >
                          <div className="flex items-center gap-1">
                            <div className={`w-1.5 h-1.5 rounded-full ${
                              currentSegmentCounts.pdf > 0
                                ? 'bg-slate-400 group-hover:animate-pulse'
                                : 'bg-slate-600'
                            }`}></div>
                            <span className={`text-xs font-medium ${
                              currentSegmentCounts.pdf > 0 ? 'text-slate-300' : 'text-slate-500'
                            }`}>PDF</span>
                          </div>
                          <span className={`text-sm font-bold transition-transform ${
                            currentSegmentCounts.pdf > 0
                              ? 'text-white group-hover:scale-110'
                              : 'text-slate-600'
                          }`}>
                            {currentSegmentCounts.pdf}
                          </span>
                        </button>

                        <button
                          onClick={() => {
                            console.log('🔍 [DocumentPreview] AI analysis clicked (video)', {
                              currentSegmentCounts,
                              ai: currentSegmentCounts.ai,
                              currentSegmentDetail,
                              analysis_results: currentSegmentDetail?.analysis_results
                            });
                            if (currentSegmentCounts.ai > 0) {
                              onAnalysisPopup({ type: 'ai', isOpen: true });
                            }
                          }}
                          disabled={currentSegmentCounts.ai === 0}
                          className={`flex items-center justify-between px-2 py-1.5 rounded border transition-all duration-200 group ${
                            currentSegmentCounts.ai > 0
                              ? 'bg-white/5 border-white/10 hover:bg-white/10 hover:border-white/20 cursor-pointer'
                              : 'bg-white/2 border-white/5 opacity-50 cursor-not-allowed'
                          }`}
                        >
                          <div className="flex items-center gap-1">
                            <div className={`w-1.5 h-1.5 rounded-full ${
                              currentSegmentCounts.ai > 0
                                ? 'bg-slate-400 group-hover:animate-pulse'
                                : 'bg-slate-600'
                            }`}></div>
                            <span className={`text-xs font-medium ${
                              currentSegmentCounts.ai > 0 ? 'text-slate-300' : 'text-slate-500'
                            }`}>AI</span>
                          </div>
                          <span className={`text-sm font-bold transition-transform ${
                            currentSegmentCounts.ai > 0
                              ? 'text-white group-hover:scale-110'
                              : 'text-slate-600'
                          }`}>
                            {currentSegmentCounts.ai}
                          </span>
                        </button>
                      </div>

                      {/* Compact Segment Navigation for Video - moved below analysis results */}
                      {totalSegments > 1 && (
                        <div className="bg-white/5 rounded-lg p-2 border border-white/10">
                          <div className="flex items-center justify-between gap-2">
                            <Button
                              size="sm"
                              variant="ghost"
                              disabled={!selectedSegment || selectedSegment === 0}
                              onClick={() => {
                                const newSegment = (selectedSegment || 0) - 1;
                                onSegmentChange(newSegment);
                              }}
                              className="h-6 w-6 p-0 text-white/80 hover:text-white hover:bg-white/20"
                            >
                              ←
                            </Button>
                            
                            <select
                              value={selectedSegment || 0}
                              onChange={(e) => {
                                const newSegment = parseInt(e.target.value);
                                onSegmentChange(newSegment);
                              }}
                              className="flex-1 bg-white/10 border border-white/20 rounded px-2 py-1 text-white text-xs focus:outline-none"
                            >
                              {Array.from({ length: totalSegments }, (_, i) => (
                                <option key={i} value={i} className="bg-gray-800">
                                  Segment {i + 1}
                                </option>
                              ))}
                            </select>
                            
                            <span className="text-white/60 text-xs whitespace-nowrap">
                              {(selectedSegment || 0) + 1}/{totalSegments}
                            </span>
                            
                            <Button
                              size="sm"
                              variant="ghost"
                              disabled={!selectedSegment && selectedSegment !== 0 || selectedSegment >= totalSegments - 1}
                              onClick={() => {
                                const newSegment = (selectedSegment || 0) + 1;
                                onSegmentChange(newSegment);
                              }}
                              className="h-6 w-6 p-0 text-white/80 hover:text-white hover:bg-white/20"
                            >
                              →
                            </Button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ) : currentPageImageUrl && !imageLoading ? (
                // Image preview for documents
                <div className="flex flex-col h-full">
                  <div className="flex-1 flex items-center justify-center relative overflow-hidden">
                    {/* Image Controls */}
                    <div className="absolute top-2 right-2 z-10 flex gap-1 bg-black/60 backdrop-blur-sm rounded-lg p-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={onZoomOut}
                        className="h-8 w-8 p-0 text-white/80 hover:text-white hover:bg-white/20"
                        disabled={imageZoom <= 0.25}
                      >
                        <ZoomOut className="h-4 w-4" />
                      </Button>
                      <span className="px-2 py-1 text-white/80 text-xs font-mono">
                        {Math.round(imageZoom * 100)}%
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={onZoomIn}
                        className="h-8 w-8 p-0 text-white/80 hover:text-white hover:bg-white/20"
                        disabled={imageZoom >= 3}
                      >
                        <ZoomIn className="h-4 w-4" />
                      </Button>
                      <div className="w-px bg-white/20 mx-1"></div>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={onRotateLeft}
                        className="h-8 w-8 p-0 text-white/80 hover:text-white hover:bg-white/20"
                      >
                        <RotateCcw className="h-4 w-4" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={onRotateRight}
                        className="h-8 w-8 p-0 text-white/80 hover:text-white hover:bg-white/20"
                      >
                        <RotateCw className="h-4 w-4" />
                      </Button>
                      <div className="w-px bg-white/20 mx-1"></div>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={onResetImage}
                        className="h-8 w-8 p-0 text-white/80 hover:text-white hover:bg-white/20"
                        title="Reset"
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>

                    {/* Image Container */}
                    <div 
                      className="w-full h-full flex items-center justify-center"
                      onMouseMove={onMouseMove}
                      onMouseUp={onMouseUp}
                      onMouseLeave={onMouseUp}
                    >
                      <div
                        className="relative"
                        onMouseDown={onMouseDown}
                        style={{
                          transform: `scale(${imageZoom}) rotate(${imageRotation}deg) translate(${imagePosition.x}px, ${imagePosition.y}px)`,
                          cursor: imageZoom > 1 ? (isDragging ? 'grabbing' : 'grab') : 'pointer',
                          transition: isDragging ? 'none' : 'transform 0.2s ease-out'
                        }}
                      >
                        <div
                          className="cursor-pointer"
                          onClick={async () => {
                            if (imageZoom === 1) {
                              // Check SecureImage cache for presigned URL
                              const cache = (window as any).__secureImageCache__ as Map<string, { url: string; timestamp: number; expiration: number }>;
                              let presignedUrl = currentPageImageUrl;
                              
                              if (cache && currentPageImageUrl?.startsWith('s3://')) {
                                const cached = cache.get(currentPageImageUrl);
                                if (cached && cached.url) {
                                  presignedUrl = cached.url;
                                } else {
                                  // If not in cache, request new presigned URL
                                  try {
                                    const response = await documentApi.getPresignedUrlFromS3Uri(currentPageImageUrl, 3600, indexId);
                                    presignedUrl = response.presigned_url;
                                  } catch (error) {
                                    console.error('Failed to get presigned URL for zoomed image:', error);
                                    // Try original URL even if failed to get presigned URL
                                  }
                                }
                              }
                              
                              onSetZoomedImage({
                                isOpen: true,
                                imageData: presignedUrl || currentPageImageUrl || '',
                                mimeType: 'image/png'
                              });
                            }
                          }}
                        >
                          <SecureImage
                            s3Uri={currentPageImageUrl}
                            alt={`Page ${(selectedSegment || 0) + 1}`}
                            className="max-h-80 max-w-72 object-contain rounded-lg shadow-lg"
                            projectId={indexId}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                  {/* Analysis Results Summary - Compact with integrated buttons */}
                  <div className="w-full pt-1 mt-2">
                    <div className="px-3 py-2 bg-gradient-to-r from-slate-800/50 to-slate-700/50 rounded-md border border-white/10 space-y-3">
                      {/* Compact Analysis Type Buttons */}
                      <div className="grid grid-cols-3 gap-1.5">
                        <button
                          onClick={() => {
                            console.log('🔍 [DocumentPreview] BDA analysis clicked (image)', {
                              currentSegmentCounts,
                              bda: currentSegmentCounts.bda,
                              currentSegmentDetail,
                              analysis_results: currentSegmentDetail?.analysis_results
                            });
                            if (currentSegmentCounts.bda > 0) {
                              onAnalysisPopup({ type: 'bda', isOpen: true });
                            }
                          }}
                          disabled={currentSegmentCounts.bda === 0}
                          className={`flex items-center justify-between px-2 py-1.5 rounded border transition-all duration-200 group ${
                            currentSegmentCounts.bda > 0
                              ? 'bg-white/5 border-white/10 hover:bg-white/10 hover:border-white/20 cursor-pointer'
                              : 'bg-white/2 border-white/5 opacity-50 cursor-not-allowed'
                          }`}
                        >
                          <div className="flex items-center gap-1">
                            <div className={`w-1.5 h-1.5 rounded-full ${
                              currentSegmentCounts.bda > 0
                                ? 'bg-slate-400 group-hover:animate-pulse'
                                : 'bg-slate-600'
                            }`}></div>
                            <span className={`text-xs font-medium ${
                              currentSegmentCounts.bda > 0 ? 'text-slate-300' : 'text-slate-500'
                            }`}>BDA</span>
                          </div>
                          <span className={`text-sm font-bold transition-transform ${
                            currentSegmentCounts.bda > 0
                              ? 'text-white group-hover:scale-110'
                              : 'text-slate-600'
                          }`}>
                            {currentSegmentCounts.bda}
                          </span>
                        </button>

                        <button
                          onClick={() => {
                            console.log('🔍 [DocumentPreview] PDF analysis clicked (image)', {
                              currentSegmentCounts,
                              pdf: currentSegmentCounts.pdf,
                              currentSegmentDetail,
                              analysis_results: currentSegmentDetail?.analysis_results
                            });
                            if (currentSegmentCounts.pdf > 0) {
                              onAnalysisPopup({ type: 'pdf', isOpen: true });
                            }
                          }}
                          disabled={currentSegmentCounts.pdf === 0}
                          className={`flex items-center justify-between px-2 py-1.5 rounded border transition-all duration-200 group ${
                            currentSegmentCounts.pdf > 0
                              ? 'bg-white/5 border-white/10 hover:bg-white/10 hover:border-white/20 cursor-pointer'
                              : 'bg-white/2 border-white/5 opacity-50 cursor-not-allowed'
                          }`}
                        >
                          <div className="flex items-center gap-1">
                            <div className={`w-1.5 h-1.5 rounded-full ${
                              currentSegmentCounts.pdf > 0
                                ? 'bg-slate-400 group-hover:animate-pulse'
                                : 'bg-slate-600'
                            }`}></div>
                            <span className={`text-xs font-medium ${
                              currentSegmentCounts.pdf > 0 ? 'text-slate-300' : 'text-slate-500'
                            }`}>PDF</span>
                          </div>
                          <span className={`text-sm font-bold transition-transform ${
                            currentSegmentCounts.pdf > 0
                              ? 'text-white group-hover:scale-110'
                              : 'text-slate-600'
                          }`}>
                            {currentSegmentCounts.pdf}
                          </span>
                        </button>

                        <button
                          onClick={() => {
                            console.log('🔍 [DocumentPreview] AI analysis clicked (image)', {
                              currentSegmentCounts,
                              ai: currentSegmentCounts.ai,
                              currentSegmentDetail,
                              analysis_results: currentSegmentDetail?.analysis_results
                            });
                            if (currentSegmentCounts.ai > 0) {
                              onAnalysisPopup({ type: 'ai', isOpen: true });
                            }
                          }}
                          disabled={currentSegmentCounts.ai === 0}
                          className={`flex items-center justify-between px-2 py-1.5 rounded border transition-all duration-200 group ${
                            currentSegmentCounts.ai > 0
                              ? 'bg-white/5 border-white/10 hover:bg-white/10 hover:border-white/20 cursor-pointer'
                              : 'bg-white/2 border-white/5 opacity-50 cursor-not-allowed'
                          }`}
                        >
                          <div className="flex items-center gap-1">
                            <div className={`w-1.5 h-1.5 rounded-full ${
                              currentSegmentCounts.ai > 0
                                ? 'bg-slate-400 group-hover:animate-pulse'
                                : 'bg-slate-600'
                            }`}></div>
                            <span className={`text-xs font-medium ${
                              currentSegmentCounts.ai > 0 ? 'text-slate-300' : 'text-slate-500'
                            }`}>AI</span>
                          </div>
                          <span className={`text-sm font-bold transition-transform ${
                            currentSegmentCounts.ai > 0
                              ? 'text-white group-hover:scale-110'
                              : 'text-slate-600'
                          }`}>
                            {currentSegmentCounts.ai}
                          </span>
                        </button>
                      </div>

                      {/* Compact Segment Navigation for Images - moved below analysis results */}
                      {totalSegments > 1 && (
                        <div className="bg-white/5 rounded-lg p-2 border border-white/10">
                          <div className="flex items-center justify-between gap-2">
                            <Button
                              size="sm"
                              variant="ghost"
                              disabled={!selectedSegment || selectedSegment === 0}
                              onClick={() => {
                                const newSegment = (selectedSegment || 0) - 1;
                                onSegmentChange(newSegment);
                              }}
                              className="h-6 w-6 p-0 text-white/80 hover:text-white hover:bg-white/20"
                            >
                              ←
                            </Button>
                            
                            <select
                              value={selectedSegment || 0}
                              onChange={(e) => {
                                const newSegment = parseInt(e.target.value);
                                onSegmentChange(newSegment);
                              }}
                              className="flex-1 bg-white/10 border border-white/20 rounded px-2 py-1 text-white text-xs focus:outline-none"
                            >
                              {Array.from({ length: totalSegments }, (_, i) => (
                                <option key={i} value={i} className="bg-gray-800">
                                  Segment {i + 1}
                                </option>
                              ))}
                            </select>
                            
                            <span className="text-white/60 text-xs whitespace-nowrap">
                              {(selectedSegment || 0) + 1}/{totalSegments}
                            </span>
                            
                            <Button
                              size="sm"
                              variant="ghost"
                              disabled={!selectedSegment && selectedSegment !== 0 || selectedSegment >= totalSegments - 1}
                              onClick={() => {
                                const newSegment = (selectedSegment || 0) + 1;
                                onSegmentChange(newSegment);
                              }}
                              className="h-6 w-6 p-0 text-white/80 hover:text-white hover:bg-white/20"
                            >
                              →
                            </Button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="h-full flex items-center justify-center">
                  {imageLoading ? (
                    <div className="flex flex-col items-center gap-3">
                      <Loader2 className="h-8 w-8 animate-spin text-purple-400" />
                      <p className="text-white/60 text-sm">Loading preview...</p>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-3">
                      {selectedDocument && (selectedDocument.file_type.includes('video') || ['mp4', 'avi', 'mov', 'wmv', 'mkv', 'webm'].some(ext => selectedDocument.file_name.toLowerCase().endsWith(ext))) ? (
                        <>
                          <Play className="h-12 w-12 text-white/40" />
                          <p className="text-white/60 text-sm">Analysis is not available for video files</p>
                        </>
                      ) : (
                        <>
                          <FileText className="h-12 w-12 text-white/40" />
                          <p className="text-white/60 text-sm">Analysis is not available for this file</p>
                        </>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>


          </div>
        )}

        {/* Document Info & Actions - Only show when document is selected */}
        {selectedDocument && (
          <div className="p-3 border-t border-white/10 space-y-2">
            {/* Document Info */}
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-white/60">File Type:</span>
                  <span className="ml-2 text-white">{selectedDocument.file_type.toUpperCase()}</span>
                </div>
                <div>
                  <span className="text-white/60">File Size:</span>
                  <span className="ml-2 text-white">{formatFileSize(selectedDocument.file_size)}</span>
                </div>
                <div>
                  <span className="text-white/60">Created At:</span>
                  <span className="ml-2 text-white">{formatDate(selectedDocument.created_at)}</span>
                </div>
                <div>
                  <span className="text-white/60">Total Segments:</span>
                  <span className="ml-2 text-white">{selectedDocument.total_pages || 'N/A'}</span>
                </div>
              </div>
              
              {selectedDocument.description && (
                <SummarySection 
                  summary={selectedDocument.description}
                />
              )}


            </div>
          </div>
        )}
      </div>
    </div>
  );
}