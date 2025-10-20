"use client";

import React, { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  MessageCircle,
  Loader2,
  CheckCircle,
  Clock,
  AlertCircle,
  Send,
  Sparkles,
  FileText,
  RotateCcw,
  Zap,
  Brain,
  Settings,
  ArrowDown,
  X,
  ChevronDown,
  ChevronRight,
  Wrench,
  Cog,
  Paperclip
} from "lucide-react";
import { cn } from "@/lib/utils";
import { MarkdownRenderer } from "@/components/ui/markdown-renderer";
import Image from 'next/image';
import { MessageLoading } from "@/components/ui/message-loading";
import { searchApi, documentApi } from "@/lib/api";
import { SearchHero } from "./search-hero";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { FileAttachment } from "@/types/chat.types";
import { v4 as uuidv4 } from 'uuid';

// Types for SearchAgent workflow
interface PlanStep {
  title: string;
  tool_name?: string;
  tool_args?: Record<string, any>;
  description: string;
  status: "pending" | "executing" | "completed" | "failed";
  result?: string;
  execution_time?: number;
}

interface Plan {
  requires_tool: boolean;
  direct_response?: string;
  overview: string;
  tasks: PlanStep[];
  reasoning?: string;
}

interface Reference {
  id: string;
  type: string;
  value: string;
  title?: string;
  description?: string;
  display_name?: string;
  image_uri?: string;
  file_uri?: string;
  document_id?: string;
  file_name?: string;
  segment_index?: number;
  page_index?: number;
  page_id?: string;
  score?: number;
}

interface Message {
  id: string;
  sender: "user" | "ai";
  content: string;
  timestamp: number;
  plan?: Plan;
  references?: Reference[];
  isStreaming?: boolean;
  isPlanning?: boolean;  // Planning in progress
  planningStep?: number;  // Current planning step (0-4)
  planningBuffer?: string;  // Accumulated planning tokens
  planningPreview?: {
    overview?: string;
    tasks?: string[];
  };
  isAnalyzingImage?: boolean;  // Image analysis in progress
  imageAnalysisResult?: string;  // Image analysis result
  attachedImages?: FileAttachment[];  // Attached images for user messages
}

// Types for persistent state across tabs
interface PersistentSearchState {
  messages: Message[];
  input: string;
  currentPhase: "idle" | "planning" | "executing" | "responding";
  toolCollapsed: Record<string, boolean>;
  isChatStarted: boolean;
  attachments?: FileAttachment[];
}

interface SearchInterfaceProps {
  indexId?: string;
  onOpenPdf?: (document: any) => void;
  onAttachToChat?: (pageInfo: {
    document_id: string;
    page_index: number;
    page_number: number;
    file_name: string;
  }) => void;
  onReferenceClick?: (reference: any) => void;
  persistentState?: PersistentSearchState;
  onStateUpdate?: (updates: Partial<PersistentSearchState>) => void;
  onChatReset?: () => void;
}

export function SearchInterface({ indexId, onOpenPdf, onAttachToChat, onReferenceClick, persistentState, onStateUpdate, onChatReset: externalChatReset }: SearchInterfaceProps) {
  // Use persistent state as primary source of truth with memoization
  const messages = useMemo(() => persistentState?.messages ?? [], [persistentState?.messages]);
  const input = persistentState?.input ?? "";
  const currentPhase = persistentState?.currentPhase ?? "idle";
  const toolCollapsed = useMemo(() => persistentState?.toolCollapsed ?? {}, [persistentState?.toolCollapsed]);
  const isChatStarted = persistentState?.isChatStarted ?? false;
  const attachments = useMemo(() => persistentState?.attachments ?? [], [persistentState?.attachments]);

  // Local state for UI-only concerns
  const [isStreaming, setIsStreaming] = useState(false);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [isNearBottom, setIsNearBottom] = useState(true); // Track if user is near bottom
  const [isComposing, setIsComposing] = useState(false);
  const [sourceDialogOpen, setSourceDialogOpen] = useState(false);
  const [sourceDialogData, setSourceDialogData] = useState<{ title?: string; references?: Reference[] }>({});
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [imageAnalysisCollapsed, setImageAnalysisCollapsed] = useState<Record<string, boolean>>({});

  // File input ref for file attachments
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Local messages state for real-time updates during streaming
  const [localMessages, setLocalMessages] = useState<Message[]>(() => {
    // Initialize with persistent messages if available
    return messages.length > 0 ? messages : [];
  });

  // Prevent duplicate API calls
  const sendingRef = useRef(false);

  // Safe input setter to ensure string type
  const handleSetInput = useCallback((value: string | any) => {
    onStateUpdate?.({ input: String(value || "") });
  }, [onStateUpdate]);

  // Update tool collapse state
  const handleToolCollapse = useCallback((messageId: string, collapsed: boolean) => {
    const currentToolCollapsed = persistentState?.toolCollapsed ?? {};
    const newToolCollapsed = { ...currentToolCollapsed, [messageId]: collapsed };
    onStateUpdate?.({ toolCollapsed: newToolCollapsed });
  }, [persistentState?.toolCollapsed, onStateUpdate]);

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
      console.log('📤 Syncing localMessages to persistent state:', {
        localMessagesCount: localMessages.length,
        messagesCount: messages.length,
        lastLocalMessage: localMessages[localMessages.length - 1],
        hasReferencesInLast: localMessages[localMessages.length - 1]?.references?.length
      });
      onStateUpdate?.({ messages: localMessages });
    }
  }, [isStreaming, localMessages, localMessages.length, messages.length, onStateUpdate]);

  // Handle reference click - supports both single reference and array of references
  const handleReferenceClick = useCallback((referencesOrSingle: any | any[], title?: string) => {
    const references = Array.isArray(referencesOrSingle) ? referencesOrSingle : [referencesOrSingle];
    
    // If we have onReferenceClick prop and it's a single reference with document info, use DocumentDetailDialog
    if (onReferenceClick && !Array.isArray(referencesOrSingle) && referencesOrSingle.document_id) {
      console.log('🔍 Opening document detail for reference:', referencesOrSingle);
      onReferenceClick(referencesOrSingle);
      return;
    }
    
    // Otherwise, use the existing source dialog
    const dialogTitle = title || (references[0]?.title || references[0]?.display_name || 'Reference');
    setSourceDialogData({ title: dialogTitle, references });
    setSourceDialogOpen(true);
  }, [onReferenceClick]);
  
  const inputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const currentMessageIdRef = useRef<string>("");

  // Scroll to bottom
  const scrollToBottom = useCallback((smooth = true) => {
    const el = messagesEndRef.current;
    if (!el) return;

    const doScroll = () => {
      el.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'end' });
      // After scrolling to bottom, mark user as near bottom
      setIsNearBottom(true);
    };

    requestAnimationFrame(() => requestAnimationFrame(doScroll));
  }, []);

  // Handle scroll position
  const handleScroll = useCallback(() => {
    if (!scrollContainerRef.current) return;

    const container = scrollContainerRef.current;
    const { scrollTop, scrollHeight, clientHeight } = container;
    const scrollDifference = scrollHeight - (scrollTop + clientHeight);

    // Show scroll button if user is not near bottom
    setShowScrollButton(scrollDifference > 150);

    // Track if user is near bottom (within 150px)
    setIsNearBottom(scrollDifference < 150);
  }, []);

  // Register scroll event listener
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (container) {
      container.addEventListener('scroll', handleScroll, { passive: true });
      return () => container.removeEventListener('scroll', handleScroll);
    }
  }, [handleScroll]);

  // Auto scroll on new messages - only if user is near bottom
  useEffect(() => {
    const displayMessages = localMessages.length > 0 ? localMessages : messages;
    if ((isStreaming || displayMessages.length > 0) && isNearBottom) {
      setTimeout(() => scrollToBottom(false), 100);
    }
  }, [localMessages, messages, isStreaming, scrollToBottom, isNearBottom]);

  // Helper functions for processing different event types
  const handlePlanningEvents = useCallback((currentMessage: Message, event: any) => {
    const updatedMessage = { ...currentMessage };

    switch (event.type) {
      case 'planning_start':
        // Set planning flag to show animation
        updatedMessage.isPlanning = true;
        updatedMessage.planningStep = 0;
        updatedMessage.planningBuffer = '';
        updatedMessage.planningPreview = {};
        setTimeout(() => onStateUpdate?.({ currentPhase: 'planning' }), 0);
        break;

      case 'planning_token':
        // Accumulate planning tokens
        const buffer = (updatedMessage.planningBuffer || '') + (event.token || '');
        updatedMessage.planningBuffer = buffer;

        // Update planning step
        const currentStep = updatedMessage.planningStep ?? 0;
        updatedMessage.planningStep = Math.min(currentStep + 1, 4);

        // Try to extract preview information from buffer
        try {
          // Extract overview
          const overviewMatch = buffer.match(/"overview"\s*:\s*"([^"]+)"/);
          if (overviewMatch) {
            updatedMessage.planningPreview = {
              ...updatedMessage.planningPreview,
              overview: overviewMatch[1]
            };
          }

          // Extract task titles
          const taskMatches = [...buffer.matchAll(/"title"\s*:\s*"([^"]+)"/g)];
          if (taskMatches.length > 0) {
            updatedMessage.planningPreview = {
              ...updatedMessage.planningPreview,
              tasks: taskMatches.map(m => m[1])
            };
          }
        } catch (e) {
          // Ignore parsing errors during streaming
        }
        break;

      case 'plan':
      case 'plan_complete':
        // Clear planning flag and set the final plan
        updatedMessage.isPlanning = false;
        updatedMessage.planningStep = undefined;
        updatedMessage.planningBuffer = undefined;
        updatedMessage.planningPreview = undefined;
        updatedMessage.plan = event.plan;
        setTimeout(() => onStateUpdate?.({ currentPhase: event.plan?.requires_tool ? 'executing' : 'responding' }), 0);
        break;
    }

    return updatedMessage;
  }, [onStateUpdate]);
  
  const handleTaskEvents = useCallback((currentMessage: Message, event: any) => {
    const updatedMessage = { ...currentMessage };
    
    // Handle execution_complete separately as it doesn't need a plan
    if (event.type === 'execution_complete') {
      console.log('✅ Execution complete - references received:', event.all_references);
      console.log('✅ Execution complete - full event:', event);
      if (event.all_references && Array.isArray(event.all_references)) {
        if (!updatedMessage.references) {
          updatedMessage.references = [];
        }
        event.all_references.forEach((ref: any) => {
          // Use document_id for deduplication if available, otherwise use the entire ref object comparison
          const exists = updatedMessage.references?.find((existing: any) => 
            (ref.document_id && existing.document_id === ref.document_id) || 
            (ref.id && existing.id === ref.id) ||
            (JSON.stringify(existing) === JSON.stringify(ref))
          );
          if (!exists && updatedMessage.references) {
            console.log('✅ Adding reference:', ref);
            updatedMessage.references.push(ref);
          }
        });
        console.log('✅ Updated message references (final):', updatedMessage.references);
      } else {
        console.log('❌ No all_references or not an array');
      }
      return updatedMessage;
    }
    
    if (!updatedMessage.plan) return updatedMessage;
    
    const updatedPlan = { ...updatedMessage.plan };
    const taskIndex = updatedPlan.tasks.findIndex(t => t.title === event.task?.title);
    
    if (taskIndex >= 0) {
      switch (event.type) {
        case 'task_start':
          updatedPlan.tasks[taskIndex] = { ...updatedPlan.tasks[taskIndex], status: 'executing' };
          break;
        
        case 'task_complete':
          updatedPlan.tasks[taskIndex] = {
            ...updatedPlan.tasks[taskIndex],
            status: 'completed',
            result: event.result?.text || 'Completed',
            execution_time: event.execution_time
          };
          
          // Collect references from task completion
          if (event.references && Array.isArray(event.references)) {
            if (!updatedMessage.references) {
              updatedMessage.references = [];
            }
            event.references.forEach((ref: any) => {
              const exists = updatedMessage.references?.find((existing: any) => 
                (ref.document_id && existing.document_id === ref.document_id) || 
                (ref.id && existing.id === ref.id) ||
                (JSON.stringify(existing) === JSON.stringify(ref))
              );
              if (!exists && updatedMessage.references) {
                updatedMessage.references.push(ref);
              }
            });
          }

          // Also try to extract references from the result if it's a JSON string
          if (event.result && typeof event.result === 'string') {
            try {
              const parsed = JSON.parse(event.result);
              if (parsed && Array.isArray(parsed) && parsed.length > 0) {
                const firstResult = parsed[0];
                if (firstResult && firstResult.references && Array.isArray(firstResult.references)) {
                  console.log('🔗 Found references in task result:', firstResult.references);
                  if (!updatedMessage.references) {
                    updatedMessage.references = [];
                  }
                  firstResult.references.forEach((ref: any) => {
                    const exists = updatedMessage.references?.find((existing: any) => 
                      (ref.document_id && existing.document_id === ref.document_id) || 
                      (ref.id && existing.id === ref.id) ||
                      (JSON.stringify(existing) === JSON.stringify(ref))
                    );
                    if (!exists && updatedMessage.references) {
                      updatedMessage.references.push(ref);
                    }
                  });
                  console.log('🔗 Updated message references from result:', updatedMessage.references);
                }
              }
            } catch (e) {
              console.warn('Failed to parse task result as JSON:', e);
            }
          }
          break;
        
        case 'task_failed':
          updatedPlan.tasks[taskIndex] = {
            ...updatedPlan.tasks[taskIndex],
            status: 'failed',
            result: event.error || 'Task failed'
          };
          break;
      }
      
      updatedMessage.plan = updatedPlan;
    }
    
    return updatedMessage;
  }, []);
  
  const handleImageAnalysisEvents = useCallback((currentMessage: Message, event: any) => {
    const updatedMessage = { ...currentMessage };

    switch (event.type) {
      case 'phase_start':
        if (event.phase === 'image_analysis') {
          updatedMessage.isAnalyzingImage = true;
          setTimeout(() => onStateUpdate?.({ currentPhase: 'planning' }), 0);
        }
        break;

      case 'image_analysis_complete':
        console.log('📸 Image analysis completed:', event.analysis);
        updatedMessage.isAnalyzingImage = false;

        // Extract text from analysis result if it's a string representation of dict
        let analysisText = event.analysis;
        if (typeof analysisText === 'string') {
          try {
            // Try to parse if it looks like a stringified dict
            const parsed = JSON.parse(analysisText);
            if (parsed && parsed.content && Array.isArray(parsed.content)) {
              analysisText = parsed.content[0]?.text || analysisText;
            }
          } catch (e) {
            // If not JSON, check if it's a Python dict string representation
            const textMatch = analysisText.match(/'text':\s*'([^']+)'/);
            if (textMatch) {
              analysisText = textMatch[1];
            }
          }
        }

        updatedMessage.imageAnalysisResult = analysisText;
        break;

      case 'image_analysis_skip':
        console.log('📸 Image analysis skipped:', event.message);
        updatedMessage.isAnalyzingImage = false;
        break;
    }

    return updatedMessage;
  }, [onStateUpdate]);

  const handleResponseEvents = useCallback((currentMessage: Message, event: any) => {
    const updatedMessage = { ...currentMessage };

    switch (event.type) {
      case 'response_start':
        setTimeout(() => onStateUpdate?.({ currentPhase: 'responding' }), 0);
        break;

      case 'token':
        if (event.token && typeof event.token === 'string') {
          updatedMessage.content += event.token;
        }
        break;

      case 'references':
        if (event.references && Array.isArray(event.references)) {
          updatedMessage.references = event.references;
        }
        break;

      case 'complete':
        setTimeout(() => onStateUpdate?.({ currentPhase: 'idle' }), 0);
        updatedMessage.isStreaming = false;
        break;

      case 'error':
        updatedMessage.content = `Error: ${event.error || 'Unknown error'}`;
        updatedMessage.isStreaming = false;
        setTimeout(() => onStateUpdate?.({ currentPhase: 'idle' }), 0);
        break;
    }

    return updatedMessage;
  }, [onStateUpdate]);

  // Process streaming events from ChatAgent
  const processChatEvent = useCallback((event: any, messageId: string) => {
    const eventType = event.type;

    setLocalMessages(prev => {
      const messageIndex = prev.findIndex(msg => msg.id === messageId);
      if (messageIndex === -1) return prev;

      const newMessages = [...prev];
      let currentMessage = { ...newMessages[messageIndex] };

      // Route to appropriate handler based on event type
      switch (eventType) {
        case 'phase_start':
          // Handle phase transitions
          if (event.phase === 'image_analysis') {
            currentMessage = handleImageAnalysisEvents(currentMessage, event);
          } else if (event.phase === 'execution') {
            setTimeout(() => onStateUpdate?.({ currentPhase: 'executing' }), 0);
          } else if (event.phase === 'response') {
            setTimeout(() => onStateUpdate?.({ currentPhase: 'responding' }), 0);
          }
          break;

        case 'image_analysis_complete':
        case 'image_analysis_skip':
          currentMessage = handleImageAnalysisEvents(currentMessage, event);
          break;

        case 'planning_start':
        case 'planning_token':
        case 'plan':
        case 'plan_complete':
          currentMessage = handlePlanningEvents(currentMessage, event);
          break;

        case 'task_start':
        case 'task_complete':
        case 'task_failed':
        case 'execution_complete':
          currentMessage = handleTaskEvents(currentMessage, event);
          break;

        case 'response_start':
        case 'token':
        case 'references':
        case 'complete':
        case 'error':
          currentMessage = handleResponseEvents(currentMessage, event);
          break;
      }

      newMessages[messageIndex] = currentMessage;
      return newMessages;
    });
  }, [onStateUpdate, handleImageAnalysisEvents, handlePlanningEvents, handleTaskEvents, handleResponseEvents]);

  // Chat reset function
  const handleChatReset = useCallback(async () => {
    // Clear local messages first
    setLocalMessages([]);

    if (externalChatReset) {
      externalChatReset();
      return;
    }

    console.log('🔄 Chat reset initiated');
    setIsResetting(true);

    try {
      // Reinitialize search API
      await searchApi.reinitialize();

      // Update persistent state to clear messages, input, and reset chat started state
      onStateUpdate?.({
        messages: [],
        input: "",
        isChatStarted: false, // Reset to show welcome screen again
        currentPhase: 'idle',
        toolCollapsed: {} // Reset tool collapse states too
      });

      console.log('✅ Chat reset completed');
    } catch (error) {
      console.error('❌ Chat reset failed:', error);
      // Still reset UI even if API call fails
      onStateUpdate?.({
        messages: [],
        input: "",
        isChatStarted: false,
        currentPhase: 'idle',
        toolCollapsed: {}
      });
    } finally {
      setIsResetting(false);
      setShowResetConfirm(false);
    }
  }, [onStateUpdate, externalChatReset]);

  // Handle reset button click
  const handleResetClick = useCallback(() => {
    setShowResetConfirm(true);
  }, []);

  // Handle file upload
  const handleFileUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const newAttachments: FileAttachment[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];

      // Check file type
      if (!file.type.startsWith('image/')) {
        console.warn('Only image files are supported for search');
        continue;
      }

      // Check file size (max 10MB)
      if (file.size > 10 * 1024 * 1024) {
        console.warn(`File ${file.name} is too large (max 10MB)`);
        continue;
      }

      try {
        // For images: create preview URL
        let previewUrl: string | undefined;
        if (file.type.startsWith('image/')) {
          previewUrl = URL.createObjectURL(file);
        }

        const attachment: FileAttachment = {
          id: uuidv4(),
          file: file,
          type: file.type,
          previewUrl
        };

        newAttachments.push(attachment);
      } catch (error) {
        console.error(`Error processing file ${file.name}:`, error);
      }
    }

    if (newAttachments.length > 0) {
      const updatedAttachments = [...attachments, ...newAttachments];
      onStateUpdate?.({ attachments: updatedAttachments });
    }

    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [attachments, onStateUpdate]);

  // Remove attachment
  const removeAttachment = useCallback((attachmentId: string) => {
    const attachment = attachments.find(a => a.id === attachmentId);
    if (attachment?.previewUrl) {
      URL.revokeObjectURL(attachment.previewUrl);
    }

    const updatedAttachments = attachments.filter(a => a.id !== attachmentId);
    onStateUpdate?.({ attachments: updatedAttachments });
  }, [attachments, onStateUpdate]);

  // Send message
  const handleSendMessage = useCallback(async (message?: string) => {
    // Prevent duplicate calls
    if (sendingRef.current) {
      console.log('⚠️ Duplicate send attempt blocked');
      return;
    }

    // Debug logging
    console.log('🔍 handleSendMessage debug:', {
      message,
      messageType: typeof message,
      input,
      inputType: typeof input
    });

    // Safe string conversion with fallback
    let inputText = "";
    if (typeof message === "string") {
      inputText = message;
    } else if (typeof input === "string") {
      inputText = input;
    } else if (message !== undefined) {
      inputText = JSON.stringify(message);
    } else if (input !== undefined) {
      inputText = String(input);
    }

    console.log('📝 Final inputText:', inputText);

    if ((!inputText.trim() && attachments.length === 0) || isStreaming) return;

    // Set sending flag
    sendingRef.current = true;

    // When sending a new message, scroll to bottom and enable auto-scroll
    setIsNearBottom(true);

    // Check for reset marker or if chat hasn't started yet (hero screen)
    const RESET_MARKER = "__RESET__:";
    let shouldReset = false;

    // If hero screen is showing (not started), automatically add reset marker
    if (!isChatStarted) {
      inputText = `${RESET_MARKER}${inputText}`;
      console.log('🔄 Hero screen detected, adding reset marker for backend');
    }

    if (inputText.startsWith(RESET_MARKER)) {
      inputText = inputText.substring(RESET_MARKER.length).trim();
      console.log('🔄 Reset marker detected. New message:', inputText);

      // Only reinitialize if chat has already started (actual reset)
      // Don't reinitialize on first message from hero screen
      if (isChatStarted) {
        console.log('🔄 Reinitializing search API for existing conversation');
        try {
          await searchApi.reinitialize();
          console.log('✅ Search API reinitialized');
        } catch (error) {
          console.error('❌ Failed to reinitialize search API:', error);
          // Continue anyway - backend will handle fresh conversation
        }

        // Clear local and persistent messages for reset
        setLocalMessages([]);
        onStateUpdate?.({
          messages: [],
          currentPhase: 'idle',
          toolCollapsed: {}
        });
      } else {
        console.log('🆕 First message from hero screen - no reinit needed');
      }
    }

    const wasNotStarted = !isChatStarted;

    if (!isChatStarted) {
      onStateUpdate?.({ isChatStarted: true });
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      sender: "user",
      content: inputText.trim(),
      timestamp: Date.now(),
      attachedImages: attachments.length > 0 ? [...attachments] : undefined
    };

    const aiMessageId = (Date.now() + 1).toString();
    currentMessageIdRef.current = aiMessageId;

    const aiMessage: Message = {
      id: aiMessageId,
      sender: "ai",
      content: "",
      timestamp: Date.now() + 1,
      isStreaming: true
    };

    // Update local messages for real-time display
    // If this is the first message after reset, start with a new array
    if (wasNotStarted) {
      setLocalMessages([userMessage, aiMessage]);
    } else {
      setLocalMessages(prev => [...prev, userMessage, aiMessage]);
    }

    // Clear input and attachments
    onStateUpdate?.({ input: "", attachments: [] });
    setIsStreaming(true);
    onStateUpdate?.({ currentPhase: "planning" });

    try {
      const finalIndexId = indexId || "default";
      console.log('📋 ChatAgent sending request with index_id:', finalIndexId);
      console.log('📎 Attachments:', attachments.length);

      const response = await searchApi.chatStream({
        message: userMessage.content,
        index_id: finalIndexId as string, // Type assertion since we ensure it's not undefined
        files: attachments.length > 0 ? attachments.map(a => a.file) : undefined
      });

      if (!response.ok) {
        throw new Error(`Chat request failed: ${response.status}`);
      }

      if (!response.body) {
        throw new Error("No response stream received");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6).trim();
            
            if (dataStr === '[DONE]') {
              setIsStreaming(false);
              onStateUpdate?.({ currentPhase: "idle" });
              setLocalMessages(prev => prev.map(msg => {
                if (msg.id === aiMessageId) {
                  // Preserve all existing properties including references
                  const updatedMsg = { ...msg, isStreaming: false };
                  console.log('🏁 Stream complete - preserving message with references:', updatedMsg.references);
                  return updatedMsg;
                }
                return msg;
              }));
              setTimeout(() => {
                inputRef.current?.focus();
              }, 500);
              return;
            }

            if (dataStr === '') continue;

            try {
              const event = JSON.parse(dataStr);
              console.log('📨 Received event:', event.type, event);
              processChatEvent(event, aiMessageId);
            } catch (parseError) {
              console.warn('Failed to parse chat event:', parseError, 'Raw data:', dataStr);
            }
          }
        }
      }

    } catch (error) {
      console.error('Chat error:', error);
      setLocalMessages(prev => prev.map(msg =>
        msg.id === aiMessageId
          ? { ...msg, content: `Error: ${error instanceof Error ? error.message : "Unknown error"}`, isStreaming: false }
          : msg
      ));
      setIsStreaming(false);
      onStateUpdate?.({ currentPhase: "idle" });
    } finally {
      sendingRef.current = false;
    }
  }, [input, indexId, isStreaming, onStateUpdate, isChatStarted, processChatEvent, attachments]);

  // Handle example click with proper async handling
  const handleExampleClick = useCallback((example: string) => {
    // Update input first
    onStateUpdate?.({ input: example });

    // Schedule send after state update
    requestAnimationFrame(() => {
      setTimeout(() => {
        if (!isStreaming) {
          handleSendMessage();
        }
      }, 50);
    });
  }, [onStateUpdate, handleSendMessage, isStreaming]);

  // Custom citation renderer component
  const CitationRenderer = useCallback(({ content, references }: { content: string, references?: any[] }) => {
    if (!references || references.length === 0) {
      return <MarkdownRenderer content={content} />;
    }

    const citationPattern = /\[(\d+)\]/g;
    const citationMap: { [key: string]: any } = {};

    // Build citation map
    content.replace(citationPattern, (match, num) => {
      const refIndex = parseInt(num) - 1;
      if (refIndex >= 0 && refIndex < references.length) {
        citationMap[num] = references[refIndex];
      }
      return match;
    });

    // Convert citations to markdown links (e.g., [[1]](#citation-1))
    const processedContent = content.replace(citationPattern, (match, num) => {
      if (citationMap[num]) {
        return `[[${num}]](#citation-${num})`;
      }
      return match;
    });

    // Handle citation clicks using event delegation
    const handleClick = (e: React.MouseEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === 'A' && target.getAttribute('href')?.startsWith('#citation-')) {
        e.preventDefault();
        e.stopPropagation();
        const refNum = target.getAttribute('href')?.replace('#citation-', '');
        if (refNum && citationMap[refNum]) {
          handleReferenceClick(citationMap[refNum]);
        }
      }
    };

    return (
      <div className="citation-container" onClick={handleClick}>
        <style jsx>{`
          .citation-container :global(a[href^="#citation-"]) {
            display: inline;
            cursor: pointer;
            font-size: 0.75rem;
            font-weight: 700;
            color: rgb(52 211 153) !important;
            white-space: nowrap;
            margin-left: 0.125rem;
            text-decoration: none !important;
            border: none !important;
          }
          .citation-container :global(a[href^="#citation-"]:hover) {
            color: rgb(110 231 183) !important;
            text-decoration: none !important;
          }
        `}</style>
        <MarkdownRenderer content={processedContent} />
      </div>
    );
  }, [handleReferenceClick]);

  // Handle key press
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !isComposing) {
      e.preventDefault();
      if (!isStreaming) {
        handleSendMessage();
      } else {
        // During streaming, Enter creates a new line (by updating input with newline)
        const currentValue = e.currentTarget.value;
        const cursorPos = e.currentTarget.selectionStart || 0;
        const newValue = currentValue.slice(0, cursorPos) + '\n' + currentValue.slice(cursorPos);
        handleSetInput(newValue);
        // Maintain focus and set cursor position after newline
        requestAnimationFrame(() => {
          const input = inputRef.current;
          if (input) {
            input.focus();
            input.setSelectionRange(cursorPos + 1, cursorPos + 1);
          }
        });
      }
    }
  }, [handleSendMessage, isComposing, isStreaming, handleSetInput]);

  // Get animation styles
  const getAnimationStyles = () => `
    @keyframes fadeIn {
      from { 
        opacity: 0;
        transform: translateY(2px);
      }
      to { 
        opacity: 1;
        transform: translateY(0);
      }
    }
    
    @keyframes spin-slow {
      from {
        transform: rotate(0deg);
      }
      to {
        transform: rotate(360deg);
      }
    }
    
    .animate-spin-slow {
      animation: spin-slow 2s linear infinite;
    }
    
    .fade-in {
      animation: fadeIn 0.3s ease-out forwards;
    }
  `;

  // Render plan with enhanced design
  const renderPlan = (plan: Plan, messageId: string) => {
    // Determine plan type for display
    const isDirectResponse = plan.requires_tool === false || (plan.direct_response && (!plan.tasks || plan.tasks.length === 0));

    return (
      <div className="mt-4 space-y-4">
        {/* Plan Header - different for direct response vs tool execution */}
        <div className={`relative overflow-hidden rounded-2xl border p-4 backdrop-blur-sm ${
          isDirectResponse
            ? 'bg-gradient-to-br from-cyan-500/10 via-cyan-500/5 to-transparent border-cyan-500/20'
            : 'bg-gradient-to-br from-purple-500/10 via-purple-500/5 to-transparent border-purple-500/20'
        }`}>
          <div className={`absolute top-0 right-0 w-32 h-32 rounded-full blur-3xl ${
            isDirectResponse ? 'bg-cyan-500/10' : 'bg-purple-500/10'
          }`} />
          <div className="relative flex items-center gap-3">
            <div className={`flex-shrink-0 w-10 h-10 rounded-xl border flex items-center justify-center ${
              isDirectResponse
                ? 'bg-gradient-to-br from-cyan-500/20 to-cyan-600/20 border-cyan-400/30'
                : 'bg-gradient-to-br from-purple-500/20 to-purple-600/20 border-purple-400/30'
            }`}>
              {isDirectResponse ? (
                <Sparkles className="h-5 w-5 text-cyan-300" />
              ) : (
                <Settings className="h-5 w-5 text-purple-300" />
              )}
            </div>
            <div className="flex-1">
              <div className={`text-sm font-semibold mb-0.5 ${
                isDirectResponse ? 'text-cyan-200' : 'text-purple-200'
              }`}>
                {isDirectResponse ? 'Quick Response' : 'Search Plan'}
              </div>
              <div className={`text-xs ${
                isDirectResponse ? 'text-cyan-300/60' : 'text-purple-300/60'
              }`}>
                {isDirectResponse ? 'No tools needed for this request' : 'AI will search through documents'}
              </div>
            </div>
          </div>
        </div>

        {/* Plan Overview - only if not a simple greeting */}
        {plan.overview && !plan.overview.toLowerCase().includes('greeting') && !plan.overview.toLowerCase().includes('simple') && (
          <div className="relative overflow-hidden rounded-xl bg-gradient-to-br from-purple-950/40 to-purple-900/20 border border-purple-500/20 p-4 backdrop-blur-sm">
            <div className="absolute top-0 left-0 w-24 h-24 bg-purple-500/10 rounded-full blur-2xl" />
            <div className="relative">
              <div className="flex items-start gap-2 mb-2">
                <Brain className="h-4 w-4 text-purple-300 mt-0.5 flex-shrink-0" />
                <span className="text-xs font-medium text-purple-200 uppercase tracking-wide">Strategy</span>
              </div>
              <div className="text-purple-100 text-sm leading-relaxed">{plan.overview}</div>
            </div>
          </div>
        )}

        {/* Tasks Timeline */}
        {plan.tasks && plan.tasks.length > 0 && (
          <div className="space-y-2.5">
            {plan.tasks.map((task, index) => (
              <div
                key={index}
                className="group relative overflow-hidden rounded-xl bg-gradient-to-br from-white/[0.03] to-white/[0.01] border border-white/[0.08] hover:border-white/[0.15] p-4 transition-all duration-300 backdrop-blur-sm"
              >
                {/* Status-based gradient overlay */}
                {task.status === 'executing' && (
                  <div className="absolute inset-0 bg-gradient-to-r from-yellow-500/5 via-yellow-500/10 to-yellow-500/5 animate-pulse" />
                )}
                {task.status === 'completed' && (
                  <div className="absolute inset-0 bg-gradient-to-r from-green-500/5 to-transparent" />
                )}
                {task.status === 'failed' && (
                  <div className="absolute inset-0 bg-gradient-to-r from-red-500/5 to-transparent" />
                )}

                <div className="relative flex items-start gap-4">
                  {/* Status Icon */}
                  <div className="flex-shrink-0 mt-0.5">
                    {task.status === 'pending' && (
                      <div className="w-8 h-8 rounded-xl border-2 border-gray-500/30 bg-gray-500/10 flex items-center justify-center backdrop-blur-sm">
                        <Clock className="w-4 h-4 text-gray-400" />
                      </div>
                    )}
                    {task.status === 'executing' && (
                      <div className="relative w-8 h-8 rounded-xl bg-gradient-to-br from-yellow-500/20 to-yellow-600/20 border border-yellow-400/40 flex items-center justify-center backdrop-blur-sm">
                        <div className="absolute inset-0 rounded-xl bg-yellow-400/20 animate-ping" />
                        <Cog className="relative w-4 h-4 text-yellow-300 animate-spin-slow" />
                      </div>
                    )}
                    {task.status === 'completed' && (
                      <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-green-500/20 to-green-600/20 border border-green-400/40 flex items-center justify-center backdrop-blur-sm">
                        <CheckCircle className="w-4 h-4 text-green-300" />
                      </div>
                    )}
                    {task.status === 'failed' && (
                      <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-red-500/20 to-red-600/20 border border-red-400/40 flex items-center justify-center backdrop-blur-sm">
                        <AlertCircle className="w-4 h-4 text-red-300" />
                      </div>
                    )}
                  </div>

                  {/* Task Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-3 mb-1.5">
                      <h4 className="text-white text-sm font-semibold leading-tight">{task.title}</h4>
                      {task.execution_time && (
                        <span className="flex-shrink-0 px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-xs text-white/50 font-mono">
                          {task.execution_time.toFixed(2)}s
                        </span>
                      )}
                    </div>

                    <p className="text-white/60 text-xs leading-relaxed mb-2">{task.description}</p>

                    {/* Tool Badge */}
                    {task.tool_name && (
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-cyan-500/10 border border-cyan-400/20 backdrop-blur-sm">
                        <Wrench className="w-3 h-3 text-cyan-300" />
                        <span className="text-xs font-medium text-cyan-200">{task.tool_name}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Progress indicator line for executing tasks */}
                {task.status === 'executing' && (
                  <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-yellow-400/50 to-transparent">
                    <div className="h-full w-1/3 bg-gradient-to-r from-yellow-400/0 via-yellow-400 to-yellow-400/0 animate-pulse" />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  // Render references
  const renderReferences = (references: Reference[]) => {
    console.log('📚 renderReferences called with:', references);
    if (!references || references.length === 0) {
      console.log('📚 No references to render');
      return null;
    }

    return (
      <div className="mt-3 pt-2 border-t border-white/5">
        <div className="mb-2 flex items-center justify-between">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/5 border border-white/10 backdrop-blur-md text-[10px] text-white/80">
            <FileText className="w-3 h-3 text-cyan-300" />
            <span>References</span>
            <span className="text-cyan-300">({references.length})</span>
          </div>
          {references.length > 3 && (
            <button
              onClick={() => handleReferenceClick(references, '모든 참조')}
              className="text-xs text-cyan-300 hover:text-cyan-200 underline"
            >
              모두 보기
            </button>
          )}
        </div>
        <div className="space-y-1">
          {references.slice(0, 3).map((ref, index) => (
            <div 
              key={index} 
              className="p-2 bg-white/[0.02] border border-white/[0.05] rounded-lg cursor-pointer hover:bg-white/[0.04] transition-colors group"
              onClick={() => {
                // If reference has document info and we have onReferenceClick, use DocumentDetailDialog
                if (onReferenceClick && ref.document_id) {
                  onReferenceClick(ref);
                } else {
                  // Otherwise, use source dialog
                  handleReferenceClick([ref], ref.display_name || ref.title);
                }
              }}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="text-xs text-white/80 font-medium">
                    {ref.file_name || ref.display_name || ref.title || ref.value?.substring(0, 50)}
                  </div>
                  {(ref.segment_index !== undefined || ref.page_index !== undefined) && (
                    <div className="text-xs text-white/50 mt-0.5">
                      Segment {(ref.segment_index ?? ref.page_index ?? 0) + 1}
                    </div>
                  )}
                </div>
                <div className="ml-2 flex-shrink-0 flex items-center gap-1">
                  {ref.type === 'image' && (
                    <FileText className="w-3 h-3 text-white/40" />
                  )}
                  {ref.document_id && onReferenceClick && (
                    <div className="text-xs text-purple-300/70 group-hover:text-purple-300 transition-colors">
                      Details
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: getAnimationStyles() }} />
      
      <div className="h-full flex flex-col bg-transparent relative overflow-hidden">
        {/* Background effect */}
        <div className="absolute inset-0 w-full h-full overflow-hidden pointer-events-none">
          <div className="absolute top-0 left-1/4 w-96 h-96 bg-cyan-500/5 rounded-full mix-blend-normal filter blur-[128px] animate-pulse" />
          <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-sky-500/5 rounded-full mix-blend-normal filter blur-[128px] animate-pulse delay-700" />
        </div>

        {/* Messages area */}
        <div 
          ref={scrollContainerRef}
          className="flex-1 overflow-y-auto relative z-10"
          style={{ 
            scrollbarWidth: 'none',
            msOverflowStyle: 'none',
            height: 'calc(100vh - 270px)',
            maxHeight: 'calc(100vh - 270px)',
          }}
        >
          <style>
            {`
              .scroll-container::-webkit-scrollbar {
                display: none;
              }
            `}
          </style>
          
          <div className="max-w-3xl mx-auto w-full p-4">
            {!isChatStarted && (
              <SearchHero onExampleClick={handleExampleClick} />
            )}

            {isChatStarted && (() => {
              // Always use localMessages as primary source since it has the most up-to-date data
              // Fall back to persistent messages only if localMessages is empty
              const displayMessages = localMessages.length > 0 ? localMessages : messages;
              console.log('🎨 Display messages selection:', {
                usingLocalMessages: localMessages.length > 0,
                localMessagesCount: localMessages.length,
                messagesCount: messages.length,
                lastMessageReferences: displayMessages[displayMessages.length - 1]?.references?.length
              });
              return displayMessages;
            })().map((message) => (
              message.sender === "user" ? (
                <div key={message.id} className="mb-4 flex justify-end">
                  <div className="max-w-[80%] bg-white/[0.08] backdrop-blur-xl rounded-2xl border border-white/[0.1] p-4">
                    {/* Attached Images */}
                    {message.attachedImages && message.attachedImages.length > 0 && (
                      <div className="mb-3 flex flex-wrap gap-2">
                        {message.attachedImages.map((img) => (
                          <div key={img.id} className="relative group">
                            {img.previewUrl && (
                              <Image
                                src={img.previewUrl}
                                alt={img.file.name}
                                width={120}
                                height={120}
                                className="rounded-lg border border-white/20 object-cover"
                              />
                            )}
                            <div className="absolute bottom-0 left-0 right-0 bg-black/70 text-white text-[10px] px-1 py-0.5 rounded-b-lg truncate">
                              {img.file.name}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="text-white/90 text-sm">
                      <MarkdownRenderer content={message.content} />
                    </div>
                  </div>
                </div>
              ) : (
                <div key={message.id} className="mb-6 max-w-full">
                  <div className="flex items-start gap-2">
                    <div className="flex-1 max-w-full">
                      <div className="text-white/90 text-sm break-words overflow-wrap-anywhere max-w-full">
                        {/* Show image analysis animation */}
                        {message.isAnalyzingImage && (
                          <div className="mb-4">
                            <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-green-500/10 via-green-500/5 to-transparent border border-green-500/20 p-6 backdrop-blur-sm">
                              <div className="absolute top-0 right-0 w-32 h-32 bg-green-500/10 rounded-full blur-3xl animate-pulse" />
                              <div className="relative flex items-center gap-3">
                                <div className="flex-shrink-0 w-10 h-10 rounded-xl bg-gradient-to-br from-green-500/20 to-green-600/20 border border-green-400/30 flex items-center justify-center">
                                  <Sparkles className="h-5 w-5 text-green-300 animate-pulse" />
                                </div>
                                <div className="flex-1">
                                  <div className="text-sm font-semibold text-green-200 mb-1">이미지 분석 중</div>
                                  <div className="text-xs text-green-300/60">첨부된 이미지를 분석하여 검색에 활용합니다...</div>
                                </div>
                                <div className="flex gap-1">
                                  <motion.div
                                    className="w-2 h-2 rounded-full bg-green-400"
                                    animate={{ opacity: [0.3, 1, 0.3] }}
                                    transition={{ duration: 1.5, repeat: Infinity, delay: 0 }}
                                  />
                                  <motion.div
                                    className="w-2 h-2 rounded-full bg-green-400"
                                    animate={{ opacity: [0.3, 1, 0.3] }}
                                    transition={{ duration: 1.5, repeat: Infinity, delay: 0.2 }}
                                  />
                                  <motion.div
                                    className="w-2 h-2 rounded-full bg-green-400"
                                    animate={{ opacity: [0.3, 1, 0.3] }}
                                    transition={{ duration: 1.5, repeat: Infinity, delay: 0.4 }}
                                  />
                                </div>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Show image analysis result */}
                        {message.imageAnalysisResult && !message.isAnalyzingImage && (() => {
                          const isCollapsed = imageAnalysisCollapsed[message.id] ?? true; // Default collapsed

                          return (
                            <div className="mb-4">
                              <div className="relative overflow-hidden rounded-xl bg-gradient-to-br from-green-950/40 to-green-900/20 border border-green-500/20 backdrop-blur-sm">
                                <div className="absolute top-0 left-0 w-24 h-24 bg-green-500/10 rounded-full blur-2xl" />
                                <div className="relative">
                                  {/* Header - always visible, clickable */}
                                  <button
                                    onClick={() => setImageAnalysisCollapsed(prev => ({ ...prev, [message.id]: !isCollapsed }))}
                                    className="w-full flex items-center justify-between gap-2 p-4 hover:bg-green-500/5 transition-colors rounded-xl"
                                  >
                                    <div className="flex items-center gap-2">
                                      <Sparkles className="h-4 w-4 text-green-300 flex-shrink-0" />
                                      <span className="text-xs font-medium text-green-200 uppercase tracking-wide">이미지 분석 결과</span>
                                    </div>
                                    <motion.div
                                      animate={{ rotate: isCollapsed ? 0 : 180 }}
                                      transition={{ duration: 0.2 }}
                                    >
                                      <ChevronDown className="h-4 w-4 text-green-300" />
                                    </motion.div>
                                  </button>

                                  {/* Content - collapsible */}
                                  <AnimatePresence>
                                    {!isCollapsed && (
                                      <motion.div
                                        initial={{ height: 0, opacity: 0 }}
                                        animate={{ height: "auto", opacity: 1 }}
                                        exit={{ height: 0, opacity: 0 }}
                                        transition={{ duration: 0.2 }}
                                        className="overflow-hidden"
                                      >
                                        <div className="px-4 pb-4">
                                          <div className="text-green-100 text-sm leading-relaxed whitespace-pre-wrap">
                                            {message.imageAnalysisResult}
                                          </div>
                                        </div>
                                      </motion.div>
                                    )}
                                  </AnimatePresence>
                                </div>
                              </div>
                            </div>
                          );
                        })()}

                        {/* Show planning animation */}
                        {message.isPlanning && (() => {
                          const planningSteps = [
                            { title: "Analyzing Your Request", description: "Understanding your question..." },
                            { title: "Analyzing Your Request", description: "Evaluating search requirements..." },
                            { title: "Planning Search Strategy", description: "Designing document search approach..." },
                            { title: "Planning Search Strategy", description: "Identifying relevant tools and methods..." },
                            { title: "Finalizing Plan", description: "Optimizing search parameters..." }
                          ];

                          const step = planningSteps[Math.min(message.planningStep ?? 0, planningSteps.length - 1)];
                          const preview = message.planningPreview;

                          return (
                            <div className="space-y-3">
                              <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-purple-500/10 via-purple-500/5 to-transparent border border-purple-500/20 p-6 backdrop-blur-sm">
                                <div className="absolute top-0 right-0 w-32 h-32 bg-purple-500/10 rounded-full blur-3xl animate-pulse" />
                                <div className="relative flex items-center gap-3">
                                  <div className="flex-shrink-0 w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500/20 to-purple-600/20 border border-purple-400/30 flex items-center justify-center">
                                    <Brain className="h-5 w-5 text-purple-300 animate-pulse" />
                                  </div>
                                  <div className="flex-1">
                                    <div className="text-sm font-semibold text-purple-200 mb-1">{step.title}</div>
                                    <div className="text-xs text-purple-300/60">{step.description}</div>
                                  </div>
                                  <div className="flex gap-1">
                                    <motion.div
                                      className="w-2 h-2 rounded-full bg-purple-400"
                                      animate={{ opacity: [0.3, 1, 0.3] }}
                                      transition={{ duration: 1.5, repeat: Infinity, delay: 0 }}
                                    />
                                    <motion.div
                                      className="w-2 h-2 rounded-full bg-purple-400"
                                      animate={{ opacity: [0.3, 1, 0.3] }}
                                      transition={{ duration: 1.5, repeat: Infinity, delay: 0.2 }}
                                    />
                                    <motion.div
                                      className="w-2 h-2 rounded-full bg-purple-400"
                                      animate={{ opacity: [0.3, 1, 0.3] }}
                                      transition={{ duration: 1.5, repeat: Infinity, delay: 0.4 }}
                                    />
                                  </div>
                                </div>
                              </div>

                              {/* Show extracted plan preview */}
                              {preview && (preview.overview || (preview.tasks && preview.tasks.length > 0)) && (
                                <motion.div
                                  initial={{ opacity: 0, y: -10 }}
                                  animate={{ opacity: 1, y: 0 }}
                                  className="relative overflow-hidden rounded-xl bg-gradient-to-br from-indigo-500/5 via-purple-500/5 to-transparent border border-indigo-500/20 p-4 backdrop-blur-sm"
                                >
                                  <div className="space-y-2">
                                    {preview.overview && (
                                      <div>
                                        <div className="text-xs font-medium text-indigo-300/80 mb-1 uppercase tracking-wide">Plan Overview</div>
                                        <div className="text-sm text-indigo-200/90 leading-relaxed">{preview.overview}</div>
                                      </div>
                                    )}

                                    {preview.tasks && preview.tasks.length > 0 && (
                                      <div>
                                        <div className="text-xs font-medium text-purple-300/80 mb-1 uppercase tracking-wide">Planned Tasks</div>
                                        <div className="space-y-1">
                                          {preview.tasks.map((task, idx) => (
                                            <div key={idx} className="flex items-start gap-2">
                                              <div className="flex-shrink-0 w-4 h-4 rounded bg-purple-500/20 border border-purple-400/30 flex items-center justify-center mt-0.5">
                                                <span className="text-[10px] text-purple-300">{idx + 1}</span>
                                              </div>
                                              <div className="text-xs text-purple-200/80">{task}</div>
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                </motion.div>
                              )}
                            </div>
                          );
                        })()}

                        {/* Show plan if available */}
                        {message.plan && renderPlan(message.plan, message.id)}
                        
                        {/* Show response content */}
                        {message.content && (
                          <div className={cn("mt-4", message.isStreaming && "fade-in")}>
                            <CitationRenderer content={message.content} references={message.references} />
                          </div>
                        )}
                        
                        {/* Show references */}
                        {(() => {
                          const hasRefs = message.references && Array.isArray(message.references) && message.references.length > 0;
                          console.log(`🔍 Rendering message ${message.id}:`, { 
                            hasReferences: hasRefs, 
                            referencesLength: message.references?.length,
                            references: message.references,
                            isArray: Array.isArray(message.references),
                            messageKeys: Object.keys(message || {})
                          });
                          return hasRefs ? renderReferences(message.references!) : null;
                        })()}
                      </div>
                    </div>
                  </div>
                </div>
              )
            ))}
            
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Scroll to bottom button */}
        {showScrollButton && (
          <div className="absolute bottom-20 right-8 z-[100]">
            <button
              onClick={() => scrollToBottom()}
              className="bg-white/20 hover:bg-white/30 text-white p-3 rounded-full shadow-xl transition-all duration-200 flex items-center justify-center transform hover:scale-110 backdrop-blur-xl border border-white/20"
            >
              <ArrowDown className="h-5 w-5" />
            </button>
          </div>
        )}

        {/* Input area - fixed at bottom */}
        <div className="flex-shrink-0 z-20 px-4 pt-4 pb-6 bg-black/60 backdrop-blur border-t border-white/10">
          <div className="max-w-3xl mx-auto w-full">
            {/* Attachment Preview - show above input when attachments exist */}
            {attachments.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-2">
                {attachments.map((attachment) => (
                  <div
                    key={attachment.id}
                    className="relative group bg-white/10 border border-white/20 rounded-lg p-2 backdrop-blur-xl"
                  >
                    {attachment.previewUrl && (
                      <Image
                        src={attachment.previewUrl}
                        alt="Preview"
                        width={80}
                        height={80}
                        className="rounded object-cover"
                      />
                    )}
                    <button
                      onClick={() => removeAttachment(attachment.id)}
                      className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 hover:bg-red-600 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <X className="w-3 h-3" />
                    </button>
                    <div className="absolute bottom-0 left-0 right-0 bg-black/70 text-white text-[10px] px-1 py-0.5 rounded-b truncate">
                      {attachment.file.name}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="relative bg-gradient-to-r from-gray-900/90 to-gray-800/90 border border-white/20 rounded-full backdrop-blur-xl shadow-2xl">
              <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/10 via-purple-500/10 to-pink-500/10 rounded-full animate-pulse" />
              <div className="relative p-4 flex items-center gap-2">
                <div className="flex-shrink-0">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-cyan-500/20 to-purple-500/20 flex items-center justify-center">
                    <Sparkles className="w-5 h-5 text-cyan-400 animate-pulse" />
                  </div>
                </div>

                {/* File Attachment Button */}
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isStreaming}
                  className="p-2 rounded-full hover:bg-white/5 transition-all group mr-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Attach Image"
                >
                  <Paperclip className="w-5 h-5 text-green-400 group-hover:text-green-300 transition-colors" />
                </button>

                {/* Hidden File Input */}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  multiple
                  onChange={handleFileUpload}
                  className="hidden"
                />

                <input
                  ref={inputRef}
                  type="text"
                  value={input}
                  onChange={(e) => handleSetInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onCompositionStart={() => setIsComposing(true)}
                  onCompositionEnd={() => setIsComposing(false)}
                  placeholder="What documents would you like to search?"
                  className="bg-transparent flex-1 outline-none text-white placeholder:text-white/50 text-lg font-medium"
                />

                <button
                  onClick={() => handleSendMessage()}
                  disabled={(!input.trim() && attachments.length === 0) || isStreaming}
                  className="ml-3 p-2 rounded-full bg-white/10 hover:bg-white/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isStreaming ? (
                    <Loader2 className="h-4 w-4 animate-spin text-white" />
                  ) : (
                    <Send className="h-4 w-4 text-white" />
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Sources Dialog */}
      {sourceDialogOpen && (
        <div className="fixed inset-0 bg-black/90 flex items-center justify-center z-50 backdrop-blur-sm">
          <div className="bg-gray-900/95 border border-white/10 rounded-xl max-w-2xl w-full mx-4 max-h-[80vh] overflow-hidden shadow-2xl">
            <div className="flex items-center justify-between p-4 border-b border-white/10">
              <h3 className="text-lg font-semibold text-white">
                {sourceDialogData.title || 'References'}
              </h3>
              <button
                onClick={() => setSourceDialogOpen(false)}
                className="p-2 hover:bg-white/10 rounded-lg transition-colors"
              >
                <X className="h-5 w-5 text-white/60" />
              </button>
            </div>
            <div className="p-4 overflow-y-auto max-h-[60vh]">
              {sourceDialogData.references && sourceDialogData.references.length > 0 ? (
                <div className="space-y-3">
                  {sourceDialogData.references.map((ref, idx) => (
                    <div key={idx} className="p-4 bg-white/5 rounded-lg border border-white/10">
                      <div className="space-y-2">
                        {/* Title with display_name */}
                        {ref.display_name && (
                          <div className="font-medium text-white">{ref.display_name}</div>
                        )}
                        
                        {/* Image preview */}
                        {ref.image_uri && (
                          <div className="mt-2 relative">
                            <Image
                              src={ref.image_uri}
                              alt={ref.title || 'Reference'}
                              width={800}
                              height={600}
                              className="max-w-full h-auto rounded border border-white/20"
                              onError={(e) => {
                                e.currentTarget.style.display = 'none';
                              }}
                            />
                          </div>
                        )}
                        
                        {/* Content/Value */}
                        {ref.value && (
                          <div className="text-white/80 text-sm max-h-40 overflow-y-auto">
                            {ref.value}
                          </div>
                        )}
                        
                        {/* Additional metadata */}
                        <div className="flex gap-4 text-xs text-white/60 mt-2">
                          {ref.file_name && <span>File: {ref.file_name}</span>}
                          {(ref.segment_index !== undefined || ref.page_index !== undefined) && (
                            <span>Segment: {(ref.segment_index ?? ref.page_index ?? 0) + 1}</span>
                          )}
                        </div>

                        {/* Actions */}
                        <div className="flex gap-2 mt-3">
                          {ref.document_id && onReferenceClick && (
                            <button
                              onClick={() => {
                                setSourceDialogOpen(false);
                                onReferenceClick(ref);
                              }}
                              className="px-3 py-1 bg-purple-500/20 text-purple-300 border border-purple-500/30 rounded text-sm hover:bg-purple-500/30 transition"
                            >
                              Document Details
                            </button>
                          )}
                          {ref.file_uri && (
                            <button
                              onClick={() => window.open(ref.file_uri, '_blank')}
                              className="px-3 py-1 bg-blue-500/20 text-blue-300 border border-blue-500/30 rounded text-sm hover:bg-blue-500/30 transition"
                            >
                              View PDF
                            </button>
                          )}
                          {onAttachToChat && ref.document_id && ref.page_index !== undefined && (
                            <button
                              onClick={() => onAttachToChat({
                                document_id: ref.document_id!,
                                page_index: ref.page_index!,
                                page_number: ref.page_index! + 1,
                                file_name: ref.title || 'Unknown'
                              })}
                              className="px-3 py-1 bg-green-500/20 text-green-300 border border-green-500/30 rounded text-sm hover:bg-green-500/30 transition"
                            >
                              Attach to Chat
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-white/60 text-center py-4">
                  No references available.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

    </>
  );
}