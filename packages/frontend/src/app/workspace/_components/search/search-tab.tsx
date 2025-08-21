"use client";

import { useState, useCallback } from "react";
import { Search, Filter, SortAsc, FileText, Image, MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { searchApi } from "@/lib/api";

interface SearchTabProps {
  indexId?: string;
  onOpenPdf?: (document: any) => void;
  onAttachToChat?: (pageInfo: {
    document_id: string;
    page_index: number;
    page_number: number;
    file_name: string;
  }) => void;
}

interface SearchResult {
  page_id: string;
  page_index: number;
  project_id: string;
  document_id: string;
  image_uri: string;
  file_uri: string;
  image_presigned_url: string;
  file_presigned_url?: string;
  highlight?: {
    [key: string]: string[];
  };
  _score?: number;
  score?: number;
}

export function SearchTab({ indexId, onOpenPdf, onAttachToChat }: SearchTabProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [selectedFilter, setSelectedFilter] = useState<'all' | 'documents' | 'images' | 'pages'>('all');

  const searchFilters = [
    { id: 'all' as const, name: '전체', icon: FileText },
    { id: 'documents' as const, name: '문서', icon: FileText },
    { id: 'images' as const, name: '이미지', icon: Image },
    { id: 'pages' as const, name: '페이지', icon: MapPin }
  ];

  const executeSearch = useCallback(async () => {
    if (!searchQuery.trim() || !indexId) {
      setSearchResults([]);
      return;
    }

    setIsSearching(true);
    try {
      const searchData = await searchApi.hybridSearch({
        index_id: indexId,
        query: searchQuery,
        size: 50,
      });

      if (searchData.success && searchData.data.results) {
        const sortedResults = searchData.data.results.sort((a: SearchResult, b: SearchResult) => {
          const scoreA = a._score || a.score || 0;
          const scoreB = b._score || b.score || 0;
          return scoreB - scoreA;
        });
        
        setSearchResults(sortedResults);
      } else {
        setSearchResults([]);
      }
    } catch (error) {
      console.error('Search failed:', error);
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  }, [searchQuery, indexId]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    executeSearch();
  };

  const handleAttachPage = (result: SearchResult) => {
    if (!onAttachToChat) return;
    onAttachToChat({
      document_id: result.document_id,
      page_index: result.page_index,
      page_number: result.page_index + 1,
      file_name: `Document ${result.document_id}`,
    });
  };

  return (
    <div className="h-full flex flex-col bg-black text-white">
      {/* Enhanced Header */}
      <div className="relative p-6 border-b border-white/10 bg-gradient-to-r from-green-500/5 to-emerald-500/5">
        {/* Background glow effect */}
        <div className="absolute inset-0 bg-gradient-to-r from-green-500/10 via-transparent to-emerald-500/10 opacity-30"></div>
        
        <div className="relative flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="relative">
              <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-green-500 to-emerald-600 flex items-center justify-center shadow-lg shadow-green-500/25">
                <Search className="h-6 w-6 text-white" />
              </div>
              <div className="absolute -inset-1 bg-gradient-to-br from-green-500/50 to-emerald-600/50 rounded-2xl blur opacity-60"></div>
            </div>
            <div>
              <h2 className="text-xl font-bold text-white bg-gradient-to-r from-green-300 to-emerald-300 bg-clip-text text-transparent">
                Hybrid Search
              </h2>
              {indexId && (
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-sm text-white/60">Index:</span>
                  <span className="px-2 py-1 bg-green-500/20 border border-green-400/30 rounded-lg text-green-300 text-sm font-medium">
                    {indexId}
                  </span>
                </div>
              )}
            </div>
          </div>
          
          {/* Search results count */}
          {searchResults.length > 0 && (
            <div className="px-3 py-1.5 bg-white/10 border border-white/20 rounded-full backdrop-blur-sm">
              <span className="text-sm text-white/80 font-medium">
                {searchResults.length}개 결과
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Enhanced Search Input */}
      <div className="p-6 border-b border-white/10 bg-gradient-to-r from-green-500/2 to-emerald-500/2">
        <form onSubmit={handleSearchSubmit} className="space-y-6">
          <div className="relative group">
            {/* Gradient background for input */}
            <div className="absolute inset-0 bg-gradient-to-r from-green-500/10 to-emerald-500/10 rounded-2xl opacity-0 group-focus-within:opacity-100 transition-opacity duration-300"></div>
            
            <div className="relative">
              <div className="absolute left-4 top-1/2 transform -translate-y-1/2 z-10">
                <div className="p-2 rounded-lg bg-green-500/20 group-focus-within:bg-green-500/30 transition-colors duration-300">
                  <Search className="h-4 w-4 text-green-300" />
                </div>
              </div>
              <Input
                placeholder="AI 기반 하이브리드 검색으로 문서 내용을 찾아보세요..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-16 pr-4 py-4 h-14 bg-black/40 border border-white/20 rounded-2xl text-white placeholder:text-white/50 focus:border-green-400/60 focus:ring-2 focus:ring-green-400/20 focus:bg-black/60 transition-all duration-300 text-base backdrop-blur-sm"
              />
              
              {/* Search suggestions overlay */}
              {searchQuery && (
                <div className="absolute right-4 top-1/2 transform -translate-y-1/2">
                  <div className="flex items-center gap-2 text-green-400/70 text-sm">
                    <span>Enter로 검색</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Enhanced Search Filters */}
          <div className="flex gap-3 flex-wrap">
            {searchFilters.map((filter) => (
              <button
                key={filter.id}
                onClick={() => setSelectedFilter(filter.id)}
                className={`relative flex items-center gap-2 px-4 py-2.5 rounded-xl transition-all duration-300 group ${
                  selectedFilter === filter.id 
                    ? 'text-white' 
                    : 'text-white/70 hover:text-white'
                }`}
              >
                {/* Active background */}
                {selectedFilter === filter.id && (
                  <div className="absolute inset-0 bg-gradient-to-r from-green-500/30 to-emerald-500/30 rounded-xl border border-green-400/40"></div>
                )}
                
                {/* Hover background */}
                <div className={`absolute inset-0 rounded-xl transition-opacity duration-300 ${
                  selectedFilter === filter.id 
                    ? 'opacity-0' 
                    : 'opacity-0 group-hover:opacity-100 bg-white/10 border border-white/20'
                }`}></div>
                
                <div className="relative flex items-center gap-2">
                  <div className={`p-1 rounded-lg transition-colors duration-300 ${
                    selectedFilter === filter.id 
                      ? 'bg-green-500/20 text-green-300' 
                      : 'bg-white/10 text-white/70 group-hover:bg-white/20 group-hover:text-white'
                  }`}>
                    <filter.icon className="h-3 w-3" />
                  </div>
                  <span className="text-sm font-medium">{filter.name}</span>
                </div>
              </button>
            ))}
          </div>

          <button 
            type="submit" 
            disabled={!searchQuery.trim() || isSearching}
            className="relative w-full h-14 bg-gradient-to-r from-green-500 to-emerald-600 hover:from-green-600 hover:to-emerald-700 disabled:from-green-500/50 disabled:to-emerald-600/50 text-white rounded-2xl font-medium transition-all duration-300 overflow-hidden group disabled:cursor-not-allowed shadow-lg shadow-green-500/25 hover:shadow-green-500/40 disabled:shadow-none"
          >
            {/* Button glow effect */}
            <div className="absolute inset-0 bg-gradient-to-r from-green-400/50 to-emerald-500/50 opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
            
            <div className="relative flex items-center justify-center gap-3">
              {isSearching ? (
                <>
                  <div className="w-5 h-5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                  <span className="text-base">AI 검색 중...</span>
                </>
              ) : (
                <>
                  <div className="p-1 rounded-lg bg-white/20">
                    <Search className="h-4 w-4" />
                  </div>
                  <span className="text-base">하이브리드 검색 시작</span>
                </>
              )}
            </div>
          </button>
        </form>
      </div>

      {/* Search Results */}
      <div className="flex-1 overflow-auto p-4">
        {searchResults.length === 0 && !isSearching && searchQuery.trim() && (
          <div className="text-center text-white/60 py-8">
            <Search className="h-16 w-16 mx-auto mb-4 opacity-50" />
            <p className="text-lg mb-2">검색 결과가 없습니다</p>
            <p className="text-sm">다른 검색어를 시도해보세요.</p>
          </div>
        )}

        {searchResults.length === 0 && !isSearching && !searchQuery.trim() && (
          <div className="text-center text-white/60 py-8">
            <Search className="h-16 w-16 mx-auto mb-4 opacity-50" />
            <p className="text-lg mb-2">문서 검색</p>
            <p className="text-sm">검색어를 입력하여 문서 내용을 찾아보세요.</p>
          </div>
        )}

        <div className="space-y-4">
          {searchResults.map((result) => (
            <Card key={result.page_id} className="bg-white/5 border-white/10 hover:bg-white/10 transition-colors">
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <Badge variant="outline" className="text-green-400 border-green-400/50">
                        페이지 {result.page_index + 1}
                      </Badge>
                      <Badge variant="outline" className="text-white/60 border-white/20">
                        문서 ID: {result.document_id.slice(0, 8)}...
                      </Badge>
                      {(result._score || result.score) && (
                        <Badge variant="outline" className="text-yellow-400 border-yellow-400/50">
                          관련도: {((result._score || result.score || 0) * 100).toFixed(1)}%
                        </Badge>
                      )}
                    </div>

                    {/* Highlight Text */}
                    {result.highlight && Object.keys(result.highlight).length > 0 && (
                      <div className="mb-3">
                        {Object.entries(result.highlight).map(([field, highlights]) => (
                          <div key={field} className="mb-2">
                            <p className="text-xs text-white/60 mb-1">{field}:</p>
                            {highlights.map((highlight, idx) => (
                              <p 
                                key={idx} 
                                className="text-sm text-white/80"
                                dangerouslySetInnerHTML={{ __html: highlight }}
                              />
                            ))}
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleAttachPage(result)}
                        className="border-green-400/50 text-green-400 hover:bg-green-400/20"
                      >
                        <MapPin className="h-3 w-3 mr-1" />
                        채팅에 추가
                      </Button>
                      
                      {result.file_presigned_url && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => onOpenPdf?.({
                            file_uri: result.file_uri,
                            file_name: `Document ${result.document_id}`,
                            document_id: result.document_id
                          })}
                          className="border-white/20 text-white/70 hover:bg-white/10"
                        >
                          <FileText className="h-3 w-3 mr-1" />
                          PDF 보기
                        </Button>
                      )}
                    </div>
                  </div>

                  {/* Page Image Thumbnail */}
                  {result.image_presigned_url && (
                    <div className="w-20 h-20 bg-white/5 rounded border border-white/10 overflow-hidden">
                      <img 
                        src={result.image_presigned_url} 
                        alt={`Page ${result.page_index + 1}`}
                        className="w-full h-full object-cover"
                      />
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
