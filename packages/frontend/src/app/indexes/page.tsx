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
import { ChatBackground } from "@/components/ui/chat-background";
import { PinContainer } from "@/components/ui/3d-pin";

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
  const [indexes, setIndexes] = useState<IndexItem[]>([]);
  const [openCreate, setOpenCreate] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

            {/* Card grid (3D pin style) */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 md:gap-4 mb-8">
              {/* Create card (3D pin) */}
              <PinContainer title="Create an index" href="#" onClick={(e) => { e.preventDefault(); setOpenCreate(true); }} containerClassName="h-72 relative z-10">
                <div className="flex flex-col p-4 tracking-tight text-slate-100/80 w-[18rem] h-[18rem] bg-gradient-to-b from-slate-800/50 to-slate-800/0 backdrop-blur-sm border border-slate-700/50 rounded-2xl items-center justify-center">
                  <div className="w-10 h-10 rounded-full border border-white/20 flex items-center justify-center mb-4">
                    <PlusCircle className="w-5 h-5 text-white/80" />
                  </div>
                  <div className="text-xl font-semibold text-white mb-2">Create an index</div>
                  <div className="text-sm text-white/60 text-center max-w-[240px]">By creating an index, you can upload your own videos and start building.</div>
                </div>
              </PinContainer>

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
                // Actual index cards
                (indexes || []).map((idx) => (
                  <PinContainer key={idx.index_id} title={idx.index_id} href={`/workspace?index_id=${idx.index_id}`} containerClassName="h-72 relative z-10">
                    <div className="flex flex-col p-4 tracking-tight text-slate-100/80 w-[18rem] h-[18rem] bg-gradient-to-b from-slate-800/50 to-slate-800/0 backdrop-blur-sm border border-slate-700/50 rounded-2xl">
                      <div className="flex items-center gap-2">
                        <div className="size-3 rounded-full bg-emerald-500" />
                        <div className="text-xs text-slate-400">{idx.status || 'active'}</div>
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
    </div>
  );
}


