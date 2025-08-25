"use client";

import { useState, useRef, useCallback, useEffect, useMemo } from "react";
import { cn } from "@/lib/utils";
import Image from "next/image";
import {
    X,
    FileIcon,
    ArrowDown,
    Download,
    ImageIcon,
    ChevronDown,
    ChevronRight,
    Wrench,
    Cog,
    CheckCircle,
    FileText,
    RotateCcw,
    Send,
    Sparkles,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import * as React from "react";
import { MessageLoading } from "@/components/ui/message-loading";
import { MarkdownRenderer } from "@/components/ui/markdown-renderer";
import { AttachedContent } from "@/types/chat.types";
import { SecureImage } from "@/components/ui/secure-image";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

import { documentApi } from "@/lib/api";


// Utility function to access SecureImage's cache
const getPreloadedImageUrls = (references: any[], projectId: string): { [key: string]: string } => {
    const preloadedUrls: { [key: string]: string } = {};
    
    references.forEach(ref => {
        if (ref.type === 'image' && ref.image_uri && projectId) {
            // Generate the same cache key format as SecureImage
            const cacheKey = `${ref.image_uri}::${projectId}`;
            
            // Get URL from global cache (same as SecureImage)
            try {
                const urlCache = (window as any).__secureImageCache__;
                if (urlCache && urlCache.has(cacheKey)) {
                    const cached = urlCache.get(cacheKey);
                    const now = Date.now();
                    const expirationTime = cached.timestamp + (cached.expiration * 1000) - 60000;
                    
                    if (now <= expirationTime) {
                        preloadedUrls[ref.image_uri] = cached.url;
                    }
                }
            } catch (error) {
                console.log('Failed to access cache:', error);
            }
        }
    });
    
    return preloadedUrls;
};

type MessageChunk = {
    type: "text" | "tool_use" | "tool_result" | "image" | "document";
    text?: string;
    name?: string;
    input?: string;
    image_data?: string;
    mime_type?: string;
    id?: string;
    index: number;
    filename?: string;
}

interface TextContentItem {
    id: string;
    type: "text";
    content: string;
    timestamp: number;
}

interface ToolUseContentItem {
    id: string;
    type: "tool_use";
    name: string;
    input: string;
    timestamp: number;
    index?: number;
    collapsed?: boolean;
    requiresApproval?: boolean;
    approved?: boolean;
}

interface ToolResultContentItem {
    id: string;
    type: "tool_result";
    result: string;
    timestamp: number;
    collapsed?: boolean;
}

interface ImageContentItem {
    id: string;
    type: "image";
    imageData: string;
    mimeType: string;
    timestamp: number;
}

interface DocumentContentItem {
    id: string;
    type: "document";
    filename: string;
    fileType: string;
    fileSize: number;
    timestamp: number;
    file_uri?: string;
    fileId?: string;
}

interface FileAttachment {
    id: string;
    file: File;
    type: string;
    file_uri?: string;
    fileId?: string;
    previewUrl?: string;
}

interface ZoomedImageState {
    isOpen: boolean;
    imageData: string;
    mimeType: string;
}

interface CommandSuggestion {
    icon: React.ReactNode;
    label: string;
    description: string;
    prefix: string;
}

type ContentItem = TextContentItem | ToolUseContentItem | ToolResultContentItem | ImageContentItem | DocumentContentItem;

interface Reference {
    type: string;
    title: string;
    display_name: string;
    file_name: string;
    page_number: number;
    value: string; // URL for image click
    image_presigned_url: string;
    file_presigned_url: string;
    page_id: string;
    document_id: string;
    project_id: string;
    created_at: string;
    page_index?: number;
    tool_name?: string;
    seq?: number;
    metadata?: {
        [key: string]: any;
    };
    file_uri?: string;
    image_uri?: string;
}

interface Message {
    id: string;
    sender: "user" | "ai";
    content: string;
    contentItems: ContentItem[];
    isStreaming?: boolean;
    references?: Reference[];
    attachedContent?: AttachedContent[];
    attachedFiles?: FileAttachment[];
}

interface UseAutoResizeTextareaProps {
    minHeight: number;
    maxHeight?: number;
}

function useAutoResizeTextarea({
    minHeight,
    maxHeight,
}: UseAutoResizeTextareaProps) {
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    const adjustHeight = useCallback(
        (reset?: boolean) => {
            const textarea = textareaRef.current;
            if (!textarea) return;

            if (reset) {
                textarea.style.height = `${minHeight}px`;
                return;
            }

            textarea.style.height = `${minHeight}px`;
            const newHeight = Math.max(
                minHeight,
                Math.min(
                    textarea.scrollHeight,
                    maxHeight ?? Number.POSITIVE_INFINITY
                )
            );

            textarea.style.height = `${newHeight}px`;
        },
        [minHeight, maxHeight]
    );

    useEffect(() => {
        const textarea = textareaRef.current;
        if (textarea) {
            textarea.style.height = `${minHeight}px`;
        }
    }, [minHeight]);

    return { textareaRef, adjustHeight };
}


interface AnalysisInterfaceProps {
    messages: Message[];
    input: string;
    setInput: (value: string) => void;
    onSendMessage: () => void;
    isStreaming: boolean;
    attachments: FileAttachment[];
    attachedContent?: AttachedContent[];
    onRemoveAttachedContent?: (id: string) => void;
    onFileUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
    onRemoveAttachment: (id: string) => void;
    onAttachButtonClick: () => void;
    fileInputRef: React.RefObject<HTMLInputElement | null>;
    className?: string;
    height?: string;
    showScrollButton?: boolean;
    onScrollToBottom?: () => void;
    zoomedImage?: ZoomedImageState;
    onSetZoomedImage?: (state: ZoomedImageState) => void;
    renderContentItem?: (item: ContentItem, index: number, isStreaming: boolean, messageId: string) => React.ReactNode;
    showCommandSuggestions?: boolean;
    commandSuggestions?: CommandSuggestion[];
    onToolApproval?: (toolItem: ToolUseContentItem, approved: boolean) => Promise<void>;

    onImageClick?: (references: Reference[], imageIndex: number, preloadedImageUrls?: { [key: string]: string }) => void;
    onPdfClick?: (ref: Reference) => void;
    onToolToggle?: (messageId: string, itemId: string) => void;
    autoFocusAfterSend?: boolean;
    externalTextareaRef?: React.RefObject<HTMLTextAreaElement | null>;

    indexId?: string;
    selectedDocument?: {
        document_id: string;
        file_name: string;
        file_type: string;
        status: string;
    } | null;
    selectedSegment?: number;
    onChatReset?: () => void;
}

export function AnalysisInterface({
    messages,
    input,
    setInput,
    onSendMessage,
    isStreaming,
    attachments,
    attachedContent = [],
    onRemoveAttachedContent,
    onFileUpload,
    onRemoveAttachment,
    onAttachButtonClick,
    fileInputRef,
    className,
    height = "h-full",
    showScrollButton = false,
    onScrollToBottom,
    zoomedImage,
    onSetZoomedImage,
    renderContentItem,
    showCommandSuggestions = true,
    commandSuggestions,
    onToolApproval,
    onImageClick,
    onPdfClick,
    onToolToggle,
    autoFocusAfterSend = true,
    externalTextareaRef,
    indexId,
    selectedDocument,
    selectedSegment,
    onChatReset
}: AnalysisInterfaceProps) {
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const commandPaletteRef = useRef<HTMLDivElement>(null);
    const FADE_DURATION = 800;

    const [showCommandPalette, setShowCommandPalette] = useState(false);
    const [activeSuggestion, setActiveSuggestion] = useState<number>(-1);
    const [recentCommand, setRecentCommand] = useState<string | null>(null);
    const [isComposing, setIsComposing] = useState(false);
    const [userHasScrolled, setUserHasScrolled] = useState(false);
    const [internalShowScrollButton, setInternalShowScrollButton] = useState(false);
    const [showResetConfirm, setShowResetConfirm] = useState(false);
    const isNearBottomRef = useRef(true);
    // Persist tool collapsed state independently of streaming/typing
    const [toolCollapsedById, setToolCollapsedById] = useState<Record<string, boolean>>({});
    const [resultCollapsedById, setResultCollapsedById] = useState<Record<string, boolean>>({});

    // Derive stable keys for collapse state so streaming/typing won't reset UI
    const getIdKey = useCallback((id?: string) => (id ? `id:${id}` : ''), []);
    const getNameKey = useCallback((name?: string) => (name ? `name:${name}` : ''), []);

    const getCollapsedForItem = useCallback((item: ToolUseContentItem) => {
        const idKey = getIdKey(item.id);
        const nameKey = getNameKey(item.name);
        if (idKey && toolCollapsedById[idKey] !== undefined) return toolCollapsedById[idKey];
        if (nameKey && toolCollapsedById[nameKey] !== undefined) return toolCollapsedById[nameKey];
        return item.collapsed ?? true;
    }, [toolCollapsedById, getIdKey, getNameKey]);

    const toggleCollapsedForItem = useCallback((item: ToolUseContentItem) => {
        setToolCollapsedById(prev => {
            const idKey = getIdKey(item.id);
            const nameKey = getNameKey(item.name);
            const current = (idKey && prev[idKey] !== undefined)
                ? prev[idKey]
                : (nameKey && prev[nameKey] !== undefined)
                    ? prev[nameKey]
                    : (item.collapsed ?? true);
            const nextVal = !current;
            return {
                ...prev,
                ...(idKey ? { [idKey]: nextVal } : {}),
                ...(nameKey ? { [nameKey]: nextVal } : {}),
            };
        });
    }, [getIdKey, getNameKey]);

    // Result collapse state lifted to parent to avoid flicker on re-renders
    const getResultCollapsedForItem = useCallback((item: ToolUseContentItem) => {
        const idKey = getIdKey(item.id);
        const nameKey = getNameKey(item.name);
        if (idKey && resultCollapsedById[idKey] !== undefined) return resultCollapsedById[idKey];
        if (nameKey && resultCollapsedById[nameKey] !== undefined) return resultCollapsedById[nameKey];
        // default collapsed true for result section
        return true;
    }, [resultCollapsedById, getIdKey, getNameKey]);

    const toggleResultCollapsedForItem = useCallback((item: ToolUseContentItem) => {
        const idKey = getIdKey(item.id);
        const nameKey = getNameKey(item.name);
        setResultCollapsedById(prev => {
            const current = (idKey && prev[idKey] !== undefined)
                ? prev[idKey]
                : (nameKey && prev[nameKey] !== undefined)
                    ? prev[nameKey]
                    : true;
            const nextVal = !current;
            return {
                ...prev,
                ...(idKey ? { [idKey]: nextVal } : {}),
                ...(nameKey ? { [nameKey]: nextVal } : {}),
            };
        });
    }, [getIdKey, getNameKey]);

    const { textareaRef, adjustHeight } = useAutoResizeTextarea({
        minHeight: 40,
        maxHeight: 120,
    });

    // Secure file opening helper function
    const handleSecureFileOpen = useCallback(async (fileUrl: string) => {
        if (!fileUrl) return;
        
        // If it's already a valid HTTP/HTTPS URL, open directly
        if (fileUrl.startsWith('http://') || fileUrl.startsWith('https://')) {
            window.open(fileUrl, '_blank');
            return;
        }
        
        // If it's an S3 URI, get pre-signed URL first
        if (fileUrl.startsWith('s3://')) {
            try {
                const response = await documentApi.getPresignedUrlFromS3Uri(fileUrl, 3600, indexId);
                window.open(response.presigned_url, '_blank');
            } catch (error) {
                console.error('Failed to get pre-signed URL:', error);
                alert('Cannot open file. Please try again later.');
            }
        } else {
            // For other URL types, try to open directly
            window.open(fileUrl, '_blank');
        }
    }, [indexId]);

    const defaultCommandSuggestions = useMemo((): CommandSuggestion[] => commandSuggestions || [], [commandSuggestions]);

    // Precompute tool results once per messages to avoid repeated scans while typing
    const toolResultsList = useMemo(() => {
        const results: ToolResultContentItem[] = [];
        for (const msg of messages) {
            for (const ci of msg.contentItems || []) {
                if ((ci as any).type === 'tool_result') {
                    results.push(ci as ToolResultContentItem);
                }
            }
        }
        results.sort((a, b) => a.timestamp - b.timestamp);
        return results;
    }, [messages]);

    const findResultAfter = useCallback((timestamp: number): ToolResultContentItem | undefined => {
        // Linear scan is acceptable due to small list sizes; replace with binary search if needed
        for (let i = 0; i < toolResultsList.length; i++) {
            const r = toolResultsList[i];
            if (r.timestamp > timestamp) return r;
        }
        return undefined;
    }, [toolResultsList]);

    const findLastResultBefore = useCallback((timestamp: number): ToolResultContentItem | undefined => {
        let last: ToolResultContentItem | undefined = undefined;
        for (let i = 0; i < toolResultsList.length; i++) {
            const r = toolResultsList[i];
            if (r.timestamp < timestamp) last = r;
            else break;
        }
        return last;
    }, [toolResultsList]);

    // Extract the last balanced JSON object from a concatenated stream like "{}{}{".
    const extractLastBalancedJsonObject = useCallback((input: string): string | null => {
        if (!input) return null;
        let inString = false;
        let escaped = false;
        let depth = 0;
        let currentStart = -1;
        let lastCompleteStart = -1;
        let lastCompleteEnd = -1;

        for (let i = 0; i < input.length; i++) {
            const ch = input[i];

            if (inString) {
                if (escaped) {
                    escaped = false;
                } else if (ch === '\\') {
                    escaped = true;
                } else if (ch === '"') {
                    inString = false;
                }
                continue;
            } else {
                if (ch === '"') {
                    inString = true;
                    continue;
                }
                if (ch === '{') {
                    if (depth === 0) {
                        currentStart = i;
                    }
                    depth++;
                } else if (ch === '}') {
                    if (depth > 0) depth--;
                    if (depth === 0 && currentStart !== -1) {
                        lastCompleteStart = currentStart;
                        lastCompleteEnd = i;
                        currentStart = -1;
                    }
                }
            }
        }

        if (lastCompleteStart !== -1 && lastCompleteEnd !== -1 && lastCompleteEnd >= lastCompleteStart) {
            return input.substring(lastCompleteStart, lastCompleteEnd + 1);
        }
        return null;
    }, []);

    // Aggregate tool_use inputs from the current item forward until a non-tool_use appears
    const getAggregatedToolInputUntilNextBreak = useCallback((messageId: string, startItemIndex: number, toolIndex?: number): string => {
        const msg = messages.find(m => m.id === messageId);
        if (!msg || typeof startItemIndex !== 'number' || typeof toolIndex !== 'number') return '';
        let result = '';
        for (let i = startItemIndex; i < msg.contentItems.length; i++) {
            const ci = msg.contentItems[i] as any;
            if (!ci) break;
            if (ci.type !== 'tool_use') break;
            if (typeof ci.index === 'number' && ci.index === toolIndex) {
                if (typeof ci.input === 'string') result += ci.input;
                continue;
            }
            // Different tool_use index means different tool call; stop here
            break;
        }
        return result;
    }, [messages]);

    // Command Palette Logic
    useEffect(() => {
        if (input.startsWith('/') && !input.includes(' ')) {
            setShowCommandPalette(true);
            
            const matchingSuggestionIndex = defaultCommandSuggestions.findIndex(
                (cmd) => cmd.prefix.startsWith(input)
            );
            
            if (matchingSuggestionIndex >= 0) {
                setActiveSuggestion(matchingSuggestionIndex);
            } else {
                setActiveSuggestion(-1);
            }
        } else {
            setShowCommandPalette(false);
        }
    }, [input, defaultCommandSuggestions]);

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            const target = event.target as Node;
            const commandButton = document.querySelector('[data-command-button]');
            
            if (commandPaletteRef.current && 
                !commandPaletteRef.current.contains(target) && 
                !commandButton?.contains(target)) {
                setShowCommandPalette(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, []);

    const selectCommandSuggestion = (index: number) => {
        const selectedCommand = defaultCommandSuggestions[index];
        setInput(selectedCommand.prefix + ' ');
        setShowCommandPalette(false);
        adjustHeight();
        
        setRecentCommand(selectedCommand.label);
        setTimeout(() => setRecentCommand(null), 2000);
    };

    // ToolUseItem component to handle useState within the component boundary
    const ToolUseItemInner: React.FC<{
        toolItem: ToolUseContentItem;
        messageId: string;
        shouldAnimate: boolean;
        isCollapsed: boolean;
        onToggleCollapsed: () => void;
        hasToolResult: boolean;
        toolResult?: ToolResultContentItem;
        resultCollapsed: boolean;
        onToggleResultCollapsed: () => void;
        effectiveInput: string;
    }> = ({ toolItem, messageId, shouldAnimate, isCollapsed, onToggleCollapsed, hasToolResult, toolResult, resultCollapsed, onToggleResultCollapsed, effectiveInput }) => {

        // Determine style based on tool execution completion
        // hasToolResult/toolResult are now passed from parent to stabilize identity

        return (
            <div 
                key={toolItem.id} 
                className="mt-2 mb-1"
            >
                <div className="relative group">
                    <div className="relative backdrop-blur-lg bg-white/[0.02] border border-white/[0.06] rounded-xl shadow-lg overflow-hidden transition-shadow duration-300 group-hover:shadow-cyan-500/10">
                        {/* Animated border glow */}
                        <div className="absolute inset-0 rounded-xl bg-gradient-to-r from-cyan-500/15 via-purple-500/8 to-pink-500/15 opacity-0 group-hover:opacity-100 transition-opacity duration-500 blur-sm"></div>
                        
                        {/* Header */}
            <div 
                className="relative flex items-center justify-between p-3 cursor-pointer bg-gradient-to-r from-slate-900/30 via-slate-800/20 to-slate-900/30 hover:from-slate-800/40 hover:via-slate-700/30 hover:to-slate-800/40 transition-colors duration-200"
                onMouseDown={(e) => e.preventDefault()}
                onClick={(e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    onToggleCollapsed();
                }}
            >
                            <div className="flex items-center gap-3">
                                {/* Icon with animated ring */}
                                <div className="relative">
                                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-400/15 to-purple-600/15 border border-cyan-400/25 flex items-center justify-center backdrop-blur-sm">
                                        {hasToolResult ? (
                                            <CheckCircle className="h-4 w-4 text-cyan-300" />
                                        ) : (
                                            <Cog className="h-4 w-4 text-cyan-300 animate-spin-slow" />
                                        )}
                                    </div>
                                    {!hasToolResult && (
                                        <div className="absolute inset-0 rounded-lg border border-cyan-400/30 animate-pulse"></div>
                                    )}
                                    {hasToolResult && (
                                        <div className="absolute inset-0 rounded-lg border border-emerald-400/20 animate-pulse"></div>
                                    )}
                                </div>
                                
                                {/* Tool info */}
                                <div className="flex flex-col">
                                    <div className="flex items-center gap-2">
                                        <span className="font-semibold text-white text-sm tracking-wide">
                                            {toolItem.name}
                                        </span>
                                        <div className="flex items-center gap-1">
                                            {hasToolResult ? (
                                                <>
                                                    <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse"></div>
                                                    <span className="text-xs text-emerald-300 font-medium">완료</span>
                                                </>
                                            ) : (
                                                <>
                                                    <div className="w-1.5 h-1.5 bg-amber-400 rounded-full animate-pulse"></div>
                                                    <span className="text-xs text-amber-300 font-medium">실행중</span>
                                                </>
                                            )}
                                        </div>
                                    </div>
                                    <div className="text-xs text-slate-400 mt-0.5 font-mono">
                                        {hasToolResult ? "작업이 성공적으로 완료되었습니다 ✨" : "도구를 실행하고 있습니다..."}
                                    </div>
                                </div>
                            </div>
                            
                            {/* Expand/collapse button */}
                            <div className="flex items-center gap-2">
                                {hasToolResult && (
                                    <div className="flex items-center gap-0.5">
                                        <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse"></div>
                                        <div className="w-1 h-1 bg-emerald-300 rounded-full animate-pulse delay-100"></div>
                                    </div>
                                )}
                                <div className="w-6 h-6 rounded-md bg-white/[0.05] border border-white/[0.08] flex items-center justify-center hover:bg-white/[0.08] transition-colors">
                                                {isCollapsed ? 
                                        <ChevronRight className="h-3 w-3 text-slate-300" /> : 
                                        <ChevronDown className="h-3 w-3 text-slate-300" />
                                    }
                                </div>
                            </div>
                        </div>
                        
                        {/* Expanded content */}
                        {!isCollapsed && (
                            <div 
                                className="relative border-t border-white/[0.05]"
                            >
                                <div className="p-3 bg-gradient-to-br from-slate-900/15 to-slate-800/15">
                                    {/* Parameters section */}
                                    <div className="flex items-center gap-2 mb-3">
                                        <div className="w-5 h-5 rounded-full bg-gradient-to-r from-cyan-400 to-purple-500 flex items-center justify-center">
                                            <Wrench className="h-2.5 w-2.5 text-white" />
                                        </div>
                                        <span className="text-xs font-semibold text-slate-200">Run Parameters</span>
                                    </div>
                                    <div className="bg-black/50 backdrop-blur-sm rounded-lg p-3 border border-white/[0.05] mb-3">
                                        <pre className="text-xs text-cyan-300 whitespace-pre-wrap break-words font-mono leading-relaxed overflow-x-auto">
                                            {(() => {
                                                const rawInput = effectiveInput || toolItem.input || '';
                                                if (!rawInput.trim() || rawInput === '{}') {
                                                    return '매개변수 없음';
                                                }
                                                
                                                // During streaming, never parse; show raw as-is
                                                if (isStreaming) {
                                                    return rawInput;
                                                }

                                                try {
                                                    // If concatenated JSON objects exist, extract the last balanced one
                                                    const candidate = extractLastBalancedJsonObject(rawInput) || rawInput;
                                                    const parsedInput = JSON.parse(candidate);
                                                    console.log('✅ JSON parsing successful, showing formatted params:', parsedInput);
                                                    return JSON.stringify(parsedInput, null, 2);
                                                } catch (jsonError: any) {
                                                    // After streaming: Attempt simple repair; if still invalid, show raw
                                                    let repaired = (extractLastBalancedJsonObject(rawInput) || rawInput).trim();
                                                    if (!repaired.startsWith('{') && rawInput.trim().startsWith('{')) repaired = '{' + repaired;
                                                    if (!repaired.endsWith('}') && rawInput.trim().endsWith('}')) repaired = repaired + '}';
                                                    try {
                                                        const repairedObj = JSON.parse(repaired);
                                                        return JSON.stringify(repairedObj, null, 2);
                                                    } catch {
                                                        return rawInput;
                                                    }
                                                }
                                            })()}
                                        </pre>
                                    </div>
                                    
                                    {/* Result section (if completed) */}
                                    {hasToolResult && toolResult && (
                                        <>
                                            {/* Result header with collapse button */}
                                            <div 
                                                className="flex items-center gap-2 mb-2 mt-2 cursor-pointer hover:bg-white/[0.02] rounded-lg p-2 -m-2 transition-colors"
                                                onMouseDown={(e) => e.preventDefault()}
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    e.preventDefault();
                                                    onToggleResultCollapsed();
                                                }}
                                            >
                                                <div className="w-5 h-5 rounded-full bg-gradient-to-r from-cyan-400 to-blue-500 flex items-center justify-center">
                                                    <FileText className="h-2.5 w-2.5 text-white" />
                                                </div>
                                                <span className="text-xs font-semibold text-cyan-200">실행 결과</span>
                                                <div className="flex-1 h-px bg-gradient-to-r from-cyan-400/20 to-transparent"></div>
                                                <div className="w-5 h-5 rounded-md bg-white/[0.05] border border-white/[0.08] flex items-center justify-center hover:bg-white/[0.08] transition-colors">
                                                    {resultCollapsed ? 
                                                        <ChevronRight className="h-3 w-3 text-cyan-300" /> : 
                                                        <ChevronDown className="h-3 w-3 text-cyan-300" />
                                                    }
                                                </div>
                                            </div>
                                            
                                            {/* Collapsible result content */}
                                            {!resultCollapsed && (
                                                <div>
                                                    <div className="bg-black/40 backdrop-blur-sm rounded-lg p-3 border border-cyan-400/15">
                                                        <div className="text-cyan-100 whitespace-pre-wrap break-words text-xs leading-relaxed font-mono selection:bg-cyan-400/20 overflow-x-auto">
                                                            {toolResult.result}
                                                        </div>
                                                    </div>
                                                </div>
                                            )}
                                        </>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        );
    };

    const ToolUseItem = React.memo(ToolUseItemInner, (prev, next) => {
        // Avoid re-render unless tool identity or visual state changes
        return (
            prev.toolItem.id === next.toolItem.id &&
            prev.toolItem.input === next.toolItem.input && // Compare input changes for streaming updates
            prev.effectiveInput === next.effectiveInput &&
            prev.isCollapsed === next.isCollapsed &&
            prev.shouldAnimate === next.shouldAnimate &&
            prev.hasToolResult === next.hasToolResult &&
            prev.toolResult?.id === next.toolResult?.id &&
            prev.resultCollapsed === next.resultCollapsed
        );
    });

    const defaultRenderContentItem = (item: ContentItem, index: number, isStreaming: boolean, messageId: string) => {
        const now = Date.now();
        const age = now - item.timestamp;
        const shouldAnimate = isStreaming && age < FADE_DURATION;
        
        if (item.type === "text") {
            // Apply fade-in and typing effect for streaming text
            const textContent = item.content;
            
            return (
                <motion.div 
                    key={item.id}
                    initial={shouldAnimate ? { opacity: 0, y: 2 } : { opacity: 1, y: 0 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ 
                        duration: shouldAnimate ? 0.3 : 0,
                        ease: "easeOut"
                    }}
                    className="prevent-scroll max-w-full w-full"
                >
                    <MarkdownRenderer content={textContent} />
                </motion.div>
            );
        }

        // Render tool use item
        if (item.type === "tool_use") {
            const toolItem = item as ToolUseContentItem;
            const collapsed = getCollapsedForItem(toolItem);
            const resultCollapsed = getResultCollapsedForItem(toolItem);
            const toolResult = findResultAfter(toolItem.timestamp);
            const hasToolResult = !!toolResult;
            const effIndex = typeof toolItem.index === 'number' ? toolItem.index : 0;
            const effectiveInput = getAggregatedToolInputUntilNextBreak(messageId, index, effIndex) || toolItem.input || '';
            
            return (
                <ToolUseItem
                    key={toolItem.id}
                    toolItem={toolItem}
                    messageId={messageId}
                    shouldAnimate={shouldAnimate}
                    isCollapsed={collapsed}
                    onToggleCollapsed={() => toggleCollapsedForItem(toolItem)}
                    hasToolResult={hasToolResult}
                    toolResult={toolResult}
                    resultCollapsed={resultCollapsed}
                    onToggleResultCollapsed={() => toggleResultCollapsedForItem(toolItem)}
                    effectiveInput={effectiveInput}
                />
            );
        }


        
        return null;
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (showCommandPalette) {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                setActiveSuggestion(prev => 
                    prev < defaultCommandSuggestions.length - 1 ? prev + 1 : 0
                );
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setActiveSuggestion(prev => 
                    prev > 0 ? prev - 1 : defaultCommandSuggestions.length - 1
                );
            } else if (e.key === 'Tab' || e.key === 'Enter') {
                e.preventDefault();
                if (activeSuggestion >= 0) {
                    selectCommandSuggestion(activeSuggestion);
                }
            } else if (e.key === 'Escape') {
                e.preventDefault();
                setShowCommandPalette(false);
            }
        } else if (e.key === "Enter" && !e.shiftKey && !isComposing) {
            e.preventDefault();
            if (!isStreaming) {
                onSendMessage();
            } else {
                // During streaming, Enter creates a new line
                const textarea = e.currentTarget;
                const currentValue = textarea.value;
                const cursorPos = textarea.selectionStart || 0;
                const newValue = currentValue.slice(0, cursorPos) + '\n' + currentValue.slice(cursorPos);
                setInput(newValue);
                // Maintain focus and set cursor position after newline
                requestAnimationFrame(() => {
                    textarea.focus();
                    textarea.setSelectionRange(cursorPos + 1, cursorPos + 1);
                    adjustHeight();
                });
            }
        }
    };

    const handleCompositionStart = () => {
        setIsComposing(true);
    };

    const handleCompositionEnd = () => {
        setIsComposing(false);
    };

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
        
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(4px) scale(0.98);
            }
            to {
                opacity: 1;
                transform: translateY(0) scale(1);
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
        
        /* Scroll prevention styles */
        .prevent-scroll {
            max-width: 100% !important;
            width: 100% !important;
            overflow: hidden !important;
            word-wrap: break-word !important;
            overflow-wrap: anywhere !important;
            word-break: break-word !important;
        }
        
        .prevent-scroll * {
            max-width: 100% !important;
            word-wrap: break-word !important;
            overflow-wrap: anywhere !important;
            word-break: break-word !important;
        }
        
        .fade-in {
            animation: fadeIn ${FADE_DURATION/1000}s ease-out forwards;
        }
        
        
        .slide-in {
            animation: slideIn ${FADE_DURATION/1000}s cubic-bezier(0.4, 0, 0.2, 1) forwards;
        }
        
        .hide-scrollbar {
            -ms-overflow-style: none !important;
            scrollbar-width: none !important;
            overflow-x: hidden !important;
        }
        .hide-scrollbar::-webkit-scrollbar {
            display: none !important;
            width: 0 !important;
            height: 0 !important;
        }
        .hide-scrollbar * {
            -ms-overflow-style: none !important;
            scrollbar-width: none !important;
            overflow-x: hidden !important;
        }
        .hide-scrollbar *::-webkit-scrollbar {
            display: none !important;
            width: 0 !important;
            height: 0 !important;
        }
        .hide-scrollbar::-webkit-scrollbar-track {
            display: none !important;
        }
        .hide-scrollbar::-webkit-scrollbar-thumb {
            display: none !important;
        }
        .hide-scrollbar::-webkit-scrollbar-corner {
            display: none !important;
        }
        
        /* Chat Interface Independent Scroll Styles */
        .chat-interface-container {
            contain: layout style paint;
            isolation: isolate;
            position: relative;
            will-change: scroll-position;
        }
        
        .chat-scroll-container {
            contain: layout style paint size;
            overscroll-behavior: contain;
            scroll-behavior: smooth;
            position: relative;
            z-index: 1;
        }
        
        .chat-scroll-container::-webkit-scrollbar {
            display: none !important;
        }
        
        .chat-scroll-container {
            scrollbar-width: none !important;
            -ms-overflow-style: none !important;
        }
        
        /* Prevent scroll interference with parent containers */
        .chat-interface-container * {
            overscroll-behavior: contain;
        }
    `;

    // Auto scroll function (double rAF to ensure layout committed)
    const scrollToBottom = useCallback((smooth = true) => {
        const el = messagesEndRef.current;
        if (!el) return;
        const doScroll = () => {
            el.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'end' });
            setUserHasScrolled(false);
            isNearBottomRef.current = true;
        };
        // Ensure DOM updates flushed before scrolling
        requestAnimationFrame(() => requestAnimationFrame(doScroll));
    }, []);

    // Scroll position detection function - 더 보수적이고 안정적으로 개선
    const handleScroll = useCallback((event?: Event) => {
        // Ensure scroll event is from our container only
        if (event && event.target !== scrollContainerRef.current) return;
        if (!scrollContainerRef.current) return;
        
        const container = scrollContainerRef.current;
        const { scrollTop, scrollHeight, clientHeight } = container;
        const isNearBottom = scrollTop + clientHeight > scrollHeight - 150; // 더 큰 임계값으로 안정성 향상
        
        // 더 보수적인 스크롤 상태 업데이트
        // 사용자가 명확하게 위로 스크롤했을 때만 userHasScrolled = true
        const scrollDifference = scrollHeight - (scrollTop + clientHeight);
        
        if (scrollDifference > 200) {
            // 하단에서 200px 이상 떨어져 있으면 사용자가 스크롤한 것으로 간주
            setUserHasScrolled(true);
        } else if (scrollDifference < 50) {
            // 하단에서 50px 이내면 하단에 있는 것으로 간주
            setUserHasScrolled(false);
        }
        // 50px ~ 200px 사이에서는 상태를 변경하지 않음 (안정적인 히스테리시스)
        
        isNearBottomRef.current = isNearBottom;
        
        // 스크롤 버튼 표시 상태 관리
        const shouldShowButton = scrollDifference > 150;
        setInternalShowScrollButton(shouldShowButton);
        
        // External callback
        if (shouldShowButton !== showScrollButton) {
            onScrollToBottom?.();
        }
    }, [showScrollButton, onScrollToBottom]);

    // Auto scroll on new message (unless user scrolled up)
    useEffect(() => {
        if (isNearBottomRef.current && !userHasScrolled) {
            const timeoutId = setTimeout(() => {
                if (isNearBottomRef.current && !userHasScrolled) {
                    scrollToBottom(false);
                }
            }, 80);
            return () => clearTimeout(timeoutId);
        }
    }, [messages, userHasScrolled, scrollToBottom]);

    // Scroll during streaming (stick to bottom unless user scrolled up)
    useEffect(() => {
        if (isStreaming && !userHasScrolled && isNearBottomRef.current) {
            const timeoutId = setTimeout(() => {
                if (isStreaming && !userHasScrolled && isNearBottomRef.current) {
                    scrollToBottom(false);
                }
            }, 120);
            return () => clearTimeout(timeoutId);
        }
    }, [isStreaming, userHasScrolled, scrollToBottom]);

    // Register scroll event listener
    useEffect(() => {
        const container = scrollContainerRef.current;
        if (container) {
            // Add scroll event listener with passive option for better performance
            container.addEventListener('scroll', handleScroll, { passive: true });
            // Initial scroll state check
            handleScroll();
            return () => container.removeEventListener('scroll', handleScroll);
        }
    }, [handleScroll]);

    // Render references (cupix-compass-ai style)
    const renderReferences = (references: Reference[], messageId: string, onPdfClick?: (ref: Reference) => void) => {
        if (!references || references.length === 0) {
            return null;
        }

        // Filter only image references
        const imageReferences = references.filter(ref => ref.type === 'image');

        return (
            <div className="mt-3 pt-2 border-t border-white/5">
                {/* Header badge */}
                {imageReferences.length > 0 && (
                    <>
                        <div className="mb-2 flex items-center">
                            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/5 border border-white/10 backdrop-blur-md text-[10px] text-white/80">
                                <ImageIcon className="w-3 h-3 text-cyan-300" />
                                <span>참조 이미지</span>
                                <span className="text-cyan-300">({imageReferences.length})</span>
                            </div>
                        </div>

                        {/* Filmstrip-style horizontal thumbnails */}
                        <div className="mb-2 -mx-1 px-1 overflow-x-auto hide-scrollbar">
                            <div className="flex gap-2.5 min-w-0">
                                {imageReferences.map((ref, index) => (
                                    <div
                                        key={index}
                                        className="relative w-24 h-24 md:w-28 md:h-28 flex-shrink-0 rounded-xl overflow-hidden bg-white/[0.04] border border-white/[0.08] shadow-sm transition-all duration-300 group cursor-pointer backdrop-blur-sm hover:shadow-lg hover:-translate-y-0.5"
                                        onClick={async () => {
                                        // 사전 정의된 방식: S3 URI -> presigned URL 생성 후 새 탭 오픈
                                        const s3Uri = ref.image_uri || ref.value;
                                        if (!s3Uri) return;
                                        try {
                                            const { presigned_url } = await documentApi.getPresignedUrlFromS3Uri(s3Uri, 3600, indexId);
                                            window.open(presigned_url, '_blank');
                                        } catch (e) {
                                            console.error('Failed to open image via presigned URL', e);
                                            // 폴백: 기존 뷰어 로직 유지
                                            if (onImageClick) {
                                                const preloadedUrls = getPreloadedImageUrls(imageReferences, indexId || '');
                                                onImageClick(imageReferences, index, preloadedUrls);
                                            } else if (ref.value) {
                                                onSetZoomedImage?.({
                                                    isOpen: true,
                                                    imageData: ref.value,
                                                    mimeType: 'image/png'
                                                });
                                            }
                                        }
                                        }}
                                    >
                                        {/* Image */}
                                        <SecureImage
                                            s3Uri={ref.image_uri || ref.value}
                                            projectId={indexId || ''}
                                            alt={ref.display_name || ref.title || `Image ${index + 1}`}
                                            className="w-full h-full object-cover transform transition-transform duration-500 group-hover:scale-105"
                                        />

                                        {/* Glow ring on hover */}
                                        <div className="pointer-events-none absolute inset-0 rounded-xl ring-0 group-hover:ring-2 ring-cyan-400/30 transition-all"></div>

                                        {/* Dark overlay on hover */}
                                        <div className="absolute inset-0 bg-gradient-to-br from-transparent via-black/10 to-black/30 opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>

                                        {/* Index badge */}
                                        <div className="absolute top-1 left-1">
                                            <div className="bg-black/60 backdrop-blur-sm border border-white/10 text-white text-[10px] rounded-full w-5 h-5 flex items-center justify-center font-semibold">
                                                {index + 1}
                                            </div>
                                        </div>

                                        {/* PDF detail button */}
                                        {ref.file_uri && onPdfClick && (
                                            <div className="absolute top-1 right-1">
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        onPdfClick(ref);
                                                    }}
                                                    className="group/pdf w-6 h-6 rounded-lg bg-white/10 backdrop-blur-md border border-white/15 hover:bg-white/20 transition-all shadow"
                                                    title="PDF detail"
                                                >
                                                    <div className="w-4 h-4 rounded-md bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center">
                                                        <FileText className="w-2.5 h-2.5 text-white" />
                                                    </div>
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    </>
                )}
            </div>
        );
    };

    return (
        <>
            <style dangerouslySetInnerHTML={{ __html: getAnimationStyles() }} />
            <div className={cn("flex flex-col bg-transparent relative chat-interface-container", height, className)}>
                {/* Background effect */}
                <div className="absolute inset-0 w-full h-full overflow-hidden pointer-events-none">
                    <div className="absolute top-0 left-1/4 w-96 h-96 bg-cyan-500/5 rounded-full mix-blend-normal filter blur-[128px] animate-pulse" />
                    <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-sky-500/5 rounded-full mix-blend-normal filter blur-[128px] animate-pulse delay-700" />
                    <div className="absolute top-1/4 right-1/3 w-64 h-64 bg-cyan-500/5 rounded-full mix-blend-normal filter blur-[96px] animate-pulse delay-1000" />
                </div>

                {/* Message area - only messages scroll */}
                <div 
                    ref={scrollContainerRef}
                    className="flex-1 overflow-y-auto hide-scrollbar relative z-10 chat-scroll-container"
                    style={{ 
                        scrollbarWidth: 'none',
                        msOverflowStyle: 'none',
                        contain: 'layout style paint',
                        isolation: 'isolate',
                    }}
                >
                    <div className="max-w-3xl mx-auto w-full p-4">
                        {messages.map((message) => (
                            message.sender === "user" ? (
                                <div key={message.id} className="mb-4 flex justify-end">
                                    <div className="max-w-[80%] bg-white/[0.08] backdrop-blur-xl rounded-2xl border border-white/[0.1] p-4">
                                        <div className="text-white/90 text-sm">
                                            {(() => {
                                                // Generate display message with attached content
                                                let displayMessage = message.content;
                                                
                                                if (message.attachedContent && message.attachedContent.length > 0) {
                                                    const attachmentDisplayText = message.attachedContent.map(item => {
                                                        if (item.type === 'document') {
                                                            return item.file_name;
                                                        }
                                                        if (item.type === 'image') {
                                                            return `Page ${item.page_number} of ${item.file_name}`;
                                                        }
                                                        return '';
                                                    }).join(' ');
                                                    
                                                    displayMessage = `${attachmentDisplayText} ${message.content}`.trim();
                                                }
                                                
                                                return <div>{displayMessage}</div>;
                                            })()}
                                            
                                            {/* Display attached files */}
                                            {message.attachedFiles && message.attachedFiles.map((attachment) => {
                                                if (attachment.type.startsWith('image/') && attachment.previewUrl) {
                                                    return (
                                                        <div key={attachment.id} className="mt-2 mb-2 max-w-full">
                                                            <Image 
                                                                src={attachment.previewUrl}
                                                                alt={`Attached image: ${attachment.file.name}`}
                                                                className="rounded-md border border-white/20 max-w-full cursor-pointer hover:opacity-90 transition-opacity"
                                                                style={{ maxHeight: "200px" }}
                                                                onClick={() => onSetZoomedImage?.({
                                                                    isOpen: true,
                                                                    imageData: attachment.previewUrl?.split(',')[1] || '',
                                                                    mimeType: attachment.type
                                                                })}
                                                                width={300}
                                                                height={200}
                                                                unoptimized
                                                            />
                                                            <div className="text-xs text-white/60 mt-1">{attachment.file.name}</div>
                                                        </div>
                                                    );
                                                } else if (!attachment.type.startsWith('image/')) {
                                                    // Non-image files
                                                    const fileSize = attachment.file.size < 1024 * 1024 
                                                        ? `${Math.round(attachment.file.size / 1024)} KB` 
                                                        : `${(attachment.file.size / (1024 * 1024)).toFixed(1)} MB`;
                                                    
                                                    const fileExtension = attachment.file.name.split('.').pop()?.toUpperCase() || '';
                                                    
                                                    return (
                                                        <div key={attachment.id} className="mt-2 mb-2">
                                                            <div className="flex border border-white/20 bg-white/[0.05] rounded-md p-3 max-w-[350px]">
                                                                <div className="mr-3 h-10 w-10 flex-shrink-0 flex items-center justify-center rounded-md bg-white/[0.1]">
                                                                    <FileIcon className="h-5 w-5 text-white/60" />
                                                                </div>
                                                                <div className="flex-1 min-w-0">
                                                                    <div className="flex items-center justify-between">
                                                                        <p className="text-sm font-medium text-white/90 truncate">
                                                                            {attachment.file.name}
                                                                        </p>
                                                                        <p className="ml-2 text-xs text-white/60 whitespace-nowrap">{fileExtension}</p>
                                                                    </div>
                                                                    <div className="flex items-center justify-between mt-1">
                                                                        <p className="text-xs text-white/60">
                                                                            {fileSize}
                                                                        </p>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    );
                                                }
                                                return null;
                                            })}
                                            
                                            {message.contentItems.map((item) => {
                                                if (item.type === "text") {
                                                    return null; // Skip text items as they're included in displayMessage above
                                                } 
                                                else if (item.type === "image") {
                                                    const imageItem = item as ImageContentItem;
                                                    
                                                    if (!imageItem.imageData) {
                                                        return (
                                                            <div key={imageItem.id} className="p-2 bg-red-500/20 rounded-md">
                                                                <p className="text-red-300 text-xs">Image data missing</p>
                                                            </div>
                                                        );
                                                    }
                                                    
                                                    const imgSrc = `data:${imageItem.mimeType};base64,${imageItem.imageData}`;
                                                    
                                                    return (
                                                        <div key={imageItem.id} className="mt-2 mb-2 max-w-full">
                                                            <Image 
                                                                src={imgSrc}
                                                                alt="Attached image"
                                                                className="rounded-md border border-white/20 max-w-full cursor-pointer hover:opacity-90 transition-opacity"
                                                                style={{ maxHeight: "200px" }}
                                                                onClick={() => onSetZoomedImage?.({
                                                                    isOpen: true,
                                                                    imageData: imageItem.imageData,
                                                                    mimeType: imageItem.mimeType
                                                                })}
                                                                width={300}
                                                                height={200}
                                                                unoptimized
                                                            />
                                                        </div>
                                                    );
                                                }
                                                else if (item.type === "document") {
                                                    const documentItem = item as DocumentContentItem;
                                                    const fileSize = documentItem.fileSize < 1024 * 1024 
                                                        ? `${Math.round(documentItem.fileSize / 1024)} KB` 
                                                        : `${(documentItem.fileSize / (1024 * 1024)).toFixed(1)} MB`;
                                                    
                                                    const fileExtension = documentItem.filename.split('.').pop()?.toUpperCase() || '';
                                                    
                                                    return (
                                                        <div key={documentItem.id} className="mt-2 mb-2">
                                                            <div className="flex border border-white/20 bg-white/[0.05] rounded-md p-3 max-w-[350px]">
                                                                <div className="mr-3 h-10 w-10 flex-shrink-0 flex items-center justify-center rounded-md bg-white/[0.1]">
                                                                    <FileIcon className="h-5 w-5 text-white/60" />
                                                                </div>
                                                                <div className="flex-1 min-w-0">
                                                                    <div className="flex items-center justify-between">
                                                                        <p className="text-sm font-medium text-white/90 truncate">
                                                                            {documentItem.filename}
                                                                        </p>
                                                                        <p className="ml-2 text-xs text-white/60 whitespace-nowrap">{fileExtension}</p>
                                                                    </div>
                                                                    <div className="flex items-center justify-between mt-1">
                                                                        <p className="text-xs text-white/60">
                                                                            {fileSize}
                                                                        </p>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    );
                                                }
                                                return null;
                                            })}
                                        </div>
                                    </div>
                                </div>
                            ) : (
                                <div key={message.id} className="mb-6 max-w-full">
                                    <div className="flex items-start gap-2">
                                        <div className="flex-1 max-w-full">
                                                                        <div className="text-white/90 text-sm break-words overflow-wrap-anywhere max-w-full">
                                {/* Streaming and no content: show loading */}
                                {message.contentItems.length === 0 && message.isStreaming && !message.content && isStreaming && (
                                    <div className="flex items-center justify-center py-3">
                                        <MessageLoading />
                                    </div>
                                )}
                                               {(() => {
                                                   // Identify last tool_result to aggregate following text chunks
                                                   let lastToolResultIndex = -1;
                                                   for (let i = 0; i < message.contentItems.length; i++) {
                                                       const it = message.contentItems[i] as any;
                                                       if (it && it.type === 'tool_result') lastToolResultIndex = i;
                                                   }

                                                   const trailingText = message.contentItems
                                                       .slice(lastToolResultIndex + 1)
                                                       .filter(ci => (ci as any).type === 'text')
                                                       .map(ci => (ci as any).content || '')
                                                       .join('');

                                                   // Compute last occurrence index for each tool_use id to avoid duplicate snapshots
                                                   const lastToolUseIndexById: Record<string, number> = {};
                                                   for (let i = 0; i < message.contentItems.length; i++) {
                                                       const it = message.contentItems[i] as any;
                                                       if (it && it.type === 'tool_use' && typeof it.id === 'string') {
                                                           lastToolUseIndexById[it.id] = i;
                                                       }
                                                   }
 
                                                   return (
                                                       <>
                                                           {message.contentItems.map((item, index) => {
                                                               // Skip trailing text items; we will render them combined below
                                                               if (lastToolResultIndex >= 0 && index > lastToolResultIndex && (item as any).type === 'text') {
                                                                   return null;
                                                               }
                                                               // Special handling for tool_use item
                                                               if (item.type === 'tool_use' && onToolApproval) {
                                                                   const toolItem = item as ToolUseContentItem;
                                                                    // Overwrite semantics: only render the last snapshot of this tool_use id
                                                                    if (toolItem.id && lastToolUseIndexById[toolItem.id] !== index) {
                                                                        return null;
                                                                    }
                                                                   return (
                                                                       <div key={item.id} className="mt-2 mb-2">
                                                                           <div className="bg-blue-900/20 rounded-md p-3 text-xs border border-blue-700/50 shadow-lg">
                                                                               <div className="font-medium text-blue-300 mb-1 flex justify_between items-center">
                                                                                   <div className="flex items-center gap-2">
                                                                                       <Wrench className="h-4 w-4" />
                                                                                       <span>Tool use: {toolItem.name}</span>
                                                                                   </div>
                                                                               </div>
                                                                               {/* Approval button */}
                                                                               {toolItem.requiresApproval && !toolItem.approved && (
                                                                                   <div className="mt-3 pt-3 border-t border-blue-700/30">
                                                                                       <div className="flex items-center justify-between">
                                                                                           <div className="flex items-center gap-2 text-blue-300">
                                                                                               <div className="w-2 h-2 bg-blue-400 rounded-full animate-pulse"></div>
                                                                                               <span className="text-sm">Waiting for execution approval...</span>
                                                                                           </div>
                                                                                           <div className="flex gap-2">
                                                                                               <button 
                                                                                                   className="bg-blue-600/20 hover:bg-blue-600/30 border border-blue-500/50 text-blue-300 hover:text-blue-200 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-200 flex items-center gap-1"
                                                                                                   onClick={() => onToolApproval(toolItem, true)}
                                                                                               >
                                                                                                   <span className="text-green-400">✓</span>
                                                                                                   승인
                                                                                               </button>
                                                                                               <button 
                                                                                                   className="bg-gray-600/20 hover:bg-gray-600/30 border border-gray-500/50 text-gray-300 hover:text-gray-200 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-200 flex items_center gap-1"
                                                                                                   onClick={() => onToolApproval(toolItem, false)}
                                                                                               >
                                                                                                   <span className="text-red-400">✗</span>
                                                                                                   거부
                                                                                               </button>
                                                                                           </div>
                                                                                       </div>
                                                                                   </div>
                                                                               )}
                                                                               {/* Tool parameters (only if not empty) */}
                                                                               {(() => {
                                                                                   const rawInput = toolItem.input || '';
                                                                                   if (!rawInput.trim() || rawInput === '{}') {
                                                                                       return null;
                                                                                   }
                                                                                   try {
                                                                                       const parsedInput = JSON.parse(rawInput);
                                                                                       const hasParams = Object.keys(parsedInput).length > 0;
                                                                                       if (hasParams) {
                                                                                           return (
                                                                                               <div className="mt-2 p-2 bg-gray-900/50 rounded border border-gray-800">
                                                                                                   <div className="text-xs text-blue-400 mb-1">Parameters:</div>
                                                                                                   <pre className="text-xs text_green-400 whitespace-pre-wrap break-all">
                                                                                                       {JSON.stringify(parsedInput, null, 2)}
                                                                                                   </pre>
                                                                                               </div>
                                                                                           );
                                                                                       }
                                                                                       return null;
                                                                                   } catch (jsonError) {
                                                                                       const isStreaming = rawInput.includes('}{') || rawInput.endsWith('{') || (!rawInput.endsWith('}') && rawInput.startsWith('{'));
                                                                                       if (isStreaming) {
                                                                                           return (
                                                                                               <div className="mt-2 p-2 bg-gray-900/50 rounded border border-gray-800">
                                                                                                   <div className="text-xs text-blue-400 mb-1 flex items-center gap-2">
                                                                                                       Parameters:
                                                                                                       <div className="w-3 h-3 border border-blue-400 border-t-transparent rounded-full animate-spin"></div>
                                                                                                   </div>
                                                                                                   <div className="text-xs text-amber-400 italic">로딩 중...</div>
                                                                                               </div>
                                                                                           );
                                                                                       } else {
                                                                                           return (
                                                                                               <div className="mt-2 p-2 bg-gray-900/50 rounded border border-gray-800">
                                                                                                   <div className="text-xs text-blue-400 mb-1">Parameters:</div>
                                                                                                   <pre className="text-xs text-green-400 whitespace-pre-wrap break-words overflow-x-auto">
                                                                                                       {rawInput}
                                                                                                   </pre>
                                                                                               </div>
                                                                                           );
                                                                                       }
                                                                                   }
                                                                               })()}
                                                                           </div>
                                                                       </div>
                                                                   );
                                                               }
                                                               // General content item handling
                                                               return (
                                                                   <div key={item.id || `${message.id}-content-${index}`}>
                                                                       {renderContentItem ? 
                                                                           renderContentItem(item, index, !!message.isStreaming, message.id) :
                                                                           defaultRenderContentItem(item, index, !!message.isStreaming, message.id)}
                                                                   </div>
                                                               );
                                                           })}
                                                           {lastToolResultIndex >= 0 && trailingText && (
                                                               <div className="mt-1">
                                                                   <MarkdownRenderer content={trailingText} />
                                                               </div>
                                                           )}
                                                       </>
                                                   );
                                               })()}
                                            </div>
                                            
                                                                        {/* Render References */}
                            {message.references && message.references.length > 0 && (
                                                                        renderReferences(message.references, message.id, onPdfClick)
                            )}
                                        </div>
                                    </div>
                                </div>
                            )
                        ))}
                                            <div ref={messagesEndRef} />
                </div>
                </div>
                
                {/* Scroll to bottom button */}
                {(showScrollButton || internalShowScrollButton) && (
                    <div className="absolute bottom-20 right-8 z-[100]">
                        <button
                            onClick={() => {
                                setUserHasScrolled(false); // Reset user scroll state
                                setInternalShowScrollButton(false); // Hide button
                                scrollToBottom();
                                onScrollToBottom?.();
                            }}
                            className="bg-white/20 hover:bg-white/30 text-white p-3 rounded-full shadow-xl transition-all duration-200 flex items-center justify-center transform hover:scale-110 backdrop-blur-xl border border-white/20"
                            aria-label="Scroll to bottom"
                        >
                            <ArrowDown className="h-5 w-5" />
                        </button>
                    </div>
                )}
                
                {/* Input area - fixed at bottom */}
                <div className={cn(
                    "flex-shrink-0 z-20 px-4 pt-4 pb-6 bg-black/60 backdrop-blur border-t border-white/10",
                    attachedContent && attachedContent.length > 0 ? "h-36" : "h-24"
                )}>
                    <div className="max-w-3xl mx-auto w-full">
                        {/* Attached content chips */}
                        {attachedContent && attachedContent.length > 0 && (
                            <div className="mb-2 flex flex-wrap gap-2">
                                {attachedContent.map((item) => (
                                    <div key={item.id} className="flex items-center gap-2 px-2 py-1 rounded-full border border-white/15 bg-white/5 text-white/80 text-xs">
                                        <span className="uppercase text-[10px] tracking-wide opacity-70">{item.type}</span>
                                        <span className="max-w-[200px] truncate">{item.type === 'document' ? item.file_name : `${item.file_name} • p.${item.page_number}`}</span>
                                        <button
                                            className="hover:text-white/100 opacity-80"
                                            onClick={() => onRemoveAttachedContent?.(item.id)}
                                            aria-label="Remove attachment"
                                        >
                                            <X className="w-3 h-3" />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                        
                        <div className="relative bg-gradient-to-r from-gray-900/90 to-gray-800/90 border border-white/20 rounded-full backdrop-blur-xl shadow-2xl">
                            <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/10 via-purple-500/10 to-pink-500/10 rounded-full animate-pulse" />
                            {/* Command palette */}
                            <AnimatePresence>
                                {showCommandPalette && (
                                    <motion.div 
                                        ref={commandPaletteRef}
                                        className="absolute left-4 right-4 bottom-full mb-2 backdrop-blur-xl bg-black/90 rounded-lg z-50 shadow-lg border border-white/10 overflow-hidden"
                                        initial={{ opacity: 0, y: 5 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0, y: 5 }}
                                        transition={{ duration: 0.15 }}
                                    >
                                        <div className="py-1 bg-black/95">
                                            {defaultCommandSuggestions.map((suggestion, index) => (
                                                <motion.div
                                                    key={suggestion.prefix}
                                                    className={cn(
                                                        "flex items-center gap-2 px-3 py-2 text-xs transition-colors cursor-pointer",
                                                        activeSuggestion === index 
                                                            ? "bg-white/10 text-white" 
                                                            : "text-white/70 hover:bg-white/5"
                                                    )}
                                                    onClick={() => selectCommandSuggestion(index)}
                                                    initial={{ opacity: 0 }}
                                                    animate={{ opacity: 1 }}
                                                    transition={{ delay: index * 0.03 }}
                                                >
                                                    <div className="w-5 h-5 flex items-center justify-center text-white/60">
                                                        {suggestion.icon}
                                                    </div>
                                                    <div className="font-medium">{suggestion.label}</div>
                                                    <div className="text-white/40 text-xs ml-1">
                                                        {suggestion.prefix}
                                                    </div>
                                                </motion.div>
                                            ))}
                                        </div>
                                    </motion.div>
                                )}
                            </AnimatePresence>

                            <div className="relative p-4 flex items-center">
                                <div className="flex-shrink-0 mr-3">
                                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-cyan-500/20 to-purple-500/20 flex items-center justify-center">
                                        <Sparkles className="w-5 h-5 text-cyan-400 animate-pulse" />
                                    </div>
                                </div>
                                {/* Reset Button - Only show if there are messages */}
                                {messages.length > 0 && onChatReset && (
                                    <button 
                                        type="button"
                                        onClick={() => setShowResetConfirm(true)}
                                        className="mr-3 p-2 rounded-full hover:bg-white/5 transition-all group"
                                        title="Reset Chat"
                                    >
                                        <RotateCcw className="w-5 h-5 text-orange-400 group-hover:text-orange-300 transition-colors" />
                                    </button>
                                )}
                                <input
                                    type="text"
                                    value={input}
                                    onChange={(e) => setInput(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
                                            e.preventDefault();
                                            if (!isStreaming) {
                                                onSendMessage();
                                            } else {
                                                // During streaming, Enter creates a new line
                                                const input = e.currentTarget;
                                                const currentValue = input.value;
                                                const cursorPos = input.selectionStart || 0;
                                                const newValue = currentValue.slice(0, cursorPos) + '\n' + currentValue.slice(cursorPos);
                                                setInput(newValue);
                                                // Maintain focus and set cursor position after newline
                                                requestAnimationFrame(() => {
                                                    input.focus();
                                                    input.setSelectionRange(cursorPos + 1, cursorPos + 1);
                                                });
                                            }
                                        }
                                    }}
                                    onCompositionStart={() => setIsComposing(true)}
                                    onCompositionEnd={() => setIsComposing(false)}
                                    placeholder="What would you like to analyze?"
                                    className="bg-transparent flex-1 outline-none text-white placeholder:text-white/50 text-lg font-medium"
                                    ref={externalTextareaRef as unknown as React.RefObject<HTMLInputElement>}
                                />
                                {/* Send button */}
                                <button
                                    onClick={onSendMessage}
                                    disabled={!input.trim() || isStreaming}
                                    className="ml-3 p-2 rounded-full bg-white/10 hover:bg-white/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    <Send className="w-4 h-4 text-white" />
                                </button>
                            </div>
                            
                            
                        </div>

                        {/* Command suggestion buttons */}
                        {showCommandSuggestions && messages.length === 0 && (
                            <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
                                {defaultCommandSuggestions.map((suggestion, index) => (
                                    <motion.button
                                        key={suggestion.prefix}
                                        onClick={() => selectCommandSuggestion(index)}
                                        className="flex items-center gap-2 px-3 py-2 bg-white/[0.02] hover:bg-white/[0.05] rounded-lg text-sm text-white/60 hover:text-white/90 transition-all relative group"
                                        initial={{ opacity: 0, y: 10 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        transition={{ delay: index * 0.1 }}
                                    >
                                        {suggestion.icon}
                                        <span>{suggestion.label}</span>
                                        <motion.div
                                            className="absolute inset-0 border border-white/[0.05] rounded-lg"
                                            initial={false}
                                            animate={{
                                                opacity: [0, 1],
                                                scale: [0.98, 1],
                                            }}
                                            transition={{
                                                duration: 0.3,
                                                ease: "easeOut",
                                            }}
                                        />
                                    </motion.button>
                                ))}
                            </div>
                        )}
                        
                        {/* Hidden file input field */}
                        <input
                            type="file"
                            ref={fileInputRef}
                            onChange={onFileUpload}
                            className="hidden"
                            multiple
                            accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.txt,.rtf,.odt,.dwg,.dxf,.xls,.xlsx,.csv,.png,.jpg,.jpeg,.gif,.bmp,.tiff,.tif,.webp,.mp4,.avi,.mov,.wmv,.flv,.mkv,.webm,.3gp,.mp3,.wav,.flac,.m4a,.aac,.ogg,.wma,.aiff"
                        />
                    </div>
                </div>
            </div>

            {/* Image zoom modal */}
            {zoomedImage?.isOpen && (
                <div 
                    className="fixed inset-0 bg-black/90 flex items-center justify-center z-50 backdrop-blur-sm"
                    onClick={() => onSetZoomedImage?.({ ...zoomedImage, isOpen: false })}
                >
                    <div className="relative max-w-[90vw] max-h-[90vh] overflow-auto p-4">
                        <div className="absolute top-4 right-4 flex gap-2 z-10">
                            <button 
                                className="bg-white/10 p-2 rounded-full text-white hover:bg-white/20 transition-colors shadow-lg backdrop-blur-sm"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
                                    const fileExtension = zoomedImage.mimeType.split('/')[1] || 'png';
                                    const fileName = `ai-generated-image-${timestamp}.${fileExtension}`;
                                    
                                    const link = document.createElement('a');
                                    link.href = `data:${zoomedImage.mimeType};base64,${zoomedImage.imageData}`;
                                    link.download = fileName;
                                    
                                    document.body.appendChild(link);
                                    link.click();
                                    document.body.removeChild(link);
                                }}
                                title="Download image"
                            >
                                <Download className="h-5 w-5" />
                            </button>
                            <button 
                                className="bg-white/10 p-2 rounded-full text-white hover:bg-red-500/20 transition-colors shadow-lg backdrop-blur-sm"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onSetZoomedImage?.({ ...zoomedImage, isOpen: false });
                                }}
                            >
                                <X className="h-5 w-5" />
                            </button>
                        </div>
                        <Image 
                            src={`data:${zoomedImage.mimeType};base64,${zoomedImage.imageData}`}
                            alt="Zoomed image"
                            className="max-w-full max-h-[80vh] object-contain mx-auto shadow-2xl rounded-md"
                            width={800}
                            height={600}
                            unoptimized
                        />
                    </div>
                </div>
            )}
            
            {/* Reset Confirmation Dialog */}
            <ConfirmDialog
                isOpen={showResetConfirm}
                onClose={() => setShowResetConfirm(false)}
                onConfirm={() => {
                    onChatReset?.();
                    setShowResetConfirm(false);
                }}
                title="Reset Chat"
                message="Are you sure you want to reset the chat? This will clear all messages and start over."
                confirmText="Reset"
                cancelText="Cancel"
                variant="destructive"
            />
        </>
    );
}