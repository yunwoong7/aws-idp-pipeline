"use client";

import { 
  Search
} from "lucide-react";
import { systemApi } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { SearchInterface } from "./components/search-interface";

// Types for persistent state across tabs
interface PersistentSearchState {
  messages: any[];
  input: string;
  currentPhase: "idle" | "planning" | "executing" | "responding";
  toolCollapsed: Record<string, boolean>;
  isChatStarted: boolean;
}

interface SearchTabProps {
  indexId?: string;
  onOpenPdf?: (document: any) => void;
  onAttachToChat?: (pageInfo: {
    document_id: string;
    page_index: number;
    page_number: number;
    file_name: string;
  }) => void;
  persistentState?: PersistentSearchState;
  onStateUpdate?: (updates: Partial<PersistentSearchState>) => void;
}


export function SearchTab({ indexId, onOpenPdf, onAttachToChat, persistentState, onStateUpdate }: SearchTabProps) {


  return (
    <>
      
      <div className="h-full flex flex-col bg-black text-white relative overflow-hidden">
        {/* Header Section */}
        <div className="flex-shrink-0 p-4 border-b border-white/10 bg-gradient-to-r from-slate-900/50 to-slate-800/50 backdrop-blur-sm relative z-20">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="relative">
                <div className="relative w-12 h-12 bg-gradient-to-br from-emerald-500/20 to-cyan-600/20 border border-emerald-400/30 rounded-2xl flex items-center justify-center">
                  <Search className="h-6 w-6 text-white" />
                </div>
                <div className="absolute -inset-1 bg-gradient-to-br from-emerald-500/50 to-cyan-600/50 rounded-2xl blur opacity-60"></div>
              </div>
              <div>
                <h2 className="text-xl font-bold text-white bg-gradient-to-r from-emerald-300 to-cyan-300 bg-clip-text text-transparent">
                  Search
                </h2>
                <div className="flex items-center gap-2 mt-1">
                  {indexId && (
                    <>
                      <span className="text-sm text-white/60">Index:</span>
                      <span className="px-2 py-1 bg-emerald-500/20 border border-emerald-400/30 rounded-lg text-emerald-300 text-sm font-medium">
                        {indexId}
                      </span>
                    </>
                  )}
                </div>
              </div>
            </div>
            
          </div>
        </div>

        {/* SearchInterface Component */}
        <SearchInterface 
          indexId={indexId}
          onOpenPdf={onOpenPdf}
          onAttachToChat={onAttachToChat}
          persistentState={persistentState}
          onStateUpdate={onStateUpdate}
        />
      </div>
    </>
  );
}
