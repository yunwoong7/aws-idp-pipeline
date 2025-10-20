import React, { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GlowingEffect } from "@/components/ui/glowing-effect";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAlert } from "@/components/ui/alert";
import { useAuth } from "@/contexts/auth-context";
import {
    Trash2,
    Eye,
    BarChart3
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Document } from "@/types/document.types";

import { getFileIcon, getFileTypeCategory, formatFileSize, truncateFilename } from "@/utils/file-utils";

interface DocumentItemProps {
    document: Document;
    onView: (document: Document) => void;
    onDelete: (documentId: string, indexId: string) => void;
    showGlowEffect?: boolean;
    searchResults?: any[];
    isSearchMode?: boolean;
    onAnalyze?: (document: Document) => void;
    indexId: string;
}

function DocumentItemComponent({
    document,
    onView,
    onDelete,
    showGlowEffect = true,
    searchResults = [],
    isSearchMode = false,
    onAnalyze,
    indexId
}: DocumentItemProps) {
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
    const { showWarning, AlertComponent } = useAlert();
    const { canDeleteDocument, hasTabAccess } = useAuth();

    const handleDeleteClick = () => {
        setShowDeleteConfirm(true);
    };

    const handleDeleteConfirm = () => {
        onDelete(document.document_id, document.index_id);
    };

    // Extract page information for this document from search results
    const getSearchedPages = () => {
        if (!isSearchMode || !searchResults || searchResults.length === 0) {
            return [];
        }
        
        const documentPages = searchResults.filter(
            (result: any) => result.document_id === document.document_id
        );
        
        return documentPages.map((result: any) => result.page_index + 1).sort((a: number, b: number) => a - b);
    };

    // Extract the highest score for this document from search results
    const getMaxScore = () => {
        if (!isSearchMode || !searchResults || searchResults.length === 0) {
            return null;
        }
        
        const documentResults = searchResults.filter(
            (result: any) => result.document_id === document.document_id
        );
        
        if (documentResults.length === 0) return null;
        
        const scores = documentResults.map((result: any) => result._score || result.score || 0);
        return Math.max(...scores);
    };

    const searchedPages = getSearchedPages();
    const maxScore = getMaxScore();


    // Status badge using document.status only
    const getStatusBadge = (document: Document) => {
        const rawStatus = document.status || '';
        const status = String(rawStatus).toLowerCase();
        const analysisStatus = String(((document as any).analysis_status || '')).toLowerCase();
        const isConcurrent = status === 'react_finalizing' && analysisStatus === 'processing';

        // Map statuses to label and style
        const statusMap: Record<string, { label: string; className: string }> = {
            pending_upload: { label: 'Pending upload', className: 'bg-slate-500/20 text-slate-300 border-slate-500/30' },
            uploading: { label: 'Uploading', className: 'bg-blue-500/20 text-blue-300 border-blue-500/30' },
            uploaded: { label: 'Uploaded', className: 'bg-blue-500/20 text-blue-300 border-blue-500/30' },
            bda_analyzing: { label: 'Analyzing (BDA)', className: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30' },
            bda_completed: { label: 'BDA completed', className: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30' },
            document_indexing_completed: { label: 'Indexing completed', className: 'bg-sky-500/20 text-sky-300 border-sky-500/30' },
            bda_skipped: { label: 'BDA skipped', className: 'bg-cyan-500/10 text-cyan-300/80 border-cyan-500/20' },
            pdf_text_extracting: { label: 'Text extracting', className: 'bg-teal-500/20 text-teal-300 border-teal-500/30' },
            pdf_text_extracted: { label: 'Text extracted', className: 'bg-teal-500/20 text-teal-300 border-teal-500/30' },
            react_analyzing: { label: 'Analyzing (AI)', className: 'bg-purple-500/20 text-purple-300 border-purple-500/30' },
            react_finalizing: { label: 'Finalizing', className: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30' },
            react_finalized: { label: 'Finalized', className: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30' },
            react_completed: { label: 'React completed', className: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30' },
            summarizing: { label: 'Summarizing', className: 'bg-amber-500/20 text-amber-300 border-amber-500/30' },
            completed: { label: 'Completed', className: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' },
        };

        if (status in statusMap) {
            // 동시 진행인 경우에는 react_analyzing으로 표시
            if (isConcurrent) {
                const sa = statusMap['react_analyzing'];
                return (
                    <Badge className={`${sa.className} text-xs`}>
                        {sa.label}
                    </Badge>
                );
            }
            const s = statusMap[status];
            return (
                <Badge className={`${s.className} text-xs`}>
                    {s.label}
                </Badge>
            );
        }

        if (status.includes('_failed') || status === 'failed' || status === 'summary_failed' || status === 'bda_failed' || status === 'react_failed' || status === 'react_finalize_failed' || status === 'error') {
            return (
                <Badge className="bg-red-500/20 text-red-400 border-red-500/30 text-xs">
                    Failed
                </Badge>
            );
        }

        // Default fallback
        return (
            <Badge className="bg-orange-500/20 text-orange-400 border-orange-500/30 text-xs">
                Processing
            </Badge>
        );
    };

    // Pipeline progress visualization
    const getStageIndex = (document: Document) => {
        const rawStatus = document.status || '';
        const status = String(rawStatus).toLowerCase();
        const order = [
            'pending_upload',
            'uploading',
            'uploaded',
            'bda_analyzing',
            'document_indexing_completed',
            'pdf_text_extracting',
            'pdf_text_extracted',
            'react_analyzing',
            'react_finalizing',
            'react_finalized',
            'summarizing',
            'completed',
        ];
        const normalize = (s: string) => {
            if (s === 'bda_skipped') return 'pdf_text_extracting';
            if (s === 'bda_completed') return 'document_indexing_completed';
            if (s === 'summary_failed') return 'summarizing';
            if (s === 'react_failed') return 'react_analyzing';
            if (s === 'react_finalize_failed') return 'react_finalizing';
            if (s === 'react_completed') return 'react_finalized';
            if (s === 'error') return 'react_analyzing';
            if (s.includes('indexing')) return 'document_indexing_completed';
            return s;
        };
        const idx = order.indexOf(normalize(status));
        if (idx >= 0) return idx;
        // fallback heuristics
        if (status.includes('completed')) return order.indexOf('completed');
        if (status.includes('extract')) return order.indexOf('pdf_text_extracting');
        if (status.includes('analy')) return order.indexOf('react_analyzing');
        return 0;
    };

    const stageIndex = getStageIndex(document);
    const totalStages = 11; // reflect added intermediate stage
    const progressPercent = Math.min(100, Math.max(0, Math.round((stageIndex / totalStages) * 100)));
    const currentStatus = String((document.status || '')).toLowerCase();
    const isCompleted = currentStatus === 'completed';
    const isFailed = currentStatus.includes('_failed') || currentStatus === 'failed' || currentStatus === 'error';


    return (
                    <Card className="group transition-all duration-300 hover:shadow-[0_8px_16px_rgb(0_0_0/0.4)] border-white/[0.1] hover:border-white/[0.2] bg-black w-full">
            <CardContent className="p-4">
                {/* Glowing Effect */}
                {false && (
                    <GlowingEffect
                        variant="default"
                        proximity={80}
                        spread={30}
                        borderWidth={1}
                        movementDuration={2}
                        className="opacity-20 group-hover:opacity-40"
                    />
                )}

                {/* Horizontal layout for full width */}
                <div className="flex items-center justify-between gap-4">
                    {/* Left side: File info */}
                    <div className="flex items-center gap-4 flex-1 min-w-0">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-slate-700 to-slate-800 flex items-center justify-center flex-shrink-0">
                                {getFileIcon(document.file_name, "h-5 w-5")}
                            </div>
                            <div className="flex-1 min-w-0">
                                <h3 className="text-sm font-medium text-white leading-tight mb-1 break-all" title={document.file_name}>
                                    <span className="hidden xl:inline">{truncateFilename(document.file_name, 60)}</span>
                                    <span className="hidden lg:inline xl:hidden">{truncateFilename(document.file_name, 45)}</span>
                                    <span className="hidden md:inline lg:hidden">{truncateFilename(document.file_name, 35)}</span>
                                    <span className="inline md:hidden">{truncateFilename(document.file_name, 25)}</span>
                                </h3>
                                <div className="flex items-center gap-2 mb-1">
                                    {getStatusBadge(document)}
                                    {/* File type category badge */}
                                    <Badge className="bg-indigo-500/20 text-indigo-400 border-indigo-500/30 text-xs">
                                        {getFileTypeCategory(document.file_name)}
                                    </Badge>
                                    {/* Display search score (only during search) */}
                                    {isSearchMode && maxScore !== null && (
                                        <Badge className="bg-yellow-500/20 text-yellow-400 border-yellow-500/30 text-xs px-1 py-0">
                                            ⭐ {maxScore.toFixed(2)}
                                        </Badge>
                                    )}
                                    {/* Display searched page info (only during search) */}
                                    {isSearchMode && searchedPages.length > 0 && (
                                        <Badge className="bg-cyan-500/20 text-cyan-400 border-cyan-500/30 text-xs px-1 py-0">
                                            p.{searchedPages.length > 3 
                                                ? `${searchedPages.slice(0, 3).join(', ')}...` 
                                                : searchedPages.join(', ')}
                                        </Badge>
                                    )}
                                    <span className="text-xs text-slate-400">
                                        {formatFileSize(document.file_size)}
                                    </span>
                                </div>
                                {/* Progress bar (hidden on completed) */}
                                {!isCompleted && !isFailed && (
                                    <div className="mt-1 w-full max-w-[360px]">
                                        <div className="h-1.5 bg-gradient-to-r from-white/5 via-white/10 to-white/5 rounded-full overflow-hidden relative">
                                            <div
                                                className={cn(
                                                    "h-full rounded-full transition-all",
                                                    progressPercent < 33 ? "bg-gradient-to-r from-cyan-400/80 to-sky-400/80" : progressPercent < 66 ? "bg-gradient-to-r from-purple-400/80 to-fuchsia-400/80" : "bg-gradient-to-r from-emerald-400/80 to-teal-400/80"
                                                )}
                                                style={{ width: `${progressPercent}%` }}
                                            />
                                            <div className="absolute inset-0 animate-pulse opacity-30 bg-[radial-gradient(circle_at_10%_50%,rgba(255,255,255,0.15),transparent_40%),radial-gradient(circle_at_90%_50%,rgba(255,255,255,0.15),transparent_40%)]" />
                                        </div>
                                        <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                                            <span>Start</span>
                                            <span>{progressPercent}%</span>
                                            <span>Done</span>
                                        </div>
                                    </div>
                                )}
                                {/* Description (truncated) */}
                                {document.description && (
                                    <p className="text-xs text-slate-400 line-clamp-1 leading-tight">
                                        {document.description}
                                    </p>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Right side: Actions */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onView(document)}
                            className="bg-transparent border-white/10 text-cyan-400 hover:bg-cyan-500/20 hover:border-cyan-400 hover:text-cyan-300 transition-all duration-200 h-8 text-xs px-3"
                        >
                            <Eye className="w-3 h-3 mr-1" />
                            View
                        </Button>
                        
                        {hasTabAccess('analysis') && (
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => {
                                    if (document.status !== 'completed') {
                                        showWarning('Document Not Ready', 'This document is not ready for analysis. Only completed documents can be analyzed.');
                                        return;
                                    }
                                    onAnalyze?.(document);
                                }}
                                className="bg-transparent border-purple-500/30 text-purple-400 hover:bg-purple-500/20 hover:border-purple-400 hover:text-purple-300 transition-all duration-200 h-8 text-xs px-3"
                            >
                                <BarChart3 className="w-3 h-3 mr-1" />
                                Analyze
                            </Button>
                        )}

                        {canDeleteDocument(indexId) && (
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={handleDeleteClick}
                                className="h-8 w-8 p-0 opacity-60 group-hover:opacity-100 transition-opacity hover:bg-red-500/20 hover:text-red-400"
                            >
                                <Trash2 className="w-3 h-3" />
                            </Button>
                        )}
                    </div>
                </div>
            </CardContent>
            
            {/* Delete Confirmation Dialog */}
            <ConfirmDialog
                isOpen={showDeleteConfirm}
                onClose={() => setShowDeleteConfirm(false)}
                onConfirm={handleDeleteConfirm}
                title="Delete Document"
                message={`Are you sure you want to delete "${document.file_name}"? This action cannot be undone.`}
                confirmText="Delete"
                cancelText="Cancel"
                variant="destructive"
            />
            
            {/* Alert Component */}
            {AlertComponent}
        </Card>
    );
}

export const DocumentItem = React.memo(DocumentItemComponent);