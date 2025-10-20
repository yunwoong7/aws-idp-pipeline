"use client";

import { 
  CheckCircle
} from "lucide-react";
import { VerificationInterface } from "./components/verification-interface";

// Types for persistent state across tabs
interface PersistentVerificationState {
  sourceDocuments: any[];
  targetDocument: any | null;
  messages: any[];
  verificationResults: any[];
  isVerifying: boolean;
  isChatStarted: boolean;
}

interface VerificationTabProps {
  indexId?: string;
  onOpenPdf?: (document: any) => void;
  onAttachToChat?: (pageInfo: {
    document_id: string;
    page_index: number;
    page_number: number;
    file_name: string;
  }) => void;
  persistentState?: PersistentVerificationState;
  onStateUpdate?: (updates: Partial<PersistentVerificationState>) => void;
}

export function VerificationTab({ 
  indexId, 
  onOpenPdf, 
  onAttachToChat, 
  persistentState, 
  onStateUpdate 
}: VerificationTabProps) {
  
  return (
    <div className="h-full flex flex-col bg-black text-white relative overflow-hidden">
      {/* Header Section */}
      <div className="flex-shrink-0 p-4 border-b border-white/10 bg-gradient-to-r from-slate-900/50 to-slate-800/50 backdrop-blur-sm relative z-20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="relative">
              <div className="relative w-12 h-12 bg-gradient-to-br from-indigo-500/20 to-purple-600/20 border border-indigo-400/30 rounded-2xl flex items-center justify-center">
                <CheckCircle className="h-6 w-6 text-white" />
              </div>
              <div className="absolute -inset-1 bg-gradient-to-br from-indigo-500/50 to-purple-600/50 rounded-2xl blur opacity-60"></div>
            </div>
            <div>
              <h2 className="text-xl font-bold text-white bg-gradient-to-r from-indigo-300 to-purple-300 bg-clip-text text-transparent">
                Content Verification
              </h2>
            </div>
          </div>
        </div>
      </div>

      {/* VerificationInterface Component */}
      <VerificationInterface 
        indexId={indexId}
        onOpenPdf={onOpenPdf}
        onAttachToChat={onAttachToChat}
        persistentState={persistentState}
        onStateUpdate={onStateUpdate}
      />
    </div>
  );
}