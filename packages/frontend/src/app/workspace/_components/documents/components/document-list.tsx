import React from "react";
import { Search, BookOpen, FileText } from "lucide-react";
import { DocumentItem } from "./document-item";
import { Document } from "@/types/document.types";

interface DocumentListProps {
    documents: Document[];
    loading: boolean;
    error: string | null;
    onViewDocument: (document: Document) => void;
    onDeleteDocument: (documentId: string, indexId: string) => void;
    indexId: string;
    // Add props for search
    searchQuery?: string;
    isSearching?: boolean;
    totalDocuments?: number;
    searchResults?: any[];
    // Analyze action
    onAnalyzeDocument?: (document: Document) => void;
}

export function DocumentList({
    documents,
    loading,
    error,
    onViewDocument,
    onDeleteDocument,
    indexId,
    searchQuery = "",
    isSearching = false,
    totalDocuments = 0,
    searchResults = [],
    onAnalyzeDocument,
}: DocumentListProps) {

    if (error) {
        return (
            <div className="text-center py-8">
                <p className="text-red-400 text-sm">{error}</p>
            </div>
        );
    }

    // Searching state
    if (isSearching) {
        return (
            <div className="flex items-center justify-center py-16">
                <div className="flex flex-col items-center gap-4 text-slate-400">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-400"></div>
                    <div className="text-center">
                        <div className="text-lg font-medium text-amber-300">Searching...</div>
                        <div className="text-sm text-slate-400 mt-1">&quot;{searchQuery}&quot;</div>
                    </div>
                </div>
            </div>
        );
    }

    // When there are no search results
    if (documents.length === 0) {
        return (
            <div className="flex items-center justify-center py-16">
                <div className="text-center text-slate-400">
                    {searchQuery ? (
                        <>
                            <Search className="h-16 w-16 mx-auto mb-4 text-slate-600" />
                            <p className="text-xl font-medium mb-2 text-slate-300">
                                No search results
                            </p>
                            <p className="text-sm">
                                Try a different search query or check your spelling
                            </p>
                            <p className="text-xs text-slate-500 mt-2">
                                Search Query: &quot;{searchQuery}&quot;
                            </p>
                        </>
                    ) : (
                        <>
                            <BookOpen className="h-16 w-16 mx-auto mb-4 text-slate-600" />
                            <p className="text-xl font-medium mb-2 text-slate-300">
                                No documents found
                            </p>
                            <p className="text-sm">
                                Upload documents to get started
                            </p>
                        </>
                    )}
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* 검색 결과 요약 */}
            {searchQuery && documents.length > 0 && (
                                    <div className="flex items-center gap-3 px-4 py-3 bg-black border border-white/[0.1] rounded-lg">
                    <FileText className="h-5 w-5 text-cyan-400" />
                    <div className="text-sm text-white/70">
                        Found <span className="font-medium text-white">{documents.length}</span> documents
                        {totalDocuments > 0 && (
                            <span className="text-white/50 ml-1">
                                out of {totalDocuments.toLocaleString()} total
                            </span>
                        )}
                        {searchQuery && (
                            <span className="text-slate-400 ml-1">
                                for &quot;{searchQuery}&quot;
                            </span>
                        )}
                    </div>
                </div>
            )}

            {/* 문서 리스트 - 한 줄에 하나씩 */}
            <div className="space-y-3">
                {documents.map((document) => (
                    <DocumentItem
                        key={document.document_id}
                        document={document}
                        onView={onViewDocument}
                        onDelete={onDeleteDocument}
                        indexId={indexId}
                        searchResults={searchResults}
                        isSearchMode={!!searchQuery}
                        onAnalyze={onAnalyzeDocument}
                    />
                ))}
            </div>
        </div>
    );
} 