"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useBranding } from "@/contexts/branding-context";
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/common/app-sidebar";
import { CreateIndexDialog } from "@/components/common/create-index-dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { UploadNotificationContainer } from "@/components/ui/upload-notification";
import { useUploadNotifications } from "@/hooks/use-upload-notifications";
import { PlusCircle, Upload, Sparkles, ChevronDown, Layers } from "lucide-react";
import { GlowingEffect } from "@/components/ui/glowing-effect";
import { ChatBackground } from "@/components/ui/chat-background";
import { cn } from "@/lib/utils";
import { indicesApi } from "@/lib/api";

type IndexItem = { index_id: string; index_name: string; description?: string; owner_name?: string; created_at?: string };

export default function StudioPage() {
  const router = useRouter();
  const { settings, loading } = useBranding();
  const [indexes, setIndexes] = useState<IndexItem[]>([]);
  const [selectedIndexId, setSelectedIndexId] = useState<string>("");
  const [openCreate, setOpenCreate] = useState(false);
  const [loadingIndexes, setLoadingIndexes] = useState(true);

  const { notifications, removeNotification } = useUploadNotifications({ maxNotifications: 3, autoRemove: true, autoRemoveDelay: 6000 });
  const [isDragActive, setIsDragActive] = useState(false);
  const fileInputId = "studio-file-input";

  useEffect(() => {
    let mounted = true;
    setLoadingIndexes(true);
    (async () => {
      try {
        const items = await indicesApi.list();
        if (!mounted) return;
        const mapped = (items || []).map((i: any) => ({
          index_id: i.index_id,
          index_name: i.index_id,
          description: i.description,
          owner_name: i.owner_name,
          created_at: i.created_at,
        }));
        setIndexes(mapped);
      } catch (e) {
        console.error('Failed to load indices', e);
        if (mounted) setIndexes([]);
      } finally {
        if (mounted) setLoadingIndexes(false);
      }
    })();
    return () => { mounted = false; };
  }, []);

  const selectedIndex = useMemo(() => indexes.find(i => i.index_id === selectedIndexId) || null, [indexes, selectedIndexId]);

  const handleCreateSuccess = (createdIndex: any) => {
    const newIndex: IndexItem = {
      index_id: createdIndex.index_id,
      index_name: createdIndex.index_id, // index_name과 index_id를 동일하게 사용
      description: createdIndex.description,
      owner_name: createdIndex.owner_name,
      created_at: createdIndex.created_at,
    };
    setIndexes(prev => [newIndex, ...prev]);
    setSelectedIndexId(newIndex.index_id);
    setOpenCreate(false);
  };

  return (
    <div className="min-h-screen bg-black text-white">
      <SidebarProvider className="bg-black" defaultOpen>
        <AppSidebar />
        <SidebarInset className="bg-black relative">
          <ChatBackground />
          <SidebarTrigger className="absolute left-3 top-3 z-40 hidden md:flex bg-black/40 border border-white/10 hover:bg-white/10" />

          {/* Hero */}
          <div className="pt-16 px-4 text-center relative z-10">
            <div className="max-w-4xl mx-auto space-y-6">
              <div className="flex justify-center">
                <button className="bg-gray-900/80 border border-white/10 hover:border-cyan-400/50 rounded-full px-4 py-2 flex items-center gap-2 w-fit transition-all hover:bg-gray-800/80 cursor-default">
                  <span className="text-xs flex items-center gap-2">
                    <span className="bg-gradient-to-r from-cyan-600 to-sky-700 p-1 rounded-full">
                      <Sparkles className="h-3 w-3 text-white" />
                    </span>
                    AI-Powered Document Processing
                  </span>
                </button>
              </div>
              <h1 className="text-5xl font-bold leading-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-cyan-200 to-sky-300">
                {!loading && settings.description ? (
                  settings.description.split('\n').map((line, index, array) => (
                    <span key={index}>
                      {line}
                      {index < array.length - 1 && <br />}
                    </span>
                  ))
                ) : (
                  <>
                    Transform Documents into 
                    <br />
                    Actionable Insights
                  </>
                )}
              </h1>
              <p className="text-lg text-white/70 max-w-2xl mx-auto">
                Extract, analyze, and understand content from documents, images, videos, and audio using advanced AI technology.
              </p>
            </div>
          </div>

          <div className="p-6 relative z-10">
            {/* Centered container (narrow and elegant) */}
            <div className="max-w-3xl mx-auto w-full">
              {/* Controls centered */}
              {loadingIndexes ? (
                <div className="text-center bg-white/5 border border-white/10 rounded-2xl px-6 py-6 backdrop-blur-md relative overflow-hidden">
                  {/* Shimmer effect */}
                  <div className="absolute inset-0 -skew-x-12 bg-gradient-to-r from-transparent via-white/10 to-transparent animate-shimmer"></div>
                  
                  <div className="flex flex-col items-center justify-center py-8 space-y-4">
                    {/* Spinning loader */}
                    <div className="relative">
                      <div className="w-8 h-8 border-2 border-emerald-500/30 border-t-emerald-400 rounded-full animate-spin"></div>
                      <div className="absolute inset-0 w-8 h-8 border-2 border-transparent border-t-cyan-400 rounded-full animate-spin animation-delay-150"></div>
                    </div>
                    
                    <div className="space-y-2">
                      <p className="text-emerald-300/80 font-medium">Loading indexes...</p>
                      <p className="text-white/50 text-sm">Preparing your workspace</p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-center bg-white/5 border border-white/10 rounded-2xl px-6 py-6 backdrop-blur-md group" data-disabled={indexes.length === 0 ? true : undefined}>
                  {/* Row 1: Label alone */}
                  <div className="w-full mb-3">
                    <Label className="flex items-center gap-2 font-medium select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50 text-white/80 text-sm">Select index</Label>
                  </div>
                  {/* Row 2: Select + Create button inline */}
                  <div className="flex items-center justify-center gap-3">
                    <div className="relative group rounded-2xl">
                      {/* Gradient ring */}
                      <div className="pointer-events-none absolute -inset-[1px] rounded-2xl bg-gradient-to-r from-emerald-500/40 via-cyan-500/40 to-blue-500/40 opacity-30 blur-[2px] transition-opacity duration-300 group-hover:opacity-60 group-focus-within:opacity-80" />
                      {/* Field container */}
                      <div className="relative rounded-2xl bg-white/5 border border-white/15 backdrop-blur-md shadow-[0_0_0_1px_rgba(255,255,255,0.08)]">
                        <Layers className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-emerald-300/80" />
                        <select
                          aria-label="Select index"
                          className={cn(
                            "peer appearance-none h-12 rounded-2xl bg-transparent text-white pl-9 pr-10 min-w-[26rem] text-base",
                            "focus-visible:outline-none focus:border-emerald-400/60 focus:ring-2 focus:ring-emerald-400/30",
                            "hover:bg-white/5 transition-all",
                            indexes.length === 0 && "opacity-60 cursor-not-allowed"
                          )}
                          value={selectedIndexId}
                          onChange={(e) => setSelectedIndexId(e.target.value)}
                          disabled={indexes.length === 0}
                        >
                          <option value="">{indexes.length ? "Choose an index" : "No index yet"}</option>
                          {indexes.map((idx) => (
                            <option key={idx.index_id} value={idx.index_id}>{idx.index_id}</option>
                          ))}
                        </select>
                        <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
                      </div>
                    </div>
                    <Button
                      onClick={() => setOpenCreate(true)}
                      className="inline-flex items-center justify-center whitespace-nowrap text-sm font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 bg-transparent border-emerald-500/50 text-emerald-400 hover:bg-emerald-500/20 hover:border-emerald-400 hover:text-emerald-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <PlusCircle className="h-4 w-4" /> Create an index
                    </Button>
                  </div>
                  {indexes.length === 0 && (
                    <p className="text-emerald-300/80 text-sm mt-3">
                      No index yet — Create your first index to get started.
                    </p>
                  )}
                </div>
              )}

              {/* Upload zone below controls */}
              {loadingIndexes ? (
                <div className="relative rounded-2xl border-2 border-dashed p-10 text-center min-h-[240px] mt-6 bg-black/30 border-white/20 overflow-hidden">
                  {/* Floating particles effect */}
                  <div className="absolute inset-0">
                    <div className="absolute top-4 left-8 w-1 h-1 bg-cyan-400/60 rounded-full animate-bounce animation-delay-0"></div>
                    <div className="absolute top-12 right-12 w-1 h-1 bg-emerald-400/60 rounded-full animate-bounce animation-delay-300"></div>
                    <div className="absolute bottom-8 left-16 w-1 h-1 bg-blue-400/60 rounded-full animate-bounce animation-delay-700"></div>
                    <div className="absolute bottom-16 right-8 w-1 h-1 bg-cyan-400/60 rounded-full animate-bounce animation-delay-500"></div>
                  </div>
                  
                  {/* Pulsing gradient overlay */}
                  <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-500/5 to-transparent animate-pulse"></div>
                  
                  <div className="relative flex flex-col items-center justify-center py-12 space-y-4">
                    {/* Upload icon with glow */}
                    <div className="relative">
                      <Upload className="h-12 w-12 text-cyan-300/80 animate-pulse" />
                      <div className="absolute inset-0 h-12 w-12 bg-cyan-400/20 rounded-full blur-xl animate-ping"></div>
                    </div>
                    
                    <div className="space-y-2">
                      <p className="text-cyan-300/80 font-medium">Getting upload zone ready...</p>
                      <p className="text-white/50 text-sm">Setting up file processing</p>
                    </div>
                    
                    {/* Progress bar */}
                    <div className="w-48 h-1 bg-white/10 rounded-full overflow-hidden">
                      <div className="h-full bg-gradient-to-r from-cyan-400 to-emerald-400 rounded-full animate-pulse"></div>
                    </div>
                  </div>
                </div>
              ) : (
                <div
                  onDragEnter={() => setIsDragActive(true)}
                  onDragLeave={() => setIsDragActive(false)}
                  className={cn(
                    "relative rounded-2xl border-2 border-dashed p-10 text-center min-h-[240px] cursor-pointer mt-6",
                    "bg-black/30 border-white/20 hover:border-cyan-400/50 hover:bg-cyan-500/5",
                    isDragActive && selectedIndex && "border-cyan-400 bg-cyan-500/10",
                    !selectedIndex && "opacity-50 cursor-not-allowed pointer-events-none"
                  )}
                  onClick={() => selectedIndex && document.getElementById(fileInputId)?.click()}
                >
                  <GlowingEffect variant="blue" proximity={110} spread={48} borderWidth={2} movementDuration={2} className="opacity-40" />
                  <input id={fileInputId} type="file" multiple className="hidden" />
                  <Upload className="h-10 w-10 text-slate-300 mx-auto mb-3" />
                  <p className="text-base md:text-lg font-medium text-white mb-2">Drag and drop files or click to upload</p>
                  <p className="text-sm text-slate-400">PDF, Images, Videos, Audio (Max 2GB)</p>
                  <div className="mt-4 flex gap-3 justify-center">
                    <Button variant="secondary" disabled={!selectedIndex} className="bg-white/10 border-white/20 text-white hover:bg-white/15 disabled:opacity-50 disabled:cursor-not-allowed">Browse files</Button>
                    <Button disabled={!selectedIndex} className="bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50 disabled:cursor-not-allowed">Upload Files</Button>
                  </div>
                  {!selectedIndex && (<p className="text-amber-300/80 text-sm mt-3">Please create an index first</p>)}
                </div>
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


