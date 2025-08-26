import React, { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GlowingEffect } from "@/components/ui/glowing-effect";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAlert } from "@/components/ui/alert";
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

export function DocumentItem({
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


    // Status badge using document.status
    const getStatusBadge = (document: Document) => {
        const status = document.status?.toLowerCase() || '';

        // completed = 완료
        if (status === 'completed') {
            return (
                <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 text-xs">
                    Completed
                </Badge>
            );
        }

        // summary_failed, bda_failed, react_failed = 실패
        if (status.includes('_failed')) {
            return (
                <Badge className="bg-red-500/20 text-red-400 border-red-500/30 text-xs">
                    Failed
                </Badge>
            );
        }

        // 나머지는 진행중
        return (
            <Badge className="bg-orange-500/20 text-orange-400 border-orange-500/30 text-xs">
                Processing
            </Badge>
        );
    };


    return (
                    <Card className="group transition-all duration-300 hover:shadow-[0_8px_16px_rgb(0_0_0/0.4)] border-white/[0.1] hover:border-white/[0.2] bg-black w-full">
            <CardContent className="p-4">
                {/* Glowing Effect */}
                {showGlowEffect && (
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
                                    <span className="hidden xl:inline">{truncateFilename(document.file_name, 35)}</span>
                                    <span className="hidden lg:inline xl:hidden">{truncateFilename(document.file_name, 25)}</span>
                                    <span className="hidden md:inline lg:hidden">{truncateFilename(document.file_name, 20)}</span>
                                    <span className="inline md:hidden">{truncateFilename(document.file_name, 15)}</span>
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

                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={handleDeleteClick}
                            className="h-8 w-8 p-0 opacity-60 group-hover:opacity-100 transition-opacity hover:bg-red-500/20 hover:text-red-400"
                        >
                            <Trash2 className="w-3 h-3" />
                        </Button>
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