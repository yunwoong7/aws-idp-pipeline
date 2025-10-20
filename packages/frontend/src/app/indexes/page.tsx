"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/common/app-sidebar";
import { CreateIndexDialog } from "@/components/common/create-index-dialog";
import { UploadNotificationContainer } from "@/components/ui/upload-notification";
import { useUploadNotifications } from "@/hooks/use-upload-notifications";
import { PlusCircle } from "lucide-react";
import { indicesApi } from "@/lib/api";
import { Trash2 } from "lucide-react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ChatBackground } from "@/components/ui/chat-background";
import { PinContainer } from "@/components/ui/3d-pin";
import { useAuth } from "@/contexts/auth-context";

type IndexItem = {
  index_id: string;
  description?: string;
  owner_name?: string;
  owner_id?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
  total_documents?: number;
};

export default function IndexesPage() {
  const router = useRouter();
  const { canCreateIndex, canDeleteIndex, canAccessIndex, hasTabAccess, accessibleIndexes } = useAuth();
  const [indexes, setIndexes] = useState<IndexItem[]>([]);
  const [openCreate, setOpenCreate] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmTargetId, setConfirmTargetId] = useState<string | null>(null);

  // Upload notification (re-use existing tone)
  const { notifications, removeNotification } = useUploadNotifications({ maxNotifications: 3, autoRemove: true, autoRemoveDelay: 6000 });

  // Load indices via API
  useEffect(() => {
    let mounted = true;
    setLoading(true);
    (async () => {
      try {
        const items = await indicesApi.list();
        if (mounted) setIndexes(items || []);
      } catch (e) {
        console.error("Failed to load indices", e);
        if (mounted) setError("Failed to load indices");
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, []);

  const handleCreateSuccess = (createdIndex: IndexItem) => {
    setIndexes(prev => [createdIndex, ...prev]);
    setOpenCreate(false);
  };

  const handleDeleteClick = (indexId: string) => {
    setConfirmTargetId(indexId);
    setConfirmOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!confirmTargetId) return;
    try {
      const result = await indicesApi.deepDelete(confirmTargetId);
      console.log('Deep delete result:', result);
      setIndexes(prev => prev.filter(i => i.index_id !== confirmTargetId));
    } catch (e: any) {
      console.error(e);
      // 간단 알림
      alert(e?.message || 'Failed to delete index');
    } finally {
      setConfirmTargetId(null);
    }
  };

  // Get the first available tab to redirect to
  const getFirstAvailableTab = (): string => {
    if (hasTabAccess('documents')) return 'documents';
    if (hasTabAccess('analysis')) return 'analysis';
    if (hasTabAccess('search')) return 'search';
    if (hasTabAccess('verification')) return 'verification';
    return 'documents'; // fallback
  };

  // Check if user has access to at least one index
  const filteredIndexes = indexes.filter(idx => canAccessIndex(idx.index_id));
  const hasAccessibleIndexes = filteredIndexes.length > 0;
  const hasAnyTabAccess = hasTabAccess('documents') || hasTabAccess('analysis') || hasTabAccess('search') || hasTabAccess('verification');

  return (
    <div className="min-h-screen bg-black text-white">
      <SidebarProvider className="bg-black" defaultOpen>
        <AppSidebar />
        <SidebarInset className="bg-black relative">
          <ChatBackground />
          {/* Top header with sidebar toggle */}
          <div className="absolute top-0 left-0 right-0 z-40 flex items-center px-3 py-3 bg-black/50 backdrop-blur-sm border-b border-white/10">
            <SidebarTrigger className="hidden md:flex bg-black/40 border border-white/10 hover:bg-white/10" />
          </div>

          <div className="p-6 relative z-0 pt-20">
            <div className="mb-6">
              <h2 className="text-2xl font-bold text-white">Workspace Indexes</h2>
              <p className="text-white/60">Create an index and start uploading your media for AI-powered analysis</p>
            </div>

            {/* Insufficient permissions message */}
            {!loading && !hasAccessibleIndexes && !canCreateIndex && (
              <div className="mb-8 rounded-xl border border-amber-500/30 bg-amber-500/10 p-6 backdrop-blur-sm">
                <div className="flex items-start gap-3">
                  <div className="rounded-full bg-amber-500/20 p-2">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-amber-400" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div className="flex-1">
                    <h3 className="text-lg font-semibold text-amber-200 mb-1">Insufficient Permissions</h3>
                    <p className="text-sm text-amber-300/80">
                      You don't have permission to access any indexes or create new ones. Please contact your administrator to request access.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Card grid (3D pin style) */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-12 md:gap-16 mb-8">
              {/* Create card (3D pin) */}
              {canCreateIndex && (
                <PinContainer title="Create an index" href="#" onClick={(e) => { e.preventDefault(); setOpenCreate(true); }} containerClassName="h-72 relative z-10">
                  <div className="flex flex-col p-4 tracking-tight text-slate-100/80 w-[18rem] h-[18rem] bg-gradient-to-b from-slate-800/50 to-slate-800/0 backdrop-blur-sm border border-slate-700/50 rounded-2xl items-center justify-center">
                    <div className="w-10 h-10 rounded-full border border-white/20 flex items-center justify-center mb-4">
                      <PlusCircle className="w-5 h-5 text-white/80" />
                    </div>
                    <div className="text-xl font-semibold text-white mb-2">Create an index</div>
                    <div className="text-sm text-white/60 text-center max-w-[240px]">By creating an index, you can upload your own videos and start building.</div>
                  </div>
                </PinContainer>
              )}

              {loading ? (
                // Loading skeleton cards
                Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="h-72 w-full">
                    <div className="flex flex-col p-4 tracking-tight text-slate-100/80 w-[18rem] h-[18rem] bg-gradient-to-b from-slate-800/50 to-slate-800/0 backdrop-blur-sm border border-slate-700/50 rounded-2xl animate-pulse">
                      <div className="flex items-center gap-2">
                        <div className="size-3 rounded-full bg-slate-600" />
                        <div className="w-12 h-3 bg-slate-600 rounded" />
                      </div>
                      <div className="flex-1 mt-4 space-y-3">
                        <div className="w-24 h-6 bg-slate-600 rounded" />
                        <div className="w-20 h-4 bg-slate-600 rounded" />
                        <div className="space-y-2">
                          <div className="w-full h-3 bg-slate-600 rounded" />
                          <div className="w-3/4 h-3 bg-slate-600 rounded" />
                        </div>
                        <div className="w-16 h-3 bg-slate-600 rounded" />
                      </div>
                      <div className="flex justify-between items-end">
                        <div className="w-16 h-3 bg-slate-600 rounded" />
                        <div className="w-12 h-4 bg-slate-600 rounded" />
                      </div>
                    </div>
                  </div>
                ))
              ) : error ? (
                // Error state
                <div className="col-span-full flex items-center justify-center py-12">
                  <div className="text-center text-red-400">
                    <p className="text-lg font-semibold mb-2">Failed to load indexes</p>
                    <p className="text-sm text-red-400/80">{error}</p>
                  </div>
                </div>
              ) : (
                // Actual index cards (filtered by canAccessIndex)
                filteredIndexes.map((idx) => (
                  <PinContainer
                    key={idx.index_id}
                    title={idx.index_id}
                    href={`/workspace?index_id=${idx.index_id}&tab=${getFirstAvailableTab()}`}
                    containerClassName="h-72 relative z-10"
                  >
                    <div className="flex flex-col p-4 tracking-tight text-slate-100/80 w-[18rem] h-[18rem] bg-gradient-to-b from-slate-800/50 to-slate-800/0 backdrop-blur-sm border border-slate-700/50 rounded-2xl">
                      <div className="flex items-center gap-2">
                        <div className="size-3 rounded-full bg-emerald-500" />
                        <div className="text-xs text-slate-400">{idx.status || 'active'}</div>
                        {canDeleteIndex && (
                          <button
                            onClick={(e) => { e.preventDefault(); e.stopPropagation(); handleDeleteClick(idx.index_id); }}
                            title="Delete index"
                            className="ml-auto inline-flex items-center justify-center w-6 h-6 rounded border border-white/10 hover:bg-white/10 text-white/70 hover:text-red-300"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                      <div className="flex-1 mt-4 space-y-3">
                        <div className="text-xl font-bold text-slate-100">{idx.index_id}</div>
                        <div className="flex items-center gap-2 text-sm text-slate-300/80">
                          <span className="inline-flex items-center gap-1 rounded-full bg-white/5 px-2 py-0.5 border border-white/10">
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 opacity-80"><path d="M3 4.5A1.5 1.5 0 0 1 4.5 3h15A1.5 1.5 0 0 1 21 4.5v15A1.5 1.5 0 0 1 19.5 21h-15A1.5 1.5 0 0 1 3 19.5v-15ZM5 6v12h14V6H5Z"/></svg>
                            <span className="text-white/80">{typeof idx.total_documents === 'number' ? idx.total_documents : 0} documents</span>
                          </span>
                        </div>
                        <div className="text-sm text-slate-300/80 line-clamp-3">{idx.description || 'No description'}</div>
                        <div className="mt-2 text-xs text-slate-400">Owner: {idx.owner_name || '-'}</div>
                      </div>
                      <div className="flex justify-between items-end">
                        <div className="text-xs text-slate-400">{idx.created_at ? new Date(idx.created_at).toLocaleDateString() : '-'}</div>
                        <div className="text-sky-400 text-sm font-medium">Open →</div>
                      </div>
                    </div>
                  </PinContainer>
                ))
              )}
            </div>

            

            <UploadNotificationContainer notifications={notifications} onDismiss={removeNotification} position="top-right" maxNotifications={3} />
          </div>
        </SidebarInset>
      </SidebarProvider>

      <CreateIndexDialog 
        isOpen={openCreate} 
        onClose={() => setOpenCreate(false)} 
        onSuccess={handleCreateSuccess} 
      />

      <ConfirmDialog
        isOpen={confirmOpen}
        onClose={() => { setConfirmOpen(false); setConfirmTargetId(null); }}
        onConfirm={handleConfirmDelete}
        title="Delete index"
        message={`Delete index "${confirmTargetId || ''}" and all its documents, segments and files? This action cannot be undone.`}
        confirmText="Delete"
        cancelText="Cancel"
        variant="destructive"
      />
    </div>
  );
}


