"use client";

import { useState, useCallback } from "react";
import {
  Search,
  RotateCcw,
  Loader2
} from "lucide-react";
import { searchApi } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { SearchInterface } from "./components/search-interface";
import type { FileAttachment } from "@/types/chat.types";

// Types for persistent state across tabs
interface PersistentSearchState {
  messages: any[];
  input: string;
  currentPhase: "idle" | "planning" | "executing" | "responding";
  toolCollapsed: Record<string, boolean>;
  isChatStarted: boolean;
  attachments?: FileAttachment[];
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
  onReferenceClick?: (reference: any) => void;
  persistentState?: PersistentSearchState;
  onStateUpdate?: (updates: Partial<PersistentSearchState>) => void;
}


export function SearchTab({ indexId, onOpenPdf, onAttachToChat, onReferenceClick, persistentState, onStateUpdate }: SearchTabProps) {
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [isResetting, setIsResetting] = useState(false);

  const isChatStarted = persistentState?.isChatStarted ?? false;

  const handleChatReset = useCallback(async () => {
    console.log('🔄 Chat reset initiated');
    setIsResetting(true);

    try {
      // Reinitialize search API
      await searchApi.reinitialize();

      // Update persistent state to clear messages, input, and reset chat started state
      onStateUpdate?.({
        messages: [],
        input: "",
        isChatStarted: false,
        currentPhase: 'idle',
        toolCollapsed: {},
        attachments: []
      });

      console.log('✅ Chat reset completed');
    } catch (error) {
      console.error('❌ Chat reset failed:', error);
      // Still reset UI even if API call fails
      onStateUpdate?.({
        messages: [],
        input: "",
        isChatStarted: false,
        currentPhase: 'idle',
        toolCollapsed: {},
        attachments: []
      });
    } finally {
      setIsResetting(false);
      setShowResetConfirm(false);
    }
  }, [onStateUpdate]);

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
              </div>
            </div>

            {/* Reset Button */}
            {isChatStarted && (
              <button
                type="button"
                onClick={() => setShowResetConfirm(true)}
                disabled={isResetting}
                className="flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 transition-all duration-200 backdrop-blur-sm group disabled:opacity-50 disabled:cursor-not-allowed"
                title="Reset Chat"
              >
                {isResetting ? (
                  <Loader2 className="w-4 h-4 text-orange-400 animate-spin" />
                ) : (
                  <RotateCcw className="w-4 h-4 text-orange-400 group-hover:text-orange-300 transition-colors" />
                )}
                <span className="text-sm text-white/60 group-hover:text-white/80">Reset</span>
              </button>
            )}
          </div>
        </div>

        {/* SearchInterface Component */}
        <SearchInterface
          indexId={indexId}
          onOpenPdf={onOpenPdf}
          onAttachToChat={onAttachToChat}
          onReferenceClick={onReferenceClick}
          persistentState={persistentState}
          onStateUpdate={onStateUpdate}
          onChatReset={handleChatReset}
        />
      </div>

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
