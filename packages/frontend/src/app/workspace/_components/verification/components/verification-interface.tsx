"use client";

import React, { useState, useCallback, useRef, useEffect } from "react";
import { 
  Plus, 
  FileText, 
  Target, 
  Play, 
  Loader2, 
  CheckCircle, 
  XCircle, 
  AlertCircle,
  GripVertical,
  ChevronDown,
  ChevronRight,
  Eye,
  X,
  BarChart3
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card, CardContent } from "@/components/ui/card";
import { motion, AnimatePresence } from "framer-motion";
import { DocumentSelectionDialog } from "./document-selection-dialog";
import { DocumentDetailDialog } from "@/app/workspace/_components/documents/components/document-detail-dialog";
import { useDocumentDetail } from "@/hooks/use-document-detail";
import { Document } from "@/types/document.types";
import { verificationApi, VerificationClaim } from "@/lib/api";

// Types for persistent state
interface PersistentVerificationState {
  sourceDocuments: Document[];
  targetDocument: Document | null;
  messages: any[];
  verificationResults: VerificationResult[];
  isVerifying: boolean;
  isChatStarted: boolean;
}

interface VerificationResult extends VerificationClaim {
  sourceDocument?: Document;
}

interface VerificationInterfaceProps {
  indexId?: string;
  onOpenPdf?: (document: any) => void;
  onAttachToChat?: (pageInfo: {
    document_id: string;
    page_index: number;
    page_number: number;
    file_name: string;
  }) => void;
  persistentState?: PersistentVerificationState;
  onStateUpdate?: (updates: Partial<PersistentVerificationState>) => void;
}

interface VerificationProcessState {
  phase: 'init' | 'loading' | 'extraction' | 'verification' | 'summary' | 'completed' | 'error';
  message: string;
  progress: number;
  claims_count?: number;
  claim_index?: number;
  total_claims?: number;
  source_count?: number;
}

export function VerificationInterface({
  indexId,
  onOpenPdf,
  onAttachToChat,
  persistentState,
  onStateUpdate
}: VerificationInterfaceProps) {
  // Panel sizes (percentages)
  const [leftPanelWidth, setLeftPanelWidth] = useState(40);
  const rightPanelWidth = 100 - leftPanelWidth;

  // Dragging state for resizer
  const [isResizing, setIsResizing] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Dialog states
  const [showSourceDialog, setShowSourceDialog] = useState(false);
  const [showTargetDialog, setShowTargetDialog] = useState(false);

  // Collapsible sections state
  const [showVerifiedClaims, setShowVerifiedClaims] = useState(false);
  
  // Process state
  const [processState, setProcessState] = useState<VerificationProcessState | null>(null);
  
  // Document detail state
  const [viewingDocument, setViewingDocument] = useState<Document | null>(null);
  
  // Document detail hook
  const {
    selectedDocument,
    showDetail,
    analysisData,
    analysisLoading,
    showPdfViewer,
    setShowPdfViewer,
    imageLoading,
    selectedSegment,
    segmentStartTimecodes,
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
    handleMouseDown: detailMouseDown,
    handleMouseMove: detailMouseMove,
    handleMouseUp: detailMouseUp,
    toggleAnalysisExpand,
    handleAnalysisPopup
  } = useDocumentDetail(indexId || '');

  // Local state with fallbacks
  const state = persistentState || {
    sourceDocuments: [],
    targetDocument: null,
    messages: [],
    verificationResults: [],
    isVerifying: false,
    isChatStarted: false
  };

  // Update state helper
  const updateState = useCallback((updates: Partial<PersistentVerificationState>) => {
    if (onStateUpdate) {
      onStateUpdate(updates);
    }
  }, [onStateUpdate]);

  // Handle panel resizing
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  }, []);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!containerRef.current || !isResizing) return;

    const container = containerRef.current;
    const rect = container.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const percentage = (x / rect.width) * 100;

    const newLeft = Math.max(25, Math.min(50, percentage));
    setLeftPanelWidth(newLeft);
  }, [isResizing]);

  const handleMouseUp = useCallback(() => {
    setIsResizing(false);
  }, []);

  useEffect(() => {
    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isResizing, handleMouseMove, handleMouseUp]);

  // Handle source document selection
  const handleSourceSelection = useCallback((documents: Document[]) => {
    updateState({ sourceDocuments: documents });
  }, [updateState]);

  // Handle target document selection
  const handleTargetSelection = useCallback((documents: Document[]) => {
    updateState({ targetDocument: documents[0] || null });
  }, [updateState]);

  // Handle document removal
  const removeSourceDocument = useCallback((documentId: string) => {
    const updatedDocs = state.sourceDocuments.filter(doc => doc.document_id !== documentId);
    updateState({ sourceDocuments: updatedDocs });
  }, [state.sourceDocuments, updateState]);

  const removeTargetDocument = useCallback(() => {
    updateState({ targetDocument: null });
  }, [updateState]);

  // Handle document view
  const handleViewDocument = useCallback((document: Document) => {
    setViewingDocument(document);
    viewDocument(document);
  }, [viewDocument]);

  // Start verification
  const startVerification = useCallback(async () => {
    if (state.sourceDocuments.length === 0 || !state.targetDocument) return;

    setProcessState({
      phase: 'init',
      message: 'Initializing verification process...',
      progress: 0
    });

    updateState({ 
      isVerifying: true, 
      verificationResults: [],
      isChatStarted: true 
    });

    try {
      const response = await verificationApi.verifyContentStream({
        source_document_ids: state.sourceDocuments.map(doc => doc.document_id),
        target_document_id: state.targetDocument.document_id,
        index_id: indexId
      });

      if (!response.ok) {
        throw new Error(`Verification failed: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const currentResults: VerificationResult[] = [];

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              
              if (data === '[DONE]') {
                updateState({ isVerifying: false });
                break;
              }

              try {
                const parsed = JSON.parse(data);
                console.log('📡 Verification stream data:', parsed);

                // Handle process updates
                if (parsed.phase) {
                  setProcessState({
                    phase: parsed.phase,
                    message: parsed.message || '',
                    progress: parsed.progress || 0,
                    claims_count: parsed.claims_count,
                    claim_index: parsed.claim_index,
                    total_claims: parsed.total_claims,
                    source_count: parsed.source_count
                  });
                }

                if (parsed.type === 'claim_result' && parsed.claim) {
                  // Find corresponding source document
                  const sourceDoc = state.sourceDocuments.find(
                    doc => doc.document_id === parsed.claim.source_document_id
                  );
                  
                  const verificationResult: VerificationResult = {
                    ...parsed.claim,
                    sourceDocument: sourceDoc
                  };
                  
                  currentResults.push(verificationResult);
                  updateState({ 
                    verificationResults: [...currentResults]
                  });
                } else if (parsed.type === 'final_result') {
                  console.log('✅ Verification completed:', parsed);
                  
                  setProcessState({
                    phase: 'completed',
                    message: 'Verification completed successfully',
                    progress: 1
                  });
                  
                  // Process final results and ensure all claims are in state
                  if (parsed.claims && Array.isArray(parsed.claims)) {
                    const finalResults: VerificationResult[] = parsed.claims.map((claim: any) => {
                      const sourceDoc = state.sourceDocuments.find(
                        doc => doc.document_id === claim.source_document_id
                      );
                      return {
                        ...claim,
                        sourceDocument: sourceDoc
                      };
                    });
                    
                    
                    updateState({ 
                      isVerifying: false,
                      verificationResults: finalResults
                    });
                  } else {
                    updateState({ 
                      isVerifying: false 
                    });
                  }
                } else if (parsed.type === 'error') {
                  console.error('❌ Verification error:', parsed.error);
                  setProcessState({
                    phase: 'error',
                    message: parsed.error || 'Verification failed',
                    progress: 0
                  });
                  updateState({ 
                    isVerifying: false 
                  });
                  break;
                }
              } catch (e) {
                console.warn('Failed to parse verification stream data:', data, e);
              }
            }
          }
        }
      }
    } catch (error) {
      console.error('Verification error:', error);
      setProcessState({
        phase: 'error',
        message: 'Network or processing error occurred',
        progress: 0
      });
      updateState({ 
        isVerifying: false 
      });
    }
  }, [state.sourceDocuments, state.targetDocument, updateState, indexId]);

  // Calculate statistics
  const stats = {
    total: state.verificationResults.length,
    verified: state.verificationResults.filter(r => r.status === "VERIFIED").length,
    contradicted: state.verificationResults.filter(r => r.status === "CONTRADICTED").length,
    notFound: state.verificationResults.filter(r => r.status === "NOT_FOUND").length
  };

  // Get disabled documents for dialogs
  const getDisabledDocuments = (mode: 'source' | 'target'): Document[] => {
    if (mode === 'source') {
      return state.targetDocument ? [state.targetDocument] : [];
    } else {
      return state.sourceDocuments;
    }
  };

  return (
    <div 
      ref={containerRef}
      className="flex h-full overflow-hidden bg-black text-white relative select-none"
    >
      {/* Left Panel - Source & Target Documents */}
      <div 
        className="border-r border-white/10 flex flex-col h-full overflow-hidden"
        style={{ width: `${leftPanelWidth}%` }}
      >
        {/* Source Documents Section */}
        <div className="flex-1 flex flex-col border-b border-white/10 overflow-hidden">
          {/* Source Header */}
          <div className="h-16 px-4 border-b border-white/10 flex-shrink-0 flex items-center">
            <div className="flex items-center justify-between w-full">
              <div className="flex items-center gap-3">
                <h3 className="text-lg font-semibold text-white">Source Documents</h3>
                <Badge variant="outline" className="text-indigo-300 border-indigo-400/30 bg-indigo-500/10">
                  {state.sourceDocuments.length} selected
                </Badge>
              </div>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setShowSourceDialog(true)}
                className="text-indigo-400 hover:text-indigo-300 hover:bg-indigo-500/10"
              >
                <Plus className="h-4 w-4 mr-1" />
                Add
              </Button>
            </div>
          </div>

          {/* Source Documents List */}
          <div className="flex-1 overflow-hidden">
            <ScrollArea className="h-full p-4">
            {state.sourceDocuments.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-center">
              <FileText className="h-8 w-8 text-white/40 mb-2" />
              <p className="text-white/60 text-sm">No source documents selected</p>
              <p className="text-white/40 text-xs mt-1">Click &quot;Add&quot; button to select documents</p>
            </div>
          ) : (
            <div className="space-y-1">
              {state.sourceDocuments.map((doc) => (
                <div key={doc.document_id} className="flex items-center gap-2 p-2 bg-white/5 border border-white/10 rounded-md hover:bg-white/10 transition-colors">
                  <FileText className="h-3 w-3 text-indigo-400 flex-shrink-0" />
                  <div className="min-w-0 flex-1">
                    <h4 
                      className="text-white text-xs font-medium truncate"
                      title={doc.file_name}
                    >
                      {doc.file_name}
                    </h4>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleViewDocument(doc)}
                      className="h-5 w-5 p-0 text-indigo-400 hover:text-indigo-300"
                    >
                      <Eye className="h-2.5 w-2.5" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => removeSourceDocument(doc.document_id)}
                      className="h-5 w-5 p-0 text-red-400 hover:text-red-300"
                    >
                      <X className="h-2.5 w-2.5" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
            </ScrollArea>
          </div>
        </div>

        {/* Target Document Section */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Target Header */}
          <div className="h-16 px-4 border-b border-white/10 flex-shrink-0 flex items-center">
            <div className="flex items-center justify-between w-full">
              <div className="flex items-center gap-3">
                <h3 className="text-lg font-semibold text-white">Target Document</h3>
                <Badge variant="outline" className="text-purple-300 border-purple-400/30 bg-purple-500/10">
                  {state.targetDocument ? "1 selected" : "Not selected"}
                </Badge>
              </div>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setShowTargetDialog(true)}
                className="text-purple-400 hover:text-purple-300 hover:bg-purple-500/10"
              >
                <Target className="h-4 w-4 mr-1" />
                Select
              </Button>
            </div>
          </div>

          {/* Target Document */}
          <div className="flex-1 p-4 overflow-auto">
            {!state.targetDocument ? (
              <div className="flex flex-col items-center justify-center h-32 text-center">
                <Target className="h-8 w-8 text-white/40 mb-2" />
                <p className="text-white/60 text-sm">No target document selected</p>
                <p className="text-white/40 text-xs mt-1">Click &quot;Select&quot; button to choose a document</p>
              </div>
            ) : (
              <Card className="bg-white/5 border-white/10 hover:bg-white/10 transition-colors">
                <CardContent className="p-4">
                  <div className="flex items-center gap-3">
                    <FileText className="h-5 w-5 text-purple-400 flex-shrink-0" />
                    <div className="min-w-0 flex-1">
                      <h4 
                        className="text-white font-medium truncate max-w-[180px]"
                        title={state.targetDocument.file_name}
                      >
                        {state.targetDocument.file_name}
                      </h4>
                      <p className="text-white/60 text-sm">{state.targetDocument.file_type.toUpperCase()}</p>
                      <div className="flex items-center gap-2 mt-2">
                        <div className={`w-2 h-2 rounded-full ${
                          state.targetDocument.status === 'completed' ? 'bg-emerald-500' : 'bg-yellow-500'
                        }`} />
                        <span className="text-white/60 text-xs capitalize">{state.targetDocument.status}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleViewDocument(state.targetDocument!)}
                        className="h-6 w-6 p-0 text-purple-400 hover:text-purple-300"
                      >
                        <Eye className="h-3 w-3" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={removeTargetDocument}
                        className="h-6 w-6 p-0 text-red-400 hover:text-red-300"
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                  {state.targetDocument.description && (
                    <p className="text-white/60 text-sm mt-3 line-clamp-3">{state.targetDocument.description}</p>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>

      {/* Resizer */}
      <div
        className="w-1 bg-white/10 hover:bg-indigo-400/50 cursor-col-resize flex items-center justify-center group transition-colors"
        onMouseDown={handleMouseDown}
      >
        <GripVertical className="h-4 w-4 text-white/20 group-hover:text-indigo-400/70 transition-colors" />
      </div>

      {/* Right Panel - Verification Results */}
      <div 
        className="flex flex-col flex-1 h-full overflow-hidden"
      >
        {/* Header */}
        <div className="h-16 px-4 border-b border-white/10 flex-shrink-0 flex items-center">
          <div className="flex items-center justify-between w-full">
            <h3 className="text-lg font-semibold text-white">Verification Results</h3>
            {state.sourceDocuments.length > 0 && state.targetDocument && (
              <Button
                size="sm"
                onClick={startVerification}
                disabled={state.isVerifying}
                className="bg-gradient-to-r from-indigo-500 to-purple-500 hover:from-indigo-600 hover:to-purple-600 text-white"
              >
                {state.isVerifying ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Verifying...
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4 mr-2" />
                    Start Verification
                  </>
                )}
              </Button>
            )}
          </div>
        </div>

        {/* Statistics and Progress Section */}
        {(state.verificationResults.length > 0 || state.isVerifying) && (
          <div className="flex-shrink-0 p-4 border-b border-white/10 bg-black/30">
            {/* Statistics */}
            <div className="grid grid-cols-4 gap-2 text-center">
              <div className="bg-white/5 rounded p-2">
                <div className="text-white text-sm font-medium">{stats.total}</div>
                <div className="text-white/60 text-xs">Total</div>
              </div>
              <div className="bg-emerald-500/10 border border-emerald-500/20 rounded p-2">
                <div className="text-emerald-400 text-sm font-medium">{stats.verified}</div>
                <div className="text-emerald-400/60 text-xs">Verified</div>
              </div>
              <div className={`bg-red-500/10 border border-red-500/20 rounded p-2 flex flex-col items-center ${stats.contradicted > 0 ? "ring-2 ring-red-500/30 animate-pulse" : ""}`}>
                <div className="text-red-400 text-sm font-medium flex items-center justify-center gap-1">
                  {stats.contradicted > 0 && <XCircle className="h-3 w-3" />}
                  {stats.contradicted}
                </div>
                <div className="text-red-400/60 text-xs">Issues Found</div>
              </div>
              <div className="bg-yellow-500/10 border border-yellow-500/20 rounded p-2">
                <div className="text-yellow-400 text-sm font-medium">{stats.notFound}</div>
                <div className="text-yellow-400/60 text-xs">Not Found</div>
              </div>
            </div>

            {/* Verification Process Status */}
            {processState && state.isVerifying && (
              <div className="mt-4 p-3 bg-indigo-500/10 border border-indigo-500/20 rounded-lg">
                <div className="flex items-center gap-2 mb-2">
                  <BarChart3 className="h-4 w-4 text-indigo-400" />
                  <span className="text-indigo-400 text-sm font-medium">Verification Progress</span>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-white/80">{processState.message}</span>
                    <span className="text-indigo-400">{Math.round(processState.progress * 100)}%</span>
                  </div>
                  <div className="w-full bg-white/10 rounded-full h-1.5">
                    <div 
                      className="bg-gradient-to-r from-indigo-400 to-purple-400 h-1.5 rounded-full transition-all duration-300" 
                      style={{ width: `${processState.progress * 100}%` }}
                    />
                  </div>
                  {processState.claims_count && (
                    <div className="text-xs text-white/60">
                      Extracted {processState.claims_count} claims for verification
                    </div>
                  )}
                  {processState.claim_index !== undefined && processState.total_claims && (
                    <div className="text-xs text-white/60">
                      Processing claim {processState.claim_index + 1} of {processState.total_claims}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Results Content */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {!state.isChatStarted ? (
            <div className="flex-1 flex items-center justify-center p-6 overflow-auto">
              <div className="text-center max-w-md">
                <div className="w-16 h-16 rounded-full border-2 border-dashed border-indigo-400/50 flex items-center justify-center mx-auto mb-4">
                  <CheckCircle className="w-8 h-8 text-indigo-400/70" />
                </div>
                <h4 className="text-xl font-semibold text-white mb-3">Ready for Verification</h4>
                <p className="text-white/60 text-sm leading-relaxed">
                  Select source documents on the left and a target document on the right, 
                  then click &quot;Start Verification&quot; to begin analysis.
                </p>
              </div>
            </div>
          ) : (
            <>
              {/* Scrollable Results Area */}
              <div className="flex-1 overflow-hidden">
                <ScrollArea className="h-full p-4">
                  <div className="max-w-4xl mx-auto">
                    {state.isVerifying ? (
                      <div className="flex flex-col items-center justify-center h-32">
                        <Loader2 className="h-8 w-8 animate-spin text-indigo-400 mb-3" />
                        <p className="text-white/60 text-sm">{processState?.message || 'Processing verification...'}</p>
                        <p className="text-white/40 text-xs mt-1">This may take several minutes</p>
                      </div>
                    ) : (
                      <div className="space-y-4 pb-4">
                      {/* Issues Found */}
                      {state.verificationResults.filter(r => r.status === "CONTRADICTED").length > 0 && (
                        <div className="space-y-3">
                          <div className="flex items-center gap-2 p-2 bg-red-500/10 border border-red-500/30 rounded-lg">
                            <XCircle className="h-4 w-4 text-red-400" />
                            <h4 className="text-red-300 font-medium text-sm">
                              {state.verificationResults.filter(r => r.status === "CONTRADICTED").length} Issues Found
                            </h4>
                          </div>
                          <div className="space-y-2">
                            <AnimatePresence>
                              {state.verificationResults.filter(r => r.status === "CONTRADICTED").map((result, idx) => (
                                <motion.div
                                  key={result.id}
                                  initial={{ opacity: 0, y: 10 }}
                                  animate={{ opacity: 1, y: 0 }}
                                  exit={{ opacity: 0, y: -10 }}
                                  transition={{ duration: 0.2 }}
                                >
                                  <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-3">
                                    <div className="space-y-2">
                                      <div className="flex items-start gap-2">
                                        <div className="flex-shrink-0 w-5 h-5 bg-red-500/20 rounded-full flex items-center justify-center mt-0.5">
                                          <span className="text-red-400 text-xs font-bold">{idx + 1}</span>
                                        </div>
                                        <div className="flex-1 min-w-0">
                                          <div className="mb-2">
                                            <p className="text-red-300 text-xs font-medium mb-1">❌ Target Claim:</p>
                                            <p className="text-white text-sm bg-red-500/10 p-2 rounded border-l-2 border-red-400">
                                              {result.claim}
                                            </p>
                                          </div>
                                          <div className="mb-2">
                                            <p className="text-emerald-300 text-xs font-medium mb-1">✓ Source Evidence:</p>
                                            <p className="text-white text-sm bg-emerald-500/10 p-2 rounded border-l-2 border-emerald-400">
                                              {result.evidence}
                                            </p>
                                          </div>
                                          <div className="flex items-center justify-between text-xs">
                                            {result.confidence && (
                                              <span className="text-white/60">
                                                {Math.round(result.confidence * 100)}% confidence
                                              </span>
                                            )}
                                            {result.sourceDocument && (
                                              <button
                                                onClick={() => handleViewDocument(result.sourceDocument!)}
                                                className="text-indigo-400 hover:text-indigo-300 underline"
                                              >
                                                View Source
                                              </button>
                                            )}
                                          </div>
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                </motion.div>
                              ))}
                            </AnimatePresence>
                          </div>
                        </div>
                      )}

                      {/* Verified Claims (collapsible) */}
                      {state.verificationResults.filter(r => r.status === "VERIFIED").length > 0 && (
                        <div className="space-y-2">
                          <button
                            onClick={() => setShowVerifiedClaims(!showVerifiedClaims)}
                            className="flex items-center gap-2 w-full p-2 bg-emerald-500/10 border border-emerald-500/30 rounded-lg hover:bg-emerald-500/20 transition-colors"
                          >
                            <CheckCircle className="h-4 w-4 text-emerald-400" />
                            <span className="text-emerald-300 font-medium text-sm flex-1 text-left">
                              {state.verificationResults.filter(r => r.status === "VERIFIED").length} Verified Claims
                            </span>
                            {showVerifiedClaims ? (
                              <ChevronDown className="h-3 w-3 text-emerald-400" />
                            ) : (
                              <ChevronRight className="h-3 w-3 text-emerald-400" />
                            )}
                          </button>

                          <AnimatePresence>
                            {showVerifiedClaims && (
                              <motion.div
                                initial={{ opacity: 0, height: 0 }}
                                animate={{ opacity: 1, height: "auto" }}
                                exit={{ opacity: 0, height: 0 }}
                                transition={{ duration: 0.3 }}
                                className="mt-2 space-y-2"
                              >
                                {state.verificationResults.filter(r => r.status === "VERIFIED").map((result) => (
                                  <motion.div
                                    key={result.id}
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, y: -10 }}
                                    transition={{ duration: 0.2 }}
                                  >
                                    <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-2">
                                      <div className="flex items-start gap-2">
                                        <CheckCircle className="h-3 w-3 text-emerald-400 flex-shrink-0 mt-1" />
                                          <div className="flex-1 min-w-0">
                                            <p className="text-white text-sm">{result.claim}</p>
                                            {result.confidence && (
                                              <span className="text-white/60 text-xs mt-1 block">
                                                {Math.round(result.confidence * 100)}% confidence
                                              </span>
                                            )}
                                          </div>
                                        </div>
                                      </div>
                                  </motion.div>
                                ))}
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </div>
                      )}

                      {/* Not Found Items */}
                      {state.verificationResults.filter(r => r.status === "NOT_FOUND").length > 0 && (
                        <div>
                          <div className="flex items-center gap-2 mb-2 p-2 bg-yellow-500/10 rounded-lg border border-yellow-500/20">
                            <AlertCircle className="h-4 w-4 text-yellow-400" />
                            <h4 className="text-yellow-400 font-semibold text-sm">
                              Not Found ({state.verificationResults.filter(r => r.status === "NOT_FOUND").length})
                            </h4>
                          </div>
                          <div className="space-y-2">
                            {state.verificationResults.filter(r => r.status === "NOT_FOUND").map((result) => (
                              <Card key={result.id} className="bg-yellow-500/5 border-yellow-500/20 hover:border-yellow-500/30">
                                <CardContent className="p-3">
                                  <div className="flex items-start gap-3">
                                    <AlertCircle className="h-4 w-4 text-yellow-400 flex-shrink-0 mt-1" />
                                    <div className="flex-1">
                                      <p className="text-white text-sm">{result.claim}</p>
                                      <p className="text-yellow-400/80 text-xs mt-1">Related information not found in source documents</p>
                                    </div>
                                  </div>
                                </CardContent>
                              </Card>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                  </div>
                </ScrollArea>
              </div>

              {/* Verification Summary */}
              {state.verificationResults.length > 0 && !state.isVerifying && (
                <div className="flex-shrink-0 p-4 border-t border-white/10 bg-gradient-to-r from-slate-900/50 to-slate-800/50">
                  <div className="max-w-4xl mx-auto">
                    <div className="space-y-3">
                      <div className="flex items-center gap-2">
                        <CheckCircle className="h-4 w-4 text-indigo-400" />
                        <h4 className="text-white font-medium text-sm">Verification Summary</h4>
                      </div>
                      
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                        <div className="bg-white/5 rounded p-2">
                          <p className="text-white/60 mb-1">Total Items</p>
                          <p className="text-white font-medium">{stats.total}</p>
                        </div>
                        
                        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded p-2">
                          <p className="text-emerald-400/80 mb-1">Verified</p>
                          <p className="text-emerald-400 font-medium">{stats.verified}</p>
                        </div>
                        
                        <div className="bg-red-500/10 border border-red-500/20 rounded p-2">
                          <p className="text-red-400/80 mb-1">Issues</p>
                          <p className="text-red-400 font-medium">{stats.contradicted}</p>
                        </div>
                      </div>

                      {stats.contradicted > 0 ? (
                        <div className="bg-red-500/10 border border-red-500/20 rounded p-3">
                          <p className="text-red-300 text-xs">
                            ⚠️ <span className="font-semibold">{stats.contradicted} inaccurate information items</span> were found. 
                            Please review the details above and correct with accurate information.
                          </p>
                        </div>
                      ) : (
                        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded p-3">
                          <p className="text-emerald-300 text-xs">
                            ✅ <span className="font-semibold">All major information is accurate</span>. 
                            The target document content matches the source documents.
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Document Selection Dialogs */}
      <DocumentSelectionDialog
        isOpen={showSourceDialog}
        onClose={() => setShowSourceDialog(false)}
        indexId={indexId}
        title="Select Source Documents"
        description="Select multiple source documents to serve as verification references"
        selectionMode="multiple"
        selectedDocuments={state.sourceDocuments}
        disabledDocuments={getDisabledDocuments('source')}
        onSelectionChange={handleSourceSelection}
        onConfirm={handleSourceSelection}
      />

      <DocumentSelectionDialog
        isOpen={showTargetDialog}
        onClose={() => setShowTargetDialog(false)}
        indexId={indexId}
        title="Select Target Document"
        description="Select the document to be verified against source documents"
        selectionMode="single"
        selectedDocuments={state.targetDocument ? [state.targetDocument] : []}
        disabledDocuments={getDisabledDocuments('target')}
        onSelectionChange={handleTargetSelection}
        onConfirm={handleTargetSelection}
      />

      {/* Document Detail Dialog */}
      <DocumentDetailDialog
        document={viewingDocument}
        open={showDetail}
        onOpenChange={(open) => {
          if (!open) {
            closeDetail();
          }
        }}
        onClose={() => {
          closeDetail();
          setViewingDocument(null);
        }}
        analysisData={analysisData}
        selectedSegment={selectedSegment}
        totalSegments={
          analysisData.length > 0 
            ? Math.max(...analysisData.map((item: any) => 
                (typeof item.segment_index === 'number' ? item.segment_index : 
                 typeof item.page_index === 'number' ? item.page_index : 0)
              ), 0) + 1
            : (typeof viewingDocument?.total_pages === 'number' ? viewingDocument.total_pages : 1)
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
        onMouseDown={detailMouseDown}
        onMouseMove={detailMouseMove}
        onMouseUp={detailMouseUp}
        onAnalysisPopup={handleAnalysisPopup}
        onShowPdfViewer={() => setShowPdfViewer(true)}
        segmentStartTimecodes={segmentStartTimecodes}
      />
    </div>
  );
}