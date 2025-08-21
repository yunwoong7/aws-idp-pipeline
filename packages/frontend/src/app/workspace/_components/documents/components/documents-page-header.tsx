import React, { useState } from "react";
import { Plus, RefreshCw, Search, X, Eye, LoaderIcon, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { GlowingEffect } from "@/components/ui/glowing-effect";

interface DocumentsPageHeaderProps {
    onAddDocument: () => void;
    onRefresh?: () => void;
    isLoading?: boolean;
    isUploading?: boolean;
    searchQuery?: string;
    onSearchChange?: (query: string) => void;
    onSearchExecute?: () => void;
    isSearching?: boolean;
    searchResultCount?: number;
    totalDocuments?: number;
}

export function DocumentsPageHeader({ 
    onAddDocument, 
    onRefresh, 
    isLoading = false,
    isUploading = false,
    searchQuery = "",
    onSearchChange,
    onSearchExecute,
    isSearching = false,
    searchResultCount = 0,
    totalDocuments = 0
}: DocumentsPageHeaderProps) {
    const [isSearchExpanded, setIsSearchExpanded] = useState(false);

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter' && searchQuery.trim() && onSearchExecute) {
            onSearchExecute();
        }
    };

    const clearSearch = () => {
        if (onSearchChange) {
            onSearchChange("");
        }
    };

    const toggleSearch = () => {
        setIsSearchExpanded(!isSearchExpanded);
        if (isSearchExpanded && searchQuery) {
            clearSearch();
        }
    };

    return (
        <div className="sticky top-0 z-10">
            <div className="p-6">
                {/* Title Section */}
                {/* <div className="mb-4">
                    <h1 className="text-3xl font-bold text-white mb-2">Document Management</h1>
                    <p className="text-slate-400">
                        {currentProject?.project_name} Project Documents
                    </p>
                </div> */}

                {/* Action Buttons Section */}
                <div className="flex gap-2">
                    <Button 
                        onClick={toggleSearch}
                        variant="outline"
                        size="sm"
                                                                className="bg-transparent border-white/10 text-white/70 hover:bg-cyan-500/20 hover:border-cyan-400 hover:text-cyan-300 transition-all duration-200 h-8 text-xs px-3"
                    >
                        <Search className="h-3 w-3 mr-1" />
                        {isSearchExpanded ? (
                            <>
                                <ChevronUp className="h-3 w-3 ml-1" />
                                Hide Search
                            </>
                        ) : (
                            <>
                                <ChevronDown className="h-3 w-3 ml-1" />
                                Show Search
                            </>
                        )}
                    </Button>
                    <div className="relative">
                        <GlowingEffect
                            variant="default"
                            proximity={60}
                            spread={25}
                            borderWidth={1}
                            movementDuration={1.2}
                            className="opacity-50"
                            disabled={isUploading}
                        />
                        <Button 
                            onClick={onAddDocument}
                            variant="outline"
                            size="sm"
                            disabled={isUploading}
                            className="bg-transparent border-white/10 text-emerald-400 hover:bg-emerald-500/20 hover:border-emerald-400 hover:text-emerald-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed h-8 text-xs px-3"
                        >
                            <Plus className="h-3 w-3 mr-1" />
                            Add Document
                        </Button>
                    </div>
                    {onRefresh && (
                        <Button 
                            onClick={onRefresh}
                            variant="outline"
                            size="sm"
                            disabled={isLoading}
                            className="bg-transparent border-white/10 text-cyan-400 hover:bg-cyan-500/20 hover:border-cyan-400 hover:text-cyan-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed h-8 text-xs px-3"
                        >
                            <RefreshCw className={`h-3 w-3 mr-1 ${isLoading ? 'animate-spin' : ''}`} />
                            {isLoading ? 'Refreshing...' : 'Refresh'}
                        </Button>
                    )}
                </div>

                {/* Search area */}
                {isSearchExpanded && (
                    <div className="space-y-3 border-t border-white/[0.1] pt-4">
                        <div className="relative w-full">
                            <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 h-5 w-5 text-white/50" />
                            <input
                                type="text"
                                placeholder="Search documents by name, content, or description..."
                                value={searchQuery}
                                onChange={(e) => onSearchChange?.(e.target.value)}
                                onKeyDown={handleKeyDown}
                                className="w-full pl-12 pr-20 py-3 bg-black border border-white/[0.1] rounded-lg focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500/50 text-white placeholder:text-white/50 text-sm transition-all duration-200"
                            />
                            <div className="absolute right-3 top-1/2 transform -translate-y-1/2 flex items-center gap-2">
                                {searchQuery && (
                                    <button
                                        onClick={clearSearch}
                                        className="p-1 rounded-lg hover:bg-white/[0.05] transition-colors"
                                    >
                                        <X className="h-4 w-4 text-white/50 hover:text-white" />
                                    </button>
                                )}
                                {isSearching ? (
                                    <LoaderIcon className="h-5 w-5 animate-spin text-cyan-400" />
                                ) : (
                                    <button
                                        onClick={onSearchExecute}
                                        disabled={!searchQuery.trim()}
                                        className="p-1 rounded-lg hover:bg-white/[0.05] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        <Search className="h-4 w-4 text-white/50 hover:text-cyan-400 transition-colors" />
                                    </button>
                                )}
                            </div>
                        </div>

                        {/* Search result information */}
                        {searchQuery && !isSearching && (
                            <div className="flex items-center gap-3 text-sm text-white/70">
                                <Eye className="h-4 w-4" />
                                <span>
                                    Search Result: <span className="text-cyan-300 font-medium">{searchResultCount} documents</span>
                                    {totalDocuments > 0 && (
                                        <span className="ml-2">
                                            of <span className="text-white">{totalDocuments.toLocaleString()}</span> total
                                        </span>
                                    )}
                                </span>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
} 