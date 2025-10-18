"use client";

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
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
  Cog
} from "lucide-react";
import { cn } from "@/lib/utils";
import { MarkdownRenderer } from "@/components/ui/markdown-renderer";
import React from 'react';
import Image from 'next/image';
import { MessageLoading } from "@/components/ui/message-loading";
import { searchApi, documentApi } from "@/lib/api";
import { SearchHero } from "./search-hero";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

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
  planningThought?: string;  // Planning 과정 표시용
}

// Types for persistent state across tabs
interface PersistentSearchState {
  messages: Message[];
  input: string;
  currentPhase: "idle" | "planning" | "executing" | "responding";
  toolCollapsed: Record<string, boolean>;
  isChatStarted: boolean;
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
}

export function SearchInterface({ indexId, onOpenPdf, onAttachToChat, onReferenceClick, persistentState, onStateUpdate }: SearchInterfaceProps) {
  // Use persistent state as primary source of truth with memoization
  const messages = useMemo(() => persistentState?.messages ?? [], [persistentState?.messages]);
  const input = persistentState?.input ?? "";
  const currentPhase = persistentState?.currentPhase ?? "idle";
  const toolCollapsed = useMemo(() => persistentState?.toolCollapsed ?? {}, [persistentState?.toolCollapsed]);
  const isChatStarted = persistentState?.isChatStarted ?? false;

  // Local state for UI-only concerns
  const [isStreaming, setIsStreaming] = useState(false);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [isComposing, setIsComposing] = useState(false);
  const [sourceDialogOpen, setSourceDialogOpen] = useState(false);
  const [sourceDialogData, setSourceDialogData] = useState<{ title?: string; references?: Reference[] }>({});
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [isResetting, setIsResetting] = useState(false);

  // Local messages state for real-time updates during streaming
  const [localMessages, setLocalMessages] = useState<Message[]>(() => {
    // Initialize with persistent messages if available
    return messages.length > 0 ? messages : [];
  });

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

  // Sync local messages with persistent state only when initially loading
  useEffect(() => {
    if (!isStreaming && messages.length > 0 && localMessages.length === 0) {
      // Only sync when localMessages is empty (initial load)
      setLocalMessages(messages);
    }
  }, [messages, messages.length, isStreaming, localMessages.length]);
  
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
    };
    
    requestAnimationFrame(() => requestAnimationFrame(doScroll));
  }, []);

  // Handle scroll position
  const handleScroll = useCallback(() => {
    if (!scrollContainerRef.current) return;
    
    const container = scrollContainerRef.current;
    const { scrollTop, scrollHeight, clientHeight } = container;
    const scrollDifference = scrollHeight - (scrollTop + clientHeight);
    
    setShowScrollButton(scrollDifference > 150);
  }, []);

  // Register scroll event listener
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (container) {
      container.addEventListener('scroll', handleScroll, { passive: true });
      return () => container.removeEventListener('scroll', handleScroll);
    }
  }, [handleScroll]);

  // Auto scroll on new messages
  useEffect(() => {
    const displayMessages = localMessages.length > 0 ? localMessages : messages;
    if (isStreaming || displayMessages.length > 0) {
      setTimeout(() => scrollToBottom(false), 100);
    }
  }, [localMessages, messages, isStreaming, scrollToBottom]);

  // Helper functions for processing different event types
  const handlePlanningEvents = useCallback((currentMessage: Message, event: any) => {
    const updatedMessage = { ...currentMessage };
    
    switch (event.type) {
      case 'planning_start':
        setTimeout(() => onStateUpdate?.({ currentPhase: 'planning' }), 0);
        break;
      
      case 'planning_token':
        console.log('🧠 Planning token received:', event.token);
        if (event.token && typeof event.token === 'string') {
          updatedMessage.planningThought = (updatedMessage.planningThought || '') + event.token;
        }
        break;
      
      case 'plan':
      case 'plan_complete':
        updatedMessage.plan = event.plan;
        updatedMessage.planningThought = undefined;
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
        case 'planning_start':
        case 'planning_token':
        case 'plan':
        case 'plan_complete':
          currentMessage = handlePlanningEvents(currentMessage, event);
          break;
        
        case 'phase_start':
          if (event.phase === 'execution') {
            setTimeout(() => onStateUpdate?.({ currentPhase: 'executing' }), 0);
          } else if (event.phase === 'response') {
            setTimeout(() => onStateUpdate?.({ currentPhase: 'responding' }), 0);
          }
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
  }, [onStateUpdate, handlePlanningEvents, handleTaskEvents, handleResponseEvents]);

  // Chat reset function
  const handleChatReset = useCallback(async () => {
    console.log('🔄 Chat reset initiated');
    setIsResetting(true);
    
    try {
      // Reinitialize search API
      await searchApi.reinitialize();
      
      // Clear local messages
      setLocalMessages([]);
      
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
      setLocalMessages([]);
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
  }, [onStateUpdate]);

  // Handle reset button click
  const handleResetClick = useCallback(() => {
    setShowResetConfirm(true);
  }, []);

  // Send message
  const handleSendMessage = useCallback(async (message?: string) => {
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
    
    if (!inputText.trim() || isStreaming) return;

    if (!isChatStarted) {
      onStateUpdate?.({ isChatStarted: true });
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      sender: "user",
      content: inputText.trim(),
      timestamp: Date.now()
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
    setLocalMessages(prev => [...prev, userMessage, aiMessage]);
    
    // Clear input
    onStateUpdate?.({ input: "" });
    setIsStreaming(true);
    onStateUpdate?.({ currentPhase: "planning" });

    try {
      const finalIndexId = indexId || "default";
      console.log('📋 ChatAgent sending request with index_id:', finalIndexId);
      
      const response = await searchApi.chatStream({
        message: userMessage.content,
        index_id: finalIndexId as string, // Type assertion since we ensure it's not undefined
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
    }
  }, [input, indexId, isStreaming, onStateUpdate, isChatStarted, processChatEvent]);

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

    // Split content by citation markers and render with clickable citations
    const citationPattern = /\[(\d+)\]/g;
    const parts = content.split(citationPattern);
    const elements: React.ReactNode[] = [];
    
    for (let i = 0; i < parts.length; i++) {
      if (i % 2 === 0) {
        // Regular text part
        if (parts[i]) {
          elements.push(<MarkdownRenderer key={`text-${i}`} content={parts[i]} />);
        }
      } else {
        // Citation number
        const citationNum = parts[i];
        const refIndex = parseInt(citationNum) - 1;
        if (refIndex >= 0 && refIndex < references.length) {
          const ref = references[refIndex];
          elements.push(
            <sup key={`citation-${i}`} className="mx-1">
              <button
                className="inline-flex items-center px-1.5 py-0.5 rounded-full text-xs bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/30 transition"
                title="소스 보기"
                onClick={() => handleReferenceClick(ref)}
              >
                {citationNum}
              </button>
            </sup>
          );
        } else {
          elements.push(`[${citationNum}]`);
        }
      }
    }
    
    return <div className="inline">{elements}</div>;
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

  // Render plan
  const renderPlan = (plan: Plan, messageId: string) => (
    <div className="mt-4 space-y-3">
      <div className="flex items-center gap-2 mb-3">
        <Settings className="h-4 w-4 text-purple-400" />
        <span className="text-sm font-medium text-purple-300">Execution Plan</span>
      </div>
      
      {plan.overview && (
        <div className="p-3 bg-purple-950/30 border border-purple-500/30 rounded-lg">
          <div className="text-purple-200 text-sm">{plan.overview}</div>
        </div>
      )}

      {plan.direct_response && (
        <div className="p-3 bg-green-950/30 border border-green-500/30 rounded-lg">
          <div className="text-green-200 text-sm">
            <strong>Direct Response Available</strong>
          </div>
        </div>
      )}

      {plan.tasks && plan.tasks.length > 0 && (
        <div className="space-y-2">
          {plan.tasks.map((task, index) => (
            <div key={index} className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-3">
              <div className="flex items-center gap-3">
                <div className="flex-shrink-0">
                  {task.status === 'pending' && (
                    <div className="w-6 h-6 rounded-full border-2 border-gray-400 flex items-center justify-center">
                      <Clock className="w-3 h-3 text-gray-400" />
                    </div>
                  )}
                  {task.status === 'executing' && (
                    <div className="w-6 h-6 rounded-full bg-yellow-500/20 border border-yellow-400 flex items-center justify-center">
                      <Cog className="w-3 h-3 text-yellow-400 animate-spin-slow" />
                    </div>
                  )}
                  {task.status === 'completed' && (
                    <div className="w-6 h-6 rounded-full bg-green-500/20 border border-green-400 flex items-center justify-center">
                      <CheckCircle className="w-3 h-3 text-green-400" />
                    </div>
                  )}
                  {task.status === 'failed' && (
                    <div className="w-6 h-6 rounded-full bg-red-500/20 border border-red-400 flex items-center justify-center">
                      <AlertCircle className="w-3 h-3 text-red-400" />
                    </div>
                  )}
                </div>
                
                <div className="flex-1">
                  <p className="text-white text-sm font-medium">{task.title}</p>
                  <p className="text-white/70 text-xs">{task.description}</p>
                  <div className="flex items-center gap-2 mt-1">
                    {task.tool_name && (
                      <span className="px-2 py-1 bg-cyan-500/20 border border-cyan-400/30 rounded text-xs text-cyan-300">
                        {task.tool_name}
                      </span>
                    )}
                    {task.execution_time && (
                      <span className="text-xs text-white/40">
                        ({task.execution_time.toFixed(2)}s)
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

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
            
            {(() => {
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
                        {/* Streaming and no content: show loading */}
                        {!message.content && !message.planningThought && message.isStreaming && (
                          <div className="flex items-center justify-center py-3">
                            <MessageLoading />
                          </div>
                        )}
                        
                        {/* Show planning thought while planning */}
                        {message.planningThought && (
                          <div className="p-3 bg-purple-950/30 border border-purple-500/30 rounded-lg">
                            <div className="flex items-center gap-2 mb-2">
                              <Brain className="h-4 w-4 text-purple-400 animate-pulse" />
                              <span className="text-sm font-medium text-purple-300">Planning your search...</span>
                            </div>
                            <p className="text-white/60 text-xs whitespace-pre-wrap font-mono">
                              {message.planningThought}
                            </p>
                          </div>
                        )}
                        
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
            <div className="relative bg-gradient-to-r from-gray-900/90 to-gray-800/90 border border-white/20 rounded-full backdrop-blur-xl shadow-2xl">
              <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/10 via-purple-500/10 to-pink-500/10 rounded-full animate-pulse" />
              <div className="relative p-4 flex items-center">
                <div className="flex-shrink-0 mr-3">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-cyan-500/20 to-purple-500/20 flex items-center justify-center">
                    <Sparkles className="w-5 h-5 text-cyan-400 animate-pulse" />
                  </div>
                </div>
                {/* Reset Button */}
                {isChatStarted && (
                  <button 
                    type="button"
                    onClick={handleResetClick}
                    disabled={isResetting}
                    className="p-2 rounded-full hover:bg-white/5 transition-all group mr-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    title="Reset Chat"
                  >
                    {isResetting ? (
                      <Loader2 className="w-5 h-5 text-orange-400 animate-spin" />
                    ) : (
                      <RotateCcw className="w-5 h-5 text-orange-400 group-hover:text-orange-300 transition-colors" />
                    )}
                  </button>
                )}
                
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
                  disabled={!input.trim() || isStreaming}
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

      {/* Reset Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showResetConfirm}
        onClose={() => setShowResetConfirm(false)}
        onConfirm={handleChatReset}
        title="Reset Chat"
        message="Are you sure you want to reset the chat? This will clear all messages and start over."
        confirmText="Reset"
        cancelText="Cancel"
        variant="destructive"
      />

      {/* Reset Loading Overlay */}
      {isResetting && (
        <div className="fixed inset-0 bg-black/80 z-[9999] flex items-center justify-center">
          <div className="bg-gray-900/90 border border-white/20 rounded-2xl p-8 shadow-2xl">
            <div className="flex items-center space-x-4">
              <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
              <div>
                <h3 className="text-white text-lg font-medium">Resetting chat...</h3>
                <p className="text-white/60 text-sm mt-1">Please wait a moment</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}