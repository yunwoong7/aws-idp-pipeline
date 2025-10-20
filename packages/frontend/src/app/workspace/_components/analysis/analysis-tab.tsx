"use client";

import React, { useState, useCallback, useEffect, useRef, useMemo } from "react";
import Image from "next/image";
import ReactDOM from "react-dom";
import { BarChart3, FileText, Loader2, X, Search, Hash, MessageCircle, Users, SendIcon, Sparkles, RotateCcw, Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useDocuments } from "@/hooks/use-documents";
import { useDocumentDetail } from "@/hooks/use-document-detail";
import { useAuth } from "@/contexts/auth-context";

import { Document } from "@/types/document.types";
import { AnalysisPopup } from "@/components/common/analysis-popup";
import { ChatBackground } from "@/components/ui/chat-background";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ResizablePanel } from "@/components/ui/resizable-panel";
import { useAlert } from "@/components/ui/alert";
import { DocumentPreview } from "./components/document-preview";
import { AnalysisInterface } from "./components/analysis-interface";
import { AnalysisHero } from "./components/analysis-hero";
import { motion, AnimatePresence } from "framer-motion";
import { v4 as uuidv4 } from 'uuid';
import { analysisAgentApi, systemApi, documentApi } from "@/lib/api";

// Import types from chat.types.ts
import type { Message, AttachedContent, FileAttachment } from "@/types/chat.types";

interface ZoomedImageState {
    isOpen: boolean;
    imageData: string;
    mimeType: string;
}

// Types for persistent state across tabs
interface PersistentAnalysisState {
    selectedDocument: Document | null;
    imageZoom: number;
    imageRotation: number;
    imagePosition: { x: number; y: number };
    messages: Message[];
    input: string;
    attachments: FileAttachment[];
    attachedContent: AttachedContent[];
    selectedSegment: number;
    isChatStarted: boolean;
}

interface AnalysisTabProps {
  indexId: string;
  onSelectDocument?: (fileName: string, documentId: string) => void;
  onAttachToChat?: (pageInfo: {
    document_id: string;
    page_index: number;
    page_number: number;
    file_name: string;
  }) => void;
  persistentState?: PersistentAnalysisState;
  onStateUpdate?: (updates: Partial<PersistentAnalysisState>) => void;
}

export function AnalysisTab({ indexId, onSelectDocument, onAttachToChat, persistentState, onStateUpdate }: AnalysisTabProps) {
  // Auth hook for user information
  const { user } = useAuth();

  // Alert hook for status warnings
  const { showWarning, AlertComponent } = useAlert();
  
  // Step 관리 헬퍼 함수들
  const getOrCreateStep = (messages: Message[], messageId: string, stepNumber: number, node: string) => {
    const message = messages.find(m => m.id === messageId);
    if (!message) return null;
    
    if (!message.steps) {
      message.steps = [];
    }
    
    let step = message.steps.find(s => s.step === stepNumber);
    if (!step) {
      step = {
        step: stepNumber,
        node: node,
        items: [],
        isComplete: false
      };
      message.steps.push(step);
    }
    
    return step;
  };
  
  // Debug indexId
  useEffect(() => {
    console.log('🏗️ indexId in AnalysisTab:', {
      indexId,
      hasIndexId: !!indexId
    });
  }, [indexId]);
  const [showAnalysisDetail, setShowAnalysisDetail] = useState(false);
  const [analysisPopup, setAnalysisPopup] = useState<{ type: 'bda' | 'pdf' | 'ai' | null; isOpen: boolean }>({ 
    type: null, 
    isOpen: false 
  });

  const [showDocumentSelect, setShowDocumentSelect] = useState(false);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [pendingDocument, setPendingDocument] = useState<Document | null>(null);

  // Get document list
  const { documents, loading, fetchDocuments } = useDocuments(indexId);

  // Get selected document details - use persistent state as primary source of truth
  const documentForHook = persistentState?.selectedDocument || null;
  const segmentForHook = persistentState?.selectedSegment ?? 0;
  
  const {
    selectedDocument: hookSelectedDocument,
    analysisData,
    analysisLoading,
    segmentStartTimecodes,
    selectedSegment: hookSelectedSegment,
    selectedSegmentId: hookSelectedSegmentId,
    currentPageImageUrl,
    imageLoading,
    handleSegmentChange: hookHandleSegmentChange,
    viewDocument: hookViewDocument
  } = useDocumentDetail(indexId, documentForHook, segmentForHook);

  // Use persistent state as primary source of truth
  const selectedDocument = persistentState?.selectedDocument || hookSelectedDocument;
  
  // Calculate total segments from analysis data or use total_pages as fallback
  const totalSegments = useMemo(() => {
    if (analysisData.length > 0) {
      const segmentIndexes = analysisData.map(item => item.segment_index).filter(idx => typeof idx === 'number');
      const maxSegment = segmentIndexes.length > 0 ? Math.max(...segmentIndexes) + 1 : 0;
      console.log('📊 Calculated total segments from analysis data:', { maxSegment, segmentIndexes });
      return maxSegment;
    }
    return selectedDocument?.total_pages ? parseInt(selectedDocument.total_pages) : 0;
  }, [analysisData, selectedDocument?.total_pages]);
  
  const imageZoom = persistentState?.imageZoom ?? 1;
  const imageRotation = persistentState?.imageRotation ?? 0;
  const imagePosition = persistentState?.imagePosition ?? { x: 0, y: 0 };
  const messages = useMemo(() => persistentState?.messages ?? [], [persistentState?.messages]);
  const input = persistentState?.input ?? "";
  const attachments = useMemo(() => persistentState?.attachments ?? [], [persistentState?.attachments]);
  const attachedContent = useMemo(() => persistentState?.attachedContent ?? [], [persistentState?.attachedContent]);
  const selectedSegment = persistentState?.selectedSegment ?? hookSelectedSegment ?? 0;
  const isChatStarted = persistentState?.isChatStarted ?? false;
  
  // Calculate selectedSegmentId from analysisData
  const selectedSegmentId = useMemo(() => {
    if (Array.isArray(analysisData) && analysisData.length > 0) {
      const match = analysisData.find(item => {
        const segmentIdx = (typeof item.segment_index === 'number' ? item.segment_index : undefined) ??
                        (typeof item.page_index === 'number' ? item.page_index : undefined);
        return segmentIdx === selectedSegment;
      });
      return match?.segment_id || null;
    }
    return hookSelectedSegmentId || null;
  }, [analysisData, selectedSegment, hookSelectedSegmentId]);

  // Segment detail state (similar to DocumentDetailDialog)
  const [currentSegmentDetail, setCurrentSegmentDetail] = useState<any>(null);
  const [segmentDetailLoading, setSegmentDetailLoading] = useState(false);

  // Local non-persistent states
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [lastDocumentId, setLastDocumentId] = useState<string | null>(null);

  // Debug logging for document detail state
  useEffect(() => {
    console.log('🔍 useDocumentDetail inputs and outputs:', {
      // Inputs to hook
      indexId,
      documentForHook: documentForHook?.document_id || 'null',
      segmentForHook,
      // Outputs from hook
      hookSelectedDocument: hookSelectedDocument?.document_id || 'null',
      analysisData: analysisData?.length || 0,
      analysisLoading,
      currentPageImageUrl: currentPageImageUrl ? 'present' : 'null',
      imageLoading,
      // Final computed values
      persistentSelectedDocument: persistentState?.selectedDocument?.document_id || 'null',
      finalSelectedDocument: selectedDocument?.document_id || 'null',
      selectedSegment
    });
  }, [indexId, documentForHook, segmentForHook, hookSelectedDocument, analysisData, analysisLoading, currentPageImageUrl, imageLoading, persistentState?.selectedDocument, selectedDocument, selectedSegment]);

  // Sync hookSelectedDocument changes to persistent state immediately
  useEffect(() => {
    if (hookSelectedDocument && hookSelectedDocument.document_id !== persistentState?.selectedDocument?.document_id) {
      console.log('🔄 Syncing new document selection and resetting chat:', hookSelectedDocument.file_name);
      onStateUpdate?.({ 
        selectedDocument: hookSelectedDocument,
        selectedSegment: 0,
        imageZoom: 1,
        imageRotation: 0,
        imagePosition: { x: 0, y: 0 },
        // Reset chat state when document changes
        messages: [],
        input: '',
        attachments: [],
        attachedContent: [],
        isChatStarted: false
      });
    }
  }, [hookSelectedDocument?.document_id, persistentState?.selectedDocument?.document_id, onStateUpdate, hookSelectedDocument]);

  // Force refresh analysis data if document is selected but no analysis data
  useEffect(() => {
    if (selectedDocument && (!analysisData || analysisData.length === 0) && !analysisLoading && hookViewDocument) {
      console.log('🔄 Force refreshing analysis data for:', selectedDocument.file_name);
      hookViewDocument(selectedDocument);
    }
  }, [selectedDocument, selectedDocument?.document_id, analysisData, analysisData?.length, analysisLoading, hookViewDocument]);

  // Fetch segment detail when selectedSegmentId changes (similar to DocumentDetailDialog)
  useEffect(() => {
    if (!selectedDocument || !selectedSegmentId || !indexId) {
      setCurrentSegmentDetail(null);
      return;
    }

    (async () => {
      setSegmentDetailLoading(true);
      try {
        console.log('🔍 [AnalysisTab] Fetching segment detail:', {
          indexId,
          documentId: selectedDocument.document_id,
          segmentId: selectedSegmentId,
          selectedSegment
        });

        const segmentDetail = await documentApi.getSegmentDetail(
          indexId,
          selectedDocument.document_id,
          selectedSegmentId
        );

        console.log('📄 [AnalysisTab] Segment detail loaded:', {
          segmentId: selectedSegmentId,
          analysis_results_count: segmentDetail?.analysis_results?.length || 0,
          segmentDetail
        });

        setCurrentSegmentDetail(segmentDetail);
      } catch (error) {
        console.error('❌ [AnalysisTab] Failed to load segment detail:', error);
        setCurrentSegmentDetail(null);
      } finally {
        setSegmentDetailLoading(false);
      }
    })();
  }, [selectedDocument, selectedSegmentId, indexId, selectedSegment]);

  // Reset image state when document changes
  useEffect(() => {
    const currentDocId = selectedDocument?.document_id;
    if (currentDocId && currentDocId !== lastDocumentId) {
      onStateUpdate?.({
        imageZoom: 1,
        imageRotation: 0,
        imagePosition: { x: 0, y: 0 }
      });
      setLastDocumentId(currentDocId);
    }
  }, [selectedDocument?.document_id, lastDocumentId, onStateUpdate]);

  // Chat state from page-backup.tsx (some local, some persistent)
  const [isStreaming, setIsStreaming] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // Local messages state for real-time updates during streaming
  const [localMessages, setLocalMessages] = useState<Message[]>(() => {
    // Initialize with persistent messages if available
    return messages.length > 0 ? messages : [];
  });

  // Prevent duplicate API calls
  const sendingRef = useRef(false);
  
  // Force clear localMessages when persistent messages are cleared
  useEffect(() => {
    if (messages.length === 0) {
      setLocalMessages([]);
    }
  }, [messages.length]);

  // Sync local messages with persistent state on initial load
  useEffect(() => {
    if (!isStreaming && messages.length > 0 && localMessages.length === 0) {
      setLocalMessages(messages);
    }
  }, [messages, isStreaming, localMessages.length]);
  
  // Sync persistent state when streaming ends
  useEffect(() => {
    if (!isStreaming && localMessages.length > messages.length) {
      // Only update if localMessages has more content (new messages)
      console.log('📤 Syncing localMessages to persistent state:', localMessages.length, 'vs', messages.length);
      onStateUpdate?.({ messages: localMessages });
    }
  }, [isStreaming, localMessages, localMessages.length, messages.length, onStateUpdate]);

  // UI state
  const [zoomedImage, setZoomedImage] = useState<ZoomedImageState>({ isOpen: false, imageData: "", mimeType: "" });

  // Safe input setter to ensure string type
  const handleSetInput = useCallback((value: string | any) => {
    onStateUpdate?.({ input: String(value || "") });
  }, [onStateUpdate]);

  // Chat reset function
  const handleChatReset = useCallback(async () => {
    try {
      console.log('🔄 Chat reset initiated');

      // Clear local messages first
      setLocalMessages([]);

      await systemApi.reinitialize();

      // Update persistent state to clear messages, input, and reset chat started state
      onStateUpdate?.({
        messages: [],
        input: "",
        attachments: [],
        attachedContent: [],
        isChatStarted: false // Reset to show welcome screen again
      });

      console.log('✅ Chat reset completed');
    } catch (error) {
      console.error('❌ Failed to reset chat:', error);
      // Still reset UI even if API call fails
      onStateUpdate?.({
        messages: [],
        input: "",
        attachments: [],
        attachedContent: [],
        isChatStarted: false
      });
    }
  }, [onStateUpdate]);

  // Actual document selection processing function
  const selectDocument = useCallback(async (document: Document) => {
    try {
      // If there was a chat, call reinit API
      if (selectedDocument && selectedDocument.document_id !== document.document_id && (localMessages.length > 0 || messages.length > 0)) {
        console.log('🔄 Reinitializing chat for document change');
        const userId = user?.email || 'anonymous';
        const newThreadId = `thread_${userId}_${indexId}`;

        await systemApi.reinitialize({
          force: true,
          reload_prompt: true,
          thread_id: newThreadId
        });
        
        // Reset chat state
        setLocalMessages([]);
        onStateUpdate?.({ 
          messages: [],
          input: "",
          attachments: [],
          attachedContent: [],
          isChatStarted: false // Reset to show hero screen
        });
        
        console.log('✅ Chat reinitialized successfully');
      }
      
      // Document selection processing - sync with persistent state and hook
      onStateUpdate?.({ selectedDocument: document });
      setShowDocumentSelect(false);
      if (hookViewDocument) {
        hookViewDocument(document);
      }
    } catch (error) {
      console.error('❌ Chat reinit failed:', error);
      // Use simple alert instead of ConfirmDialog (error is simple)
      alert('Chat reinit failed. Please try again.');
    }
  }, [selectedDocument, localMessages, messages, onStateUpdate, hookViewDocument, user, indexId]);

  // Document selection handler
  const handleDocumentSelect = useCallback((document: Document) => {
    console.log('📄 Document selected:', document);
    
    // Check if document is ready for analysis
    if (document.status !== 'completed') {
      showWarning('Document Not Ready', 'This document is not ready for analysis. Only completed documents can be analyzed.');
      return;
    }
    
    // If current selected document exists and trying to select a different document
    if (selectedDocument && selectedDocument.document_id !== document.document_id) {
      // Show confirmation dialog only if there are chat messages
      if (localMessages.length > 0 || messages.length > 0) {
        setPendingDocument(document);
        setShowConfirmDialog(true);
        return;
      }
    }
    
    // Document selection processing (direct selection or no messages)
    selectDocument(document);
  }, [selectedDocument, localMessages, messages, selectDocument, showWarning]);

  // Confirmation dialog confirmation handler
  const handleConfirmDocumentChange = useCallback(() => {
    if (pendingDocument) {
      selectDocument(pendingDocument);
      setPendingDocument(null);
    }
    setShowConfirmDialog(false);
  }, [pendingDocument, selectDocument]);

  // Confirmation dialog cancellation handler
  const handleCancelDocumentChange = useCallback(() => {
    setPendingDocument(null);
    setShowConfirmDialog(false);
  }, []);

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

  // Image manipulation functions
  const handleZoomIn = useCallback(() => {
    onStateUpdate?.({ imageZoom: Math.min(imageZoom + 0.25, 3) });
  }, [imageZoom, onStateUpdate]);

  const handleZoomOut = useCallback(() => {
    onStateUpdate?.({ imageZoom: Math.max(imageZoom - 0.25, 0.25) });
  }, [imageZoom, onStateUpdate]);

  const handleRotateLeft = useCallback(() => {
    onStateUpdate?.({ imageRotation: imageRotation - 90 });
  }, [imageRotation, onStateUpdate]);

  const handleRotateRight = useCallback(() => {
    onStateUpdate?.({ imageRotation: imageRotation + 90 });
  }, [imageRotation, onStateUpdate]);

  const handleResetImage = useCallback(() => {
    onStateUpdate?.({
      imageZoom: 1,
      imageRotation: 0,
      imagePosition: { x: 0, y: 0 }
    });
  }, [onStateUpdate]);

  // Mouse drag handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    if (imageZoom > 1) {
      setIsDragging(true);
      setDragStart({
        x: e.clientX - imagePosition.x,
        y: e.clientY - imagePosition.y
      });
      e.preventDefault();
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
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
      
      onStateUpdate?.({ imagePosition: { x: adjustedX, y: adjustedY } });
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
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

  // Get analysis counts from analysisData (from useDocumentDetail hook)
  const getAnalysisCounts = (analysisData: any) => {
    console.log('🔍 getAnalysisCounts - analysisData:', analysisData);
    
    if (!Array.isArray(analysisData) || analysisData.length === 0) {
      console.log('❌ No analysis data found');
      return { bda: 0, pdf: 0, ai: 0 };
    }
    
    console.log('✅ Found analysis items:', analysisData.length);
    
    // Count by tool_name
    let totalCounts = { bda: 0, pdf: 0, ai: 0 };
    
    analysisData.forEach((item: any, index: number) => {
      // console.log(`🔍 Item ${index}:`, {
      //   tool_name: item.tool_name,
      //   opensearch_doc_id: item.opensearch_doc_id,
      //   content_preview: item.content?.substring(0, 100) + '...'
      // });
      
      // Count based on tool_name
      if (item.tool_name === 'bda_indexer') {
        totalCounts.bda++;
      } else if (item.tool_name === 'pdf_text_extractor') {
        totalCounts.pdf++;
      } else if (item.tool_name === 'ai_analysis') {
        totalCounts.ai++;
      }
    });
    
    console.log('📊 Total analysis counts:', totalCounts);
    return totalCounts;
  };

  // Format analysis time for display
  const formatAnalysisTime = (date: Date) => {
    return date.toLocaleString('ko-KR', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };




  // Handle segment change with persistent state
  const handleSegmentChange = useCallback((newSegmentIndex: number) => {
    onStateUpdate?.({ selectedSegment: newSegmentIndex });
    if (hookHandleSegmentChange) {
      hookHandleSegmentChange(newSegmentIndex);
    }
  }, [onStateUpdate, hookHandleSegmentChange]);

  // File upload handling
  const handleFileUpload = async (files: FileList) => {
    if (!files || files.length === 0) return;

    const nonImageAttachments: FileAttachment[] = [];
    const imagePromises: Promise<FileAttachment>[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const fileId = uuidv4();

      if (file.type.startsWith('image/')) {
        imagePromises.push(new Promise((resolve, reject) => {
          try {
            const reader = new FileReader();
            reader.onload = () => {
              try {
                const result = reader.result as string;
                resolve({
                  id: uuidv4(),
                  file,
                  type: file.type,
                  previewUrl: result,
                  fileId
                });
              } catch (e) {
                reject(e);
              }
            };
            reader.onerror = (error) => reject(error);
            reader.readAsDataURL(file);
          } catch (e) {
            reject(e);
          }
        }));
      } else {
        nonImageAttachments.push({
          id: uuidv4(),
          file,
          type: file.type || getFileTypeFromExtension(file.name),
          fileId
        });
      }
    }

    try {
      const imageAttachments = await Promise.all(imagePromises);
      const finalAttachments = [...attachments, ...nonImageAttachments, ...imageAttachments];
      onStateUpdate?.({ attachments: finalAttachments });
    } catch (e) {
      console.error('Failed to read one or more images:', e);
      // Even if some images fail, attach what we have
      try {
        const settled = await Promise.allSettled(imagePromises);
        const okImages = settled
          .filter((s): s is PromiseFulfilledResult<FileAttachment> => s.status === 'fulfilled')
          .map(s => s.value);
        const finalAttachments = [...attachments, ...nonImageAttachments, ...okImages];
        onStateUpdate?.({ attachments: finalAttachments });
      } catch {}
    }

    // reset input value so selecting the same files again works
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const removeAttachment = (id: string) => {
    onStateUpdate?.({ attachments: attachments.filter(att => att.id !== id) });
  };

  const handleAttachButtonClick = () => {
    fileInputRef.current?.click();
  };

  // Helper function to get file type from extension
  const getFileTypeFromExtension = (filename: string): string => {
    const ext = filename.split('.').pop()?.toLowerCase();
    const mimeTypes: { [key: string]: string } = {
      'pdf': 'application/pdf',
      'doc': 'application/msword',
      'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'txt': 'text/plain',
      'csv': 'text/csv',
      'json': 'application/json',
      'xml': 'application/xml',
      'md': 'text/markdown',
      'png': 'image/png',
      'jpg': 'image/jpeg',
      'jpeg': 'image/jpeg',
      'gif': 'image/gif',
      'webp': 'image/webp'
    };
    return mimeTypes[ext || ''] || 'application/octet-stream';
  };

  // Send message handler (from page-backup.tsx)
  const handleSendMessage = useCallback(async (message?: string) => {
    // Prevent duplicate calls
    if (sendingRef.current) {
      console.log('⚠️ Duplicate send attempt blocked');
      return;
    }

    // Check if selected document is ready for analysis
    if (selectedDocument && selectedDocument.status !== 'completed') {
      showWarning('Document Not Ready', 'This document is not ready for analysis. Only completed documents can be analyzed.');
      return;
    }

    let inputText = String(message || input || "");

    if (!inputText.trim() && attachedContent.length === 0 && attachments.length === 0) return;

    // Set sending flag
    sendingRef.current = true;

    // Check for reset or if chat hasn't started yet (hero screen)
    if (!isChatStarted) {
      console.log('🔄 Hero screen detected, reinitializing chat');

      // Reinitialize with thread_id
      try {
        const userId = user?.email || 'anonymous';
        const threadId = `thread_${userId}_${indexId}`;

        await systemApi.reinitialize({
          force: true,
          reload_prompt: true,
          thread_id: threadId
        });
        console.log('✅ Chat reinitialized successfully');
      } catch (error) {
        console.error('❌ Failed to reinitialize chat:', error);
      }

      // Clear local and persistent messages
      setLocalMessages([]);
      onStateUpdate?.({
        messages: [],
        isChatStarted: true
      });
    }

    const attachmentStrings = attachedContent.map((item: any) => {
      if (item.type === 'document') {
        return `[Document: ${item.file_name}, document_id: ${item.document_id}]`;
      }
      if (item.type === 'image') {
        return `[Image: Page ${item.page_number} of ${item.file_name}, document_id: ${item.document_id}, page_index: ${item.page_index}]`;
      }
      return '';
    }).filter(Boolean).join('\n');

    const finalMessageToSend = `${attachmentStrings}\n\n${inputText}`.trim();

    const wasNotStarted = !isChatStarted;

    if (!isChatStarted) {
      onStateUpdate?.({ isChatStarted: true });
    }

    const userMessage: Message = {
      id: uuidv4(),
      sender: "user",
      content: inputText,
      contentItems: [{
        id: uuidv4(),
        type: "text",
        content: inputText,
        timestamp: Date.now()
      }],
      attachedContent: [...attachedContent],
      attachedFiles: [...attachments],
      timestamp: Date.now()
    };

    // Update local messages for real-time display
    // If this is the first message after reset, start with a new array
    if (wasNotStarted) {
      setLocalMessages([userMessage]);
    } else {
      setLocalMessages(prev => [...prev, userMessage]);
    }
    onStateUpdate?.({ 
      input: "",
      attachedContent: [],
      attachments: []
    });
    setIsStreaming(true);
    
    // Focus on input field after sending
    setTimeout(() => {
      if (inputRef.current) {
        inputRef.current.focus();
      }
    }, 100);
    
    try {
      const response = await analysisAgentApi.sendMessage({
        message: finalMessageToSend,
        files: attachments.map(att => att.file),
        index_id: indexId || '',
        document_id: selectedDocument?.document_id,
        segment_id: selectedSegmentId
      });
      
      if (!response.ok) {
        throw new Error(`API request failed: ${response.status}`);
      }
      
      if (!response.body) {
        throw new Error("Streaming response not received.");
      }
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      
      let buffer = '';
      let currentStep = -1;
      let currentMessageId: string | null = null;
      let accumulatedToolUses = new Map<string, any>();
      let references: any[] = [];
      
      let currentContentItems: any[] = [];
      let accumulatedText = '';
      let mainTextItemId = uuidv4();
      let accumulatedToolInputs = new Map<string, string>();
      
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          buffer += decoder.decode(value);
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.slice(6).trim();
              
              if (dataStr === '[DONE]') {
                console.log('🏁 Stream completed');
                
                // Mark current message as completed
                if (currentMessageId) {
                  setLocalMessages(prev => prev.map(msg => 
                    msg.id === currentMessageId 
                      ? { ...msg, isStreaming: false }
                      : msg
                  ));
                }
                
                // Process any remaining buffer before exiting
                if (buffer.trim()) {
                  console.log('📦 Processing remaining buffer:', buffer);
                  // Process remaining buffer here if needed
                }
                return;
              }
              
              if (dataStr === '') continue;
              
              try {
                const data = JSON.parse(dataStr);
                console.log('📦 Raw streaming data:', data);
                
                // Handle new chunk-based format
                if (data.chunk && Array.isArray(data.chunk)) {
                  // Initialize new message if this is the start
                  if (!currentMessageId && data.chunk.length > 0) {
                    currentMessageId = uuidv4();
                    currentContentItems = [];
                    accumulatedText = '';
                    mainTextItemId = uuidv4();
                    references = [];
                    
                    const newMessage: Message = {
                      id: currentMessageId,
                      sender: "ai",
                      content: "",
                      contentItems: [],
                      steps: [],  // Step 기반 구조 추가
                      references: [],
                      timestamp: Date.now(),
                      isStreaming: true
                    };
                    
                    setLocalMessages(prev => [...prev, newMessage]);
                  }
                  
                  // Step 기반 처리를 위한 메타데이터 추출
                  const strandsStep = data.metadata?.strands_step || 0;
                  const strandsNode = data.metadata?.strands_node || 'agent';
                  const stepType = data.metadata?.type;
                  
                  // console.log(`📊 Step metadata: step=${strandsStep}, node=${strandsNode}, type=${stepType}`);
                  // console.log(`📊 Chunk array length: ${data.chunk.length}`, data.chunk.map(c => `${c.type}:${c.text?.length || 'no-text'}`));
                  
                  // Process each chunk with Step support
                  for (let chunkIndex = 0; chunkIndex < data.chunk.length; chunkIndex++) {
                    const chunk = data.chunk[chunkIndex];
                    // console.log(`🔄 Processing chunk ${chunkIndex}/${data.chunk.length - 1}:`, chunk.type, chunk.text?.length);
                    // Step 기반 텍스트 처리
                    if (chunk.type === 'text' && chunk.text && currentMessageId && stepType === 'ai_response') {
                      setLocalMessages(prev => {
                        const messages = [...prev];
                        const message = messages.find(m => m.id === currentMessageId);
                        if (!message) return prev;
                        
                        // Step 가져오기 또는 생성
                        if (!message.steps) message.steps = [];
                        let step = message.steps.find(s => s.step === strandsStep);
                        if (!step) {
                          step = {
                            step: strandsStep,
                            node: strandsNode,
                            items: [],
                            isComplete: false
                          };
                          message.steps.push(step);
                          // console.log(`🆕 Created new step ${strandsStep} with node ${strandsNode}`);
                        }
                        
                        // Step 내의 텍스트 아이템 찾기 또는 생성
                        let textItem = step.items.find((item: any) => item.type === 'text');
                        if (!textItem) {
                          textItem = {
                            id: uuidv4(),
                            uniqueId: `${currentMessageId}-${strandsStep}-text-0`,
                            type: 'text',
                            content: '',
                            timestamp: Date.now()
                          };
                          step.items.push(textItem);
                          // console.log(`📄 Created new text item for step ${strandsStep}`);
                        }
                        
                        // 중복 텍스트 추가 방지 - 이미 끝에 같은 텍스트가 있으면 스킵
                        const alreadyAdded = textItem.content.endsWith(chunk.text);
                        if (alreadyAdded) {
                          // console.log(`⚠️ Duplicate chunk detected, skipping: "${chunk.text}"`);
                          return prev;
                        }
                        
                        // 텍스트 누적
                        textItem.content += chunk.text;
                        
                        // Step-based 렌더링을 사용하므로 message.content는 사용하지 않음
                        // 각 Step의 텍스트는 해당 Step 내에서만 관리됨
                        message.content = ""; // Step-based rendering 사용
                        
                        // console.log(`📝 Step ${strandsStep} text update (length: ${chunk.text.length}):`, chunk.text.substring(0, 50) + (chunk.text.length > 50 ? '...' : ''));
                        // console.log(`📝 Current step text total length: ${textItem.content.length}`);
                        return messages;
                      });
                    }
                    
                    // Step 기반 도구 사용 처리
                    else if (chunk.type === 'tool_use' && currentMessageId && stepType === 'tool_use') {
                      if (!chunk.name && !chunk.input) {
                        continue; // Skip empty chunks
                      }

                      // Step과 index를 조합하여 고유한 key 생성
                      const toolUseKey = `tool_step${strandsStep}_${chunk.index || 0}`;
                      let toolUseId = chunk.id || `${currentMessageId}_step${strandsStep}_tool${chunk.index || 0}_${Date.now()}`;
                      
                      // Find existing tool by ID or name/index
                      const existingTool = currentContentItems.find(item => 
                        item.type === 'tool_use' && (
                          (toolUseId && item.id === toolUseId) ||
                          (item.tempKey === toolUseKey)
                        )
                      );
                      
                      if (existingTool) {
                        toolUseId = existingTool.id;
                      } else if (!toolUseId) {
                        toolUseId = uuidv4();
                      }
                      
                      // Accumulate input if provided
                      if (chunk.input !== undefined) {
                        const currentInput = accumulatedToolInputs.get(toolUseKey) || '';
                        const newInput = currentInput + chunk.input;
                        accumulatedToolInputs.set(toolUseKey, newInput);
                        
                        // Try to validate if the accumulated input forms valid JSON
                        try {
                          JSON.parse(newInput);
                          // If valid JSON, we can use it directly
                        } catch (error) {
                          // Still accumulating, not complete JSON yet
                          console.log(`⚠️ Accumulating tool input for ${toolUseKey}, length: ${newInput.length}`);
                        }
                      }
                      
                      // Only create/update if we have meaningful data
                      if (chunk.name || accumulatedToolInputs.has(toolUseKey)) {
                        const finalInput = accumulatedToolInputs.get(toolUseKey) || chunk.input || '';
                        const toolUse = {
                          id: toolUseId,
                          type: "tool_use" as const,
                          name: chunk.name || existingTool?.name || '도구 실행 중',
                          input: finalInput,
                          tempKey: toolUseKey,
                          timestamp: Date.now()
                        };
                        
                        // console.log('🔧 Processing tool_use chunk:', toolUseKey);
                        
                        // Update Steps structure
                        setLocalMessages(messages => {
                          return messages.map(msg => {
                            if (msg.id !== currentMessageId) return msg;

                            // Step 가져오기 또는 생성
                            if (!msg.steps) msg.steps = [];
                            let step = msg.steps.find(s => s.step === strandsStep);
                            if (!step) {
                              step = {
                                step: strandsStep,
                                node: strandsNode,
                                items: [],
                                isComplete: false
                              };
                              msg.steps.push(step);
                            }

                            // Add uniqueId for React stability
                            const toolUseWithUniqueId = {
                              ...toolUse,
                              uniqueId: `${currentMessageId}-${strandsStep}-tool-${toolUseKey}`
                            };

                            // Update step items (preserve collapsed state only)
                            const existingStepIndex = step.items.findIndex((item: any) => item.id === toolUseId || item.tempKey === toolUseKey);
                            if (existingStepIndex >= 0) {
                              const existingItem = step.items[existingStepIndex] as any;
                              step.items[existingStepIndex] = {
                                ...toolUseWithUniqueId,
                                // Preserve collapsed state (use existing value or default to true)
                                collapsed: existingItem.hasOwnProperty('collapsed') ? existingItem.collapsed : true
                              };
                            } else {
                              step.items.push({
                                ...toolUseWithUniqueId,
                                collapsed: true // Default to collapsed for new items
                              });
                            }

                            // Also update contentItems for backward compatibility (preserve collapsed state only)
                            const nextContentItems = [...msg.contentItems];
                            const existingIndexLocal = nextContentItems.findIndex((item: any) => item.id === toolUseId || item.tempKey === toolUseKey);
                            if (existingIndexLocal >= 0) {
                              const existingItem = nextContentItems[existingIndexLocal] as any;
                              nextContentItems[existingIndexLocal] = {
                                ...toolUseWithUniqueId,
                                // Preserve collapsed state (use existing value or default to true)
                                collapsed: existingItem.hasOwnProperty('collapsed') ? existingItem.collapsed : true
                              };
                            } else {
                              nextContentItems.push({
                                ...toolUseWithUniqueId,
                                collapsed: true // Default to collapsed for new items
                              });
                            }

                            // console.log(`🔧 Step ${strandsStep} tool added:`, chunk.name);
                            return { ...msg, contentItems: nextContentItems };
                          });
                        });

                        // Sync local working array for subsequent chunk processing
                        currentContentItems = [...currentContentItems];
                        const existingIndexLocal = currentContentItems.findIndex((item: any) => item.id === toolUseId || item.tempKey === toolUseKey);
                        if (existingIndexLocal >= 0) {
                          currentContentItems[existingIndexLocal] = toolUse;
                        } else {
                          currentContentItems.push(toolUse);
                        }
                      }
                    }
                    
                    // Handle tool_result within chunks  
                    else if (chunk.type === 'tool_result' && currentMessageId) {
                      // Find or create tool_result (avoid duplicates)
                      const resultKey = `result_step${strandsStep}_${chunk.index || 0}_${chunk.tool_use_id || 'default'}`;
                      const existingResult = currentContentItems.find(item => 
                        item.type === 'tool_result' && (
                          item.tool_use_id === chunk.tool_use_id ||
                          item.resultKey === resultKey
                        )
                      );
                      
                      const toolResultId = existingResult?.id || `${currentMessageId}_step${strandsStep}_result${chunk.index || 0}_${Date.now()}`;
                      const toolResult = {
                        id: toolResultId,
                        type: "tool_result" as const,
                        tool_use_id: chunk.tool_use_id || '',
                        result: chunk.text || chunk.content || JSON.stringify(chunk) || '',
                        resultKey: resultKey,
                        timestamp: Date.now()
                      };
                      
                      // console.log('📋 Processing tool_result chunk:', toolResult);
                      
                      // Update Steps structure
                      setLocalMessages(messages => {
                        return messages.map(msg => {
                          if (msg.id !== currentMessageId) return msg;

                          // Step 가져오기 또는 생성
                          if (!msg.steps) msg.steps = [];
                          let step = msg.steps.find(s => s.step === strandsStep);
                          if (!step) {
                            step = {
                              step: strandsStep,
                              node: strandsNode,
                              items: [],
                              isComplete: false
                            };
                            msg.steps.push(step);
                          }

                          // Add uniqueId for React stability
                          const toolResultWithUniqueId = {
                            ...toolResult,
                            uniqueId: `${currentMessageId}-${strandsStep}-result-${resultKey}`
                          };

                          // Update step items (preserve collapsed state and append streaming content)
                          const existingStepIndex = step.items.findIndex((item: any) => item.id === toolResultId);
                          if (existingStepIndex >= 0) {
                            const existingItem = step.items[existingStepIndex] as any;
                            step.items[existingStepIndex] = {
                              ...toolResultWithUniqueId,
                              // Preserve collapsed state (use existing value or default to true)
                              collapsed: existingItem.hasOwnProperty('collapsed') ? existingItem.collapsed : true,
                              // Append streaming content
                              result: ((existingItem as any).result || '') + ((toolResultWithUniqueId as any).result || '')
                            };
                          } else {
                            step.items.push({
                              ...toolResultWithUniqueId,
                              collapsed: true // Default to collapsed for new items
                            });
                          }

                          // Also update contentItems for backward compatibility (preserve collapsed state)
                          const updatedContentItems = [...msg.contentItems];
                          const existingIndex = updatedContentItems.findIndex(item => item.id === toolResultId);
                          
                          if (existingIndex >= 0) {
                            const existingItem = updatedContentItems[existingIndex] as any;
                            updatedContentItems[existingIndex] = {
                              ...toolResultWithUniqueId,
                              // Preserve collapsed state (use existing value or default to true)
                              collapsed: existingItem.hasOwnProperty('collapsed') ? existingItem.collapsed : true,
                              // Append streaming content
                              result: ((existingItem as any).result || '') + ((toolResultWithUniqueId as any).result || '')
                            };
                          } else {
                            updatedContentItems.push({
                              ...toolResultWithUniqueId,
                              collapsed: true // Default to collapsed for new items
                            });
                          }

                          // console.log(`📋 Step ${strandsStep} tool result added`);
                          return { ...msg, contentItems: updatedContentItems };
                        });
                      });
                      
                      // Update local working array
                      const updatedContentItems = [...currentContentItems];
                      const existingIndex = updatedContentItems.findIndex(item => item.id === toolResultId);
                      
                      if (existingIndex >= 0) {
                        updatedContentItems[existingIndex] = toolResult;
                      } else {
                        updatedContentItems.push(toolResult);
                      }
                      
                      currentContentItems = updatedContentItems;
                    }
                  }
                  
                  // Check if this is the end (empty chunk array)
                  if (data.chunk.length === 0 && currentMessageId) {
                    console.log('🏁 Stream end detected, stopping streaming for message:', currentMessageId);
                    setLocalMessages(prev => prev.map(msg => 
                      msg.id === currentMessageId 
                        ? { ...msg, isStreaming: false }
                        : msg
                    ));
                    currentMessageId = null; // Reset for next message
                  }
                }
                
                else if (data.type === 'tool_use' && currentMessageId) {
                  const toolUseId = data.id;
                  const toolUse = {
                    id: toolUseId,
                    type: "tool_use" as const,
                    name: data.name,
                    input: data.input,
                    timestamp: Date.now()
                  };
                  
                  accumulatedToolUses.set(toolUseId, toolUse);
                  
                  const updatedContentItems = [...currentContentItems];
                  const existingIndex = updatedContentItems.findIndex(item => item.id === toolUseId);
                  
                  if (existingIndex >= 0) {
                    updatedContentItems[existingIndex] = toolUse;
                  } else {
                    updatedContentItems.push(toolUse);
                  }
                  
                  setLocalMessages(prev => prev.map(msg => 
                    msg.id === currentMessageId 
                      ? { ...msg, contentItems: updatedContentItems }
                      : msg
                  ));
                }
                
                else if (data.type === 'tool_result' && currentMessageId) {
                  const toolResultId = uuidv4();
                  const toolResult = {
                    id: toolResultId,
                    type: "tool_result" as const,
                    tool_use_id: data.tool_use_id,
                    result: data.content,
                    timestamp: Date.now()
                  };
                  
                  const updatedContentItems = [...currentContentItems, toolResult];
                  
                  setLocalMessages(prev => prev.map(msg => 
                    msg.id === currentMessageId 
                      ? { ...msg, contentItems: updatedContentItems }
                      : msg
                  ));
                  
                  currentContentItems = updatedContentItems;
                }
                
                else if (data.type === 'references' && currentMessageId) {
                  references = data.references || [];
                  
                  setLocalMessages(prev => prev.map(msg => 
                    msg.id === currentMessageId 
                      ? { ...msg, references }
                      : msg
                  ));
                }
                
                else if (data.type === 'step_end' && currentMessageId) {
                  console.log('🏁 Step end received, stopping streaming for message:', currentMessageId);
                  setLocalMessages(prev => prev.map(msg => 
                    msg.id === currentMessageId 
                      ? { ...msg, isStreaming: false }
                      : msg
                  ));
                }
                
              } catch (parseError) {
                console.warn('Failed to parse streaming data:', parseError, 'Raw data:', dataStr);
              }
            }
          }
        }
      } finally {
        setIsStreaming(false);
      }

    } catch (error) {
      console.error('Chat error:', error);

      const errorMessage: Message = {
        id: uuidv4(),
        sender: "ai",
        content: "죄송합니다. 오류가 발생했습니다. 다시 시도해주세요.",
        contentItems: [{
          id: uuidv4(),
          type: "text",
          content: "죄송합니다. 오류가 발생했습니다. 다시 시도해주세요.",
          timestamp: Date.now()
        }],
        references: [],
        timestamp: Date.now(),
        isStreaming: false
      };
      setLocalMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsStreaming(false);
      sendingRef.current = false;
      onStateUpdate?.({ attachments: [] });

      // 스트리밍 종료 후 입력 필드에 포커스
      setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.focus();
        }
      }, 200);
    }
  }, [input, attachedContent, isChatStarted, attachments, indexId, onStateUpdate, selectedDocument, selectedSegmentId, showWarning, user]);

  // Remove attached content handler
  const handleRemoveAttachedContent = (id: string) => {
    onStateUpdate?.({ attachedContent: attachedContent.filter(content => content.id !== id) });
  };

  // Note: Tool collapse/expand functionality has been replaced with popup modal

  return (
    <div className="h-full flex flex-col bg-black text-white relative">
      <ChatBackground />
      
      {/* Header Section */}
      <div className="flex-shrink-0 p-4 border-b border-white/10 bg-gradient-to-r from-slate-900/50 to-slate-800/50 backdrop-blur-sm relative z-20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="relative">
              <div className="relative w-12 h-12 bg-gradient-to-br from-blue-500/20 to-purple-600/20 border border-blue-400/30 rounded-2xl flex items-center justify-center">
                <BarChart3 className="h-6 w-6 text-white" />
              </div>
              <div className="absolute -inset-1 bg-gradient-to-br from-blue-500/50 to-purple-600/50 rounded-2xl blur opacity-60"></div>
            </div>
            <div>
              <h2 className="text-xl font-bold text-white bg-gradient-to-r from-blue-300 to-purple-300 bg-clip-text text-transparent">
                Document Analysis
              </h2>
            </div>
          </div>

          {/* Reset Button */}
          {isChatStarted && (
            <button
              type="button"
              onClick={handleChatReset}
              className="flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 transition-all duration-200 backdrop-blur-sm group"
              title="Reset Chat"
            >
              <RotateCcw className="w-4 h-4 text-orange-400 group-hover:text-orange-300 transition-colors" />
              <span className="text-sm text-white/60 group-hover:text-white/80">Reset</span>
            </button>
          )}
        </div>
      </div>
      
      <ResizablePanel className="flex-1 relative z-10" defaultLeftWidth={40} minLeftWidth={20} maxLeftWidth={50}>
        {/* Left Panel - Document Preview */}
        <DocumentPreview
          selectedDocument={selectedDocument}
          indexId={indexId}
          imageZoom={imageZoom}
          imageRotation={imageRotation}
          imagePosition={imagePosition}
          currentPageImageUrl={currentPageImageUrl}
          imageLoading={imageLoading}
          isDragging={isDragging}
          dragStart={dragStart}
          selectedSegment={selectedSegment}
          totalSegments={totalSegments}
          analysisData={analysisData}
          analysisLoading={analysisLoading}
          currentSegmentDetail={currentSegmentDetail}
          zoomedImage={zoomedImage}
          onDocumentSelect={() => setShowDocumentSelect(true)}
          onZoomIn={handleZoomIn}
          onZoomOut={handleZoomOut}
          onRotateLeft={handleRotateLeft}
          onRotateRight={handleRotateRight}
          onResetImage={handleResetImage}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onSegmentChange={handleSegmentChange}
          onAnalysisPopup={setAnalysisPopup}
          onSetZoomedImage={setZoomedImage}
          setIsDragging={setIsDragging}
          setDragStart={setDragStart}
          segmentStartTimecodes={segmentStartTimecodes}
        />

        {/* Right Panel - Chat */}
        <div className="relative h-full border-l border-white/10">
          {selectedDocument ? (
            <div className="h-full flex flex-col relative">
              {!isChatStarted ? (
                /* Welcome Screen with Hero Component */
                <motion.div 
                  className="absolute inset-0 flex flex-col items-center justify-center bg-gradient-to-br from-black/60 via-black/50 to-black/60 backdrop-blur-md z-10"
                  initial={{ opacity: 1 }}
                  animate={{ opacity: isChatStarted ? 0 : 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.5 }}
                  style={{ pointerEvents: isChatStarted ? 'none' : 'auto' }}
                >
                  <div className="w-full max-w-4xl px-8">
                    <AnalysisHero
                      title="Talk to the Document Analysis AI"
                      subtitle={`Analyze ${selectedDocument?.file_name || 'the document'} and answer your questions. AI deeply understands documents and provides insights.`}
                      examples={[
                        "Summarize the key content of this document",
                        "Find and explain specific information",
                        "Analyze the main data in the document",
                        "Provide important insights from this document"
                      ]}
                      onAttachClick={handleAttachButtonClick}
                      onExampleClick={(example) => {
                        handleSetInput(example);
                        handleSendMessage(example);
                      }}
                    />

                    {/* Fixed-height attachment preview strip (hero area, no vertical shift) */}
                    <div className="h-10 px-4 flex items-center gap-2">
                      <div className="flex items-center gap-2 w-full overflow-x-auto hide-scrollbar rounded-xl bg-white/5/50 border border-white/10 backdrop-blur-md shadow-sm px-3 py-1">
                        {attachments && attachments.length > 0 && (
                          <div className="flex items-center gap-2 text-[10px] text-white/70">
                            <div className="px-2 py-0.5 rounded-full bg-white/10 border border-white/15">
                              {attachments.length} files
                            </div>
                            <div className="w-px h-4 bg-white/10" />
                          </div>
                        )}
                        {attachments && attachments.length > 0 && attachments.map((att) => (
                          <div key={att.id} className="relative group">
                            <div className="absolute inset-0 rounded-md bg-gradient-to-br from-cyan-400/10 to-purple-500/10 opacity-0 group-hover:opacity-100 transition-opacity" />
                            {att.type?.startsWith('image/') && att.previewUrl ? (
                              <Image
                                src={att.previewUrl}
                                alt={att.file.name}
                                width={28}
                                height={28}
                                unoptimized
                                className="w-7 h-7 rounded object-cover border border-white/20 transform transition-transform duration-200 group-hover:scale-105"
                                title={att.file.name}
                              />
                            ) : (
                              <div className="w-7 h-7 rounded bg-white/10 border border-white/20 flex items-center justify-center transform transition-transform duration-200 group-hover:scale-105" title={att.file.name}>
                                <FileText className="w-4 h-4 text-white/60" />
                              </div>
                            )}
                            <button
                              className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-black/70 border border-white/20 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-black/90"
                              onClick={() => removeAttachment(att.id)}
                              aria-label="Remove attachment"
                            >
                              <X className="w-3 h-3 text-white/80" />
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                    
                    {/* Attached file previews (hero view) */}
                    {/* Hide attachment preview in hero to prevent layout shift */}

                    {/* Search Bar - Enhanced Style */}
                    <motion.div 
                      className="relative mt-8"
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.8, duration: 0.8 }}
                    >
                      <div className="relative bg-gradient-to-r from-gray-900/90 to-gray-800/90 border border-white/20 rounded-full backdrop-blur-xl shadow-2xl">
                        <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/10 via-purple-500/10 to-pink-500/10 rounded-full animate-pulse" />
                        <div className="relative p-4 flex items-center flex-nowrap gap-2">
                          <div className="flex-shrink-0">
                            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-cyan-500/20 to-purple-500/20 flex items-center justify-center">
                              <Sparkles className="w-5 h-5 text-cyan-400 animate-pulse" />
                            </div>
                          </div>
                          {/* Attach file button inside hero search bar */}
                          <button
                            onClick={handleAttachButtonClick}
                            className="p-2 rounded-full hover:bg-white/5 transition-all group"
                            title="Attach file"
                            aria-label="Attach file"
                          >
                            <Paperclip className="w-5 h-5 text-green-400 group-hover:text-green-300 transition-colors" />
                          </button>

                          {/* keep inputs from wrapping: */}
                          <input
                            type="text"
                            value={input}
                            onChange={(e) => handleSetInput(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                handleSendMessage();
                              }
                            }}
                            placeholder="Ask me anything about the document..."
                            disabled={isStreaming}
                            className="bg-transparent flex-1 min-w-0 outline-none text-white placeholder:text-white/50 text-lg font-medium"
                          />
                          <button
                            onClick={() => handleSendMessage()}
                            disabled={!input.trim() || isStreaming}
                            className="ml-2 p-3 rounded-full bg-gradient-to-r from-cyan-500 to-purple-500 hover:from-cyan-600 hover:to-purple-600 transition-all disabled:opacity-50 disabled:cursor-not-allowed transform hover:scale-105 active:scale-95"
                          >
                            <SendIcon className="w-5 h-5 text-white" />
                          </button>
                        </div>
                        {/* Attachment strip removed in hero to prevent any vertical shift */}
                      </div>
                    </motion.div>
                    
                  </div>
                </motion.div>
              ) : null}

              {/* Chat Area - moves to bottom with animation */}
              <motion.div 
                className="flex-1 bg-black/20 overflow-hidden min-h-0"
                initial={false}
                animate={{
                  y: isChatStarted ? 0 : '50%',
                  scale: isChatStarted ? 1 : 0.95,
                }}
                transition={{ 
                  type: "spring", 
                  stiffness: 300, 
                  damping: 30,
                  duration: 0.8 
                }}
              >
                <AnalysisInterface
                  messages={(() => {
                    // Use localMessages during streaming, persistent messages otherwise
                    const displayMessages = isStreaming ? localMessages : (localMessages.length > messages.length ? localMessages : messages);
                    return displayMessages;
                  })()}
                  input={input}
                  setInput={handleSetInput}
                  onSendMessage={handleSendMessage}
                  isStreaming={isStreaming}
                  attachments={attachments}
                  attachedContent={attachedContent}
                  onRemoveAttachedContent={handleRemoveAttachedContent}
                  onFileUpload={(e) => e.target.files && handleFileUpload(e.target.files)}
                  onRemoveAttachment={removeAttachment}
                  onAttachButtonClick={handleAttachButtonClick}
                  fileInputRef={fileInputRef as React.RefObject<HTMLInputElement>}
                  height="h-[calc(100vh-160px)]"
                  showScrollButton={showScrollButton}
                  onScrollToBottom={() => setShowScrollButton(false)}
                  zoomedImage={zoomedImage}
                  onSetZoomedImage={setZoomedImage}
                  onImageClick={() => {}}
                  onPdfClick={() => {}}
                  externalTextareaRef={inputRef}
                  indexId={indexId}
                  selectedDocument={selectedDocument ? {
                    document_id: selectedDocument.document_id,
                    file_name: selectedDocument.file_name,
                    file_type: selectedDocument.file_type,
                    status: selectedDocument.status
                  } : null}
                  selectedSegment={selectedSegment}
                  onChatReset={handleChatReset}
                />
              </motion.div>
            </div>
          ) : (
            <div className="h-full flex items-center justify-center">
              <div className="text-center text-white/60">
                <BarChart3 className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>Select a document to start analysis</p>
              </div>
            </div>
          )}
        </div>
      </ResizablePanel>

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.txt,.rtf,.odt,.dwg,.dxf,.csv,.json,.xml,.md,.png,.jpg,.jpeg,.gif,.bmp,.tiff,.tif,.webp,.mp4,.avi,.mov,.wmv,.flv,.mkv,.webm,.3gp,.mp3,.wav,.flac,.m4a,.aac,.ogg,.wma,.aiff"
        onChange={(e) => e.target.files && handleFileUpload(e.target.files)}
        className="hidden"
      />

      {/* Enhanced image zoom modal */}
      <AnimatePresence>
        {zoomedImage && zoomedImage.isOpen && (
          <motion.div 
            className="fixed inset-0 bg-black/95 flex items-center justify-center z-50 backdrop-blur-md"
            onClick={() => setZoomedImage(prev => ({ ...prev, isOpen: false }))}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            <motion.div 
              className="relative max-w-[95vw] max-h-[95vh] overflow-auto"
              initial={{ scale: 0.8, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.8, y: 20 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
              onClick={(e: React.MouseEvent) => e.stopPropagation()}
            >
              <div className="relative max-w-[90vw] max-h-[90vh] mx-auto">
                <div className="absolute -inset-1 bg-gradient-to-r from-blue-500/30 via-cyan-500/30 to-blue-600/30 rounded-xl blur-lg opacity-75"></div>
                
                <div className="relative bg-white dark:bg-gray-900 rounded-xl overflow-hidden shadow-2xl">
                  <div className="relative max-w-full max-h-[85vh] mx-auto">
                    <Image 
                      src={(() => {
                        if (zoomedImage.imageData.startsWith('http://') || zoomedImage.imageData.startsWith('https://')) {
                          return zoomedImage.imageData;
                        } else {
                          return `data:${zoomedImage.mimeType};base64,${zoomedImage.imageData}`;
                        }
                      })()}
                      alt="Zoomed image"
                      width={1600}
                      height={1200}
                      unoptimized
                      className="max-w-full max-h-[85vh] object-contain mx-auto block"
                      onClick={(e: React.MouseEvent) => e.stopPropagation()}
                    />
                  </div>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Document Selection Popup */}
      {showDocumentSelect && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center">
          <div className="bg-black border border-white/20 rounded-xl w-[60vw] max-h-[80vh] flex flex-col">
            {/* Popup Header */}
            <div className="p-4 border-b border-white/10">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-white">Select Document</h2>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowDocumentSelect(false)}
                  className="text-white/70 hover:text-white"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Document List */}
            <div className="flex-1 overflow-auto p-4">
              {loading ? (
                <div className="flex items-center justify-center h-32">
                  <Loader2 className="h-8 w-8 animate-spin text-purple-400" />
                </div>
              ) : (
                <div className="space-y-2">
                  {documents.map((document) => (
                    <div
                      key={document.document_id}
                      onClick={() => handleDocumentSelect(document)}
                      className="cursor-pointer p-4 bg-white/5 hover:bg-white/10 rounded-lg border border-white/10 hover:border-purple-400/50 transition-all duration-200"
                    >
                      <div className="flex items-center gap-3">
                        {/* Status indicator */}
                        <div className={`size-3 rounded-full ${
                          document.status === 'completed' ? 'bg-emerald-500' : 'bg-yellow-500'
                        }`} />
                        
                        {/* File info */}
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="font-medium text-white truncate">
                              {document.file_name}
                            </h3>
                            <Badge className={`text-xs ${
                              document.file_type === 'pdf' 
                                ? 'bg-red-500/20 text-red-400 border-red-500/30'
                                : 'bg-blue-500/20 text-blue-400 border-blue-500/30'
                            }`}>
                              {document.file_type.toUpperCase()}
                            </Badge>
                          </div>
                          
                          <div className="flex items-center gap-4 text-sm text-white/60">
                            <span>{formatFileSize(document.file_size)}</span>
                            {document.total_pages && <span>{document.total_pages} segments</span>}
                            <span>{formatDate(document.created_at)}</span>
                          </div>
                        </div>
                        
                        {/* Select arrow */}
                        <div className="text-white/40">
                          →
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Analysis Detail Popup */}
      {showAnalysisDetail && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center">
          <div className="bg-black border border-white/20 rounded-xl w-[90vw] h-[80vh] p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">Analysis Detail Result</h2>
              <Button
                variant="ghost"
                onClick={() => setShowAnalysisDetail(false)}
                className="text-white/70 hover:text-white"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="text-white/60 text-center">
              {selectedDocument ? (
                <div className="space-y-4">
                  <p>📄 {selectedDocument.file_name}</p>
                  <div className="grid grid-cols-3 gap-4 mt-6">
                    <div className="bg-blue-500/20 p-4 rounded-lg">
                      <h3 className="text-blue-400 font-semibold mb-2">BDA Analysis</h3>
                      <p className="text-sm text-white/70">
                        {getAnalysisCounts(analysisData).bda} BDA analysis results.
                      </p>
                    </div>
                    <div className="bg-green-500/20 p-4 rounded-lg">
                      <h3 className="text-green-400 font-semibold mb-2">PDF Analysis</h3>
                      <p className="text-sm text-white/70">
                        {getAnalysisCounts(analysisData).pdf} PDF analysis results.
                      </p>
                    </div>
                    <div className="bg-purple-500/20 p-4 rounded-lg">
                      <h3 className="text-purple-400 font-semibold mb-2">AI Analysis</h3>
                      <p className="text-sm text-white/70">
                        {getAnalysisCounts(analysisData).ai} AI analysis results.
                      </p>
                    </div>
                  </div>
                </div>
              ) : (
                <p>Select a document to analyze.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Document Change Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showConfirmDialog}
        onClose={handleCancelDocumentChange}
        onConfirm={handleConfirmDocumentChange}
        title="Document Change Confirmation"
        message={`Changing the document to "${pendingDocument?.file_name || 'New Document'}" will reset all current chat contents.\nContinue?`}
        confirmText="Change"
        cancelText="Cancel"
        variant="destructive"
      />

      {/* Analysis Result Popup: Using common AnalysisPopup */}
      <AnalysisPopup
        isOpen={analysisPopup.isOpen}
        type={analysisPopup.type}
        selectedSegment={selectedSegment}
        analysisData={currentSegmentDetail ? currentSegmentDetail.analysis_results || [] : []}
        onClose={() => setAnalysisPopup({ type: null, isOpen: false })}
      />
      
      {/* Alert Component */}
      {AlertComponent}
    </div>
  );
}