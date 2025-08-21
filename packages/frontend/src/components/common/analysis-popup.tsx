"use client";

import React from "react";
import ReactDOM from "react-dom";
import { X, BarChart3, FileText, Cpu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { motion, AnimatePresence } from "framer-motion";

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
  
  // Filter analysis items by tool type and current segment
  const collectAnalysisItems = (toolType: 'bda_indexer' | 'pdf_text_extractor' | 'ai_analysis') => {
    const filteredItems = analysisData.filter((item: any) => {
      const matchesTool = item.tool_name === toolType;
      const itemSegmentIndex = (typeof item.segment_index === 'number' ? item.segment_index : undefined) ??
                             (typeof item.page_index === 'number' ? item.page_index : undefined);
      const matchesSegment = itemSegmentIndex === selectedSegment;
      return matchesTool && matchesSegment;
    });
    console.log(`📋 collectAnalysisItems - ${toolType} items for segment ${selectedSegment}:`, filteredItems.length);
    return filteredItems;
  };

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
          color: 'blue',
          bgColor: 'bg-blue-500/10',
          borderColor: 'border-blue-400/30',
          textColor: 'text-blue-300'
        };
      case 'pdf':
        return {
          title: 'PDF 분석 결과',
          icon: FileText,
          color: 'green',
          bgColor: 'bg-green-500/10',
          borderColor: 'border-green-400/30',
          textColor: 'text-green-300'
        };
      case 'ai':
        return {
          title: 'AI 분석 결과',
          icon: Cpu,
          color: 'purple',
          bgColor: 'bg-purple-500/10',
          borderColor: 'border-purple-400/30',
          textColor: 'text-purple-300'
        };
      default:
        return {
          title: '분석 결과',
          icon: BarChart3,
          color: 'gray',
          bgColor: 'bg-gray-500/10',
          borderColor: 'border-gray-400/30',
          textColor: 'text-gray-300'
        };
    }
  };

  const config = getTypeConfig();
  const IconComponent = config.icon;
  const toolType = type === 'bda' ? 'bda_indexer' : 
                   type === 'pdf' ? 'pdf_text_extractor' : 
                   'ai_analysis';
  const items = collectAnalysisItems(toolType);

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
          className="bg-gradient-to-br from-slate-900/95 via-gray-900/95 to-slate-900/95 backdrop-blur-xl border border-white/20 rounded-xl max-w-4xl w-[90vw] max-h-[80vh] overflow-hidden shadow-[0_8px_32px_rgb(0_0_0/0.4)]"
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.9, opacity: 0 }}
          transition={{ type: "spring", damping: 20, stiffness: 300 }}
        >
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-white/10">
            <div className="flex items-center gap-3">
              <div className={`w-3 h-3 rounded-full bg-${config.color}-400`}></div>
              <h3 className="text-lg font-semibold text-white">
                {config.title}
                <span className="text-sm font-normal text-white/60 ml-2">
                  (Segment {selectedSegment + 1})
                </span>
              </h3>
              <Badge variant="outline" className={`${config.textColor} ${config.borderColor} ${config.bgColor}`}>
                {items.length}개
              </Badge>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              className="text-white/70 hover:text-white hover:bg-white/10"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>

          {/* Content */}
          <div className="p-6 overflow-y-auto max-h-[60vh]">
            {!Array.isArray(analysisData) || analysisData.length === 0 ? (
              <p className="text-center text-white/60">분석 데이터를 불러오는 중이거나 데이터가 없습니다.</p>
            ) : (
              <div className="space-y-4">
                {items.length > 0 ? (
                  items.map((item: any, index: number) => (
                    <div
                      key={index}
                      className={`p-4 rounded-lg border ${config.bgColor} ${config.borderColor}`}
                    >
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <IconComponent className={`h-4 w-4 ${config.textColor}`} />
                          <span className="text-sm font-medium text-white">
                            {item.analysis_query || `${config.title} ${index + 1}`}
                          </span>
                        </div>
                        {item.created_at && (
                          <span className="text-xs text-white/50">
                            {new Date(item.created_at).toLocaleDateString('ko-KR')}
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-white/90 whitespace-pre-wrap max-h-64 overflow-y-auto">
                        {item.content || '내용이 없습니다.'}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className={`p-4 rounded-lg border ${config.bgColor} ${config.borderColor}`}>
                    <p className="text-center text-white/60">
                      Segment {selectedSegment + 1}에 {config.title.split(' ')[0]} 결과가 없습니다.
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>,
    portalRoot
  );
}
