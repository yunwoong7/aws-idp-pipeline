"use client";

import React, { useCallback, useMemo, useState } from "react";
import ReactDOM from "react-dom";
import { X, BarChart3, FileText, Cpu, Search, Maximize2, Minimize2, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { MarkdownRenderer } from "@/components/ui/markdown-renderer";

interface AnalysisPopupProps {
  isOpen: boolean;
  type: 'bda' | 'pdf' | 'ai' | null;
  selectedSegment: number;
  analysisData: any[];
  onClose: () => void;
}

export function AnalysisPopup({
  isOpen,
  type,
  selectedSegment,
  analysisData,
  onClose
}: AnalysisPopupProps) {
  
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [query, setQuery] = useState("");
  const [expandedSet, setExpandedSet] = useState<Set<number>>(new Set());
  const [detailIndex, setDetailIndex] = useState<number | null>(null);

  // (리스트 전용 레이아웃) 확장 상태는 현재 사용하지 않지만 유지
  const toggleExpand = useCallback((key: number) => {
    setExpandedSet((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const handleCopy = useCallback((text: string) => {
    try {
      if (navigator?.clipboard) {
        navigator.clipboard.writeText(text);
      }
    } catch (e) {
      console.error("copy failed", e);
    }
  }, []);

  // Filter analysis items by tool type (segment is already filtered when passed)
  const collectAnalysisItems = useCallback((toolType: 'bda_indexer' | 'pdf_text_extractor' | 'ai_analysis') => {
    const filteredItems = analysisData.filter((item: any) => {
      const matchesTool = item.tool_name === toolType;
      return matchesTool;
    });
    console.log(`📋 collectAnalysisItems - ${toolType} items:`, filteredItems.length);
    console.log(`📋 Sample item:`, filteredItems[0]);
    return filteredItems;
  }, [analysisData]);

  // Hook-safe derived values (must be before any early return)
  const toolType = type === 'bda' ? 'bda_indexer' : type === 'pdf' ? 'pdf_text_extractor' : type === 'ai' ? 'ai_analysis' : null;
  const items = useMemo(() => {
    if (!toolType) return [] as any[];
    return collectAnalysisItems(toolType as 'bda_indexer' | 'pdf_text_extractor' | 'ai_analysis');
  }, [toolType, collectAnalysisItems]);

  const filteredItems = useMemo(() => {
    if (!Array.isArray(items)) return [] as any[];
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((item: any) => {
      const title = (item.analysis_query || "").toString().toLowerCase();
      const contentText = typeof item.content === 'string' ? item.content : JSON.stringify(item.content, null, 2);
      return title.includes(q) || contentText.toLowerCase().includes(q);
    });
  }, [items, query]);

  const safeDetailIndex = useMemo(() => {
    if (filteredItems.length === 0) return null as number | null;
    if (detailIndex === null || detailIndex >= filteredItems.length) return 0;
    return detailIndex;
  }, [detailIndex, filteredItems.length]);

  if (!isOpen || !type) return null;

  // Portal을 사용해서 body에 직접 렌더링
  const portalRoot = typeof document !== 'undefined' ? document.body : null;
  
  if (!portalRoot) return null;

  const getTypeConfig = () => {
    switch (type) {
      case 'bda':
        return {
          title: 'BDA 분석 결과',
          icon: BarChart3,
        };
      case 'pdf':
        return {
          title: 'PDF 분석 결과',
          icon: FileText,
        };
      case 'ai':
        return {
          title: 'AI 분석 결과',
          icon: Cpu,
        };
      default:
        return {
          title: '분석 결과',
          icon: BarChart3,
        };
    }
  };

  const config = getTypeConfig();
  const IconComponent = config.icon;

  return ReactDOM.createPortal(
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center"
        style={{ zIndex: 2147483647 }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={(e) => {
          if (e.target === e.currentTarget) {
            onClose();
          }
        }}
      >
        <motion.div
          className={`from-slate-900/95 via-gray-900/95 to-slate-900/95 backdrop-blur-xl border border-white/20 rounded-xl shadow-[0_8px_32px_rgb(0_0_0/0.4)] overflow-hidden ${isFullscreen ? 'max-w-[95vw] w-[95vw] h-[90vh] max-h-[90vh]' : 'max-w-4xl w-[90vw] max-h-[80vh]'}`}
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.9, opacity: 0 }}
          transition={{ type: "spring", damping: 20, stiffness: 300 }}
        >
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-white/10">
            <div className="flex items-center gap-3">
              <div className={"w-3 h-3 rounded-full bg-slate-400"}></div>
              <h3 className="text-lg font-semibold text-white">
                {config.title}
                <span className="text-sm font-normal text-white/60 ml-2">
                  (Segment {selectedSegment + 1})
                </span>
              </h3>
              <Badge variant="outline" className={"text-slate-300 border-slate-600/50 bg-white/5"}>
                {filteredItems.length}개
              </Badge>
            </div>
            <div className="flex items-center gap-2">
              {/* 뷰 전환 버튼 제거: 리스트 전용 UI */}
              <div className="relative">
                <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-white/40" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="검색(제목/내용)"
                  className="pl-8 pr-2 py-1.5 bg-white/5 border border-white/10 rounded-md text-sm text-white placeholder:text-white/40 focus:outline-none focus:ring-2 focus:ring-white/20"
                />
              </div>
              {/* 리스트 전용: 컨트롤 단순화 */}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsFullscreen((v) => !v)}
                className="text-white/70 hover:text-white hover:bg-white/10"
              >
                {isFullscreen ? (
                  <span className="inline-flex items-center"><Minimize2 className="h-4 w-4 mr-1" /> 축소</span>
                ) : (
                  <span className="inline-flex items-center"><Maximize2 className="h-4 w-4 mr-1" /> 전체화면</span>
                )}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={onClose}
                className="text-white/70 hover:text-white hover:bg-white/10"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Content */}
          <div className={`p-0 ${isFullscreen ? 'h-[75vh]' : 'h-[60vh]'} overflow-hidden`}>
            {!Array.isArray(analysisData) || analysisData.length === 0 ? (
              <p className="p-6 text-center text-white/60">분석 데이터를 불러오는 중이거나 데이터가 없습니다.</p>
            ) : (
              <div className="flex h-full min-h-0 divide-x divide-white/10">
                {/* Left: List Only */}
                <div className="w-[38%] min-w-[260px] max-w-[520px] h-full min-h-0 overflow-y-auto p-4 space-y-2">
                  {filteredItems.length === 0 ? (
                    <div className={"p-4 rounded-lg border bg-white/5 border-white/10"}>
                      <p className="text-center text-white/60">결과가 없습니다.</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {filteredItems.map((item: any, index: number) => {
                        const contentText = typeof item.content === 'string' ? item.content : JSON.stringify(item.content, null, 2);
                        const title = item.analysis_query || `${config.title} ${index + 1}`;
                        const excerpt = contentText ? (contentText.length > 140 ? contentText.slice(0, 140) + '…' : contentText) : '내용이 없습니다.';
                        const isActive = safeDetailIndex === index;
                        return (
                          <button
                            key={index}
                            onClick={() => setDetailIndex(index)}
                            className={cn(
                              "group relative w-full text-left p-3 rounded-xl border transition-all duration-200 backdrop-blur-sm",
                              isActive ? "bg-white/15 border-white/30 ring-1 ring-white/20 shadow-[0_8px_24px_rgb(0_0_0/0.25)]" : "bg-white/5 hover:bg-white/10 border-white/10 hover:-translate-y-0.5 hover:ring-1 hover:ring-white/20"
                            )}
                          >
                            <div className="flex items-center gap-2">
                              <span className="inline-flex items-center justify-center rounded-md bg-slate-800/80 p-1">
                                <IconComponent className={"h-4 w-4 text-slate-300"} />
                              </span>
                              <span className="text-sm font-medium text-white line-clamp-1">{title}</span>
                            </div>
                            <p className="mt-1 text-xs text-white/70 line-clamp-2">{excerpt}</p>
                            <p className="mt-2 text-[11px] text-white/50">{item.created_at ? new Date(item.created_at).toLocaleDateString('ko-KR') : ''}</p>
                            <span className="pointer-events-none absolute inset-y-0 right-2 my-auto h-6 w-px bg-white/10 opacity-0 group-hover:opacity-100 transition-opacity" />
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Right: Detail */}
                <div className="flex-1 min-w-0">
                  {safeDetailIndex === null ? (
                    <div className="h-full flex items-center justify-center text-white/50 text-sm">좌측에서 항목을 선택하세요.</div>
                  ) : (
                    <div className="h-full flex flex-col">
                      <div className="flex items-center justify-between p-4 border-b border-white/10">
                        <div className="flex items-center gap-2 min-w-0">
                          <IconComponent className={"h-5 w-5 text-slate-300"} />
                          <span className="text-base font-medium text-white truncate">
                            {filteredItems[safeDetailIndex].analysis_query || `${config.title} ${safeDetailIndex + 1}`}
                          </span>
                          {filteredItems[safeDetailIndex].created_at && (
                            <span className="ml-2 text-xs text-white/50 flex-shrink-0">
                              {new Date(filteredItems[safeDetailIndex].created_at).toLocaleDateString('ko-KR')}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleCopy(typeof filteredItems[safeDetailIndex].content === 'string' ? filteredItems[safeDetailIndex].content : JSON.stringify(filteredItems[safeDetailIndex].content, null, 2))}
                            className="text-white/70 hover:text-white hover:bg-white/10"
                            title="내용 복사"
                          >
                            <Copy className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={onClose}
                            className="text-white/70 hover:text-white hover:bg-white/10"
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                      <div className={`flex-1 overflow-y-auto p-6`}>
                        <MarkdownRenderer
                          content={
                            typeof filteredItems[safeDetailIndex].content === 'string'
                              ? filteredItems[safeDetailIndex].content
                              : JSON.stringify(filteredItems[safeDetailIndex].content, null, 2)
                          }
                        />
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>,
    portalRoot
  );
}
