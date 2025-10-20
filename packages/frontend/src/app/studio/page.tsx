"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useBranding } from "@/contexts/branding-context";
import { useAuth } from "@/contexts/auth-context";
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/common/app-sidebar";
import { CreateIndexDialog } from "@/components/common/create-index-dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { PlusCircle, Upload, Sparkles, ChevronDown, Layers, ArrowRight } from "lucide-react";
import { GlowingEffect } from "@/components/ui/glowing-effect";
import { ChatBackground } from "@/components/ui/chat-background";
import { useAlert } from "@/components/ui/alert";
import { cn } from "@/lib/utils";
import { indicesApi, documentApi } from "@/lib/api";

type IndexItem = { index_id: string; index_name: string; description?: string; owner_name?: string; created_at?: string };

export default function StudioPage() {
  const router = useRouter();
  const { settings, loading } = useBranding();
  const { canCreateIndex, canUploadDocuments, accessibleIndexes, canAccessIndex } = useAuth();
  const [indexes, setIndexes] = useState<IndexItem[]>([]);
  const [selectedIndexId, setSelectedIndexId] = useState<string>("");
  const [openCreate, setOpenCreate] = useState(false);
  const [loadingIndexes, setLoadingIndexes] = useState(true);

  const [isDragActive, setIsDragActive] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [toastMessage, setToastMessage] = useState<{text: string, type: 'success' | 'error'} | null>(null);
  const fileInputId = "studio-file-input";
  const { showError, AlertComponent } = useAlert();

  // 지원되는 파일 형식 정의
  const SUPPORTED_FILE_TYPES = {
    // Documents
    'application/pdf': ['.pdf'],
    'application/msword': ['.doc'],
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
    'text/plain': ['.txt'],
    
    // Images
    'image/png': ['.png'],
    'image/jpeg': ['.jpg', '.jpeg'],
    'image/gif': ['.gif'],
    'image/tiff': ['.tiff', '.tif'],
    
    // Videos
    'video/mp4': ['.mp4'],
    'video/quicktime': ['.mov'],
    'video/x-msvideo': ['.avi'],
    
    // Audio
    'audio/mpeg': ['.mp3'],
    'audio/wav': ['.wav'],
    'audio/flac': ['.flac'],
  };

  const SUPPORTED_EXTENSIONS = Object.values(SUPPORTED_FILE_TYPES).flat();
  const MAX_FILE_SIZE = 500 * 1024 * 1024; // 500MB

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

  // Filter indexes based on user permissions
  const filteredIndexes = useMemo(() => {
    if (accessibleIndexes === "*") {
      return indexes;
    }
    if (Array.isArray(accessibleIndexes)) {
      return indexes.filter(idx => accessibleIndexes.includes(idx.index_id));
    }
    return [];
  }, [indexes, accessibleIndexes]);

  const selectedIndex = useMemo(() => filteredIndexes.find(i => i.index_id === selectedIndexId) || null, [filteredIndexes, selectedIndexId]);

  // Simple toast function
  const showToast = (text: string, type: 'success' | 'error') => {
    console.log(`🍞 Showing toast: ${text} (${type})`);
    setToastMessage({ text, type });
    setTimeout(() => {
      console.log('🍞 Hiding toast');
      setToastMessage(null);
    }, 4000);
  };

  // 파일 검증 함수
  const validateFiles = (files: File[]) => {
    const invalidFiles: string[] = [];
    const oversizedFiles: string[] = [];
    
    files.forEach(file => {
      // 파일 크기 검증
      if (file.size > MAX_FILE_SIZE) {
        oversizedFiles.push(file.name);
        return;
      }
      
      // 파일 형식 검증
      const extension = '.' + file.name.split('.').pop()?.toLowerCase();
      const isValidType = file.type && Object.keys(SUPPORTED_FILE_TYPES).includes(file.type);
      const isValidExtension = SUPPORTED_EXTENSIONS.includes(extension);
      
      if (!isValidType && !isValidExtension) {
        invalidFiles.push(file.name);
      }
    });
    
    return { invalidFiles, oversizedFiles };
  };

  // Handle file upload
  const handleFileUpload = async (files: File[]) => {
    if (!selectedIndexId || files.length === 0) return;

    // 파일 검증
    const { invalidFiles, oversizedFiles } = validateFiles(files);
    
    if (invalidFiles.length > 0) {
      const fileList = invalidFiles.join(', ');
      console.log(`❌ Invalid file types detected: ${fileList}`);
      showError(
        'Unsupported File Type',
        `The following files are not supported: ${fileList}\n\nSupported formats: PDF, DOC/DOCX, TXT, PNG, JPG, GIF, TIFF, MP4, MOV, AVI, MP3, WAV, FLAC`
      );
      return Promise.reject(new Error('Invalid file types'));
    }
    
    if (oversizedFiles.length > 0) {
      const fileList = oversizedFiles.join(', ');
      console.log(`❌ Oversized files detected: ${fileList}`);
      showError(
        'File Too Large',
        `The following files exceed the 500MB limit: ${fileList}`
      );
      return Promise.reject(new Error('Files too large'));
    }

    setIsUploading(true);
    const uploadResults = [];

    for (const file of files) {
      try {
        console.log(`📤 Starting upload: ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`);

        // Generate upload URL
        const uploadData = await documentApi.generateUnifiedUploadUrl({
          file_name: file.name,
          file_size: file.size,
          file_type: file.type || 'application/octet-stream',
          description: `Uploaded via Studio`,
          index_id: selectedIndexId
        });

        // Upload to S3 (no progress notifications)
        await documentApi.uploadFileToS3(
          uploadData.upload_url,
          file,
          uploadData.content_type
        );

        // Notify upload completion
        await documentApi.completeLargeFileUpload(uploadData.document_id);

        // Show success notification only after completion
        showToast(`${file.name} uploaded successfully`, 'success');

        uploadResults.push({
          success: true,
          fileName: file.name,
          documentId: uploadData.document_id
        });

      } catch (error) {
        console.error(`❌ Upload failed for ${file.name}:`, error);
        
        // Show error notification only on failure
        showToast(`Failed to upload ${file.name}`, 'error');

        uploadResults.push({
          success: false,
          fileName: file.name,
          error: error instanceof Error ? error.message : 'Unknown error'
        });
      }
    }

    setIsUploading(false);
    
    const successCount = uploadResults.filter(r => r.success).length;
    const failCount = uploadResults.length - successCount;
    
    console.log(`📊 Upload completed: ${successCount} success, ${failCount} failed`);
    
    return Promise.resolve({ successCount, failCount });
  };

  // Handle file input change
  const handleFileInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    
    // Always reset input value first to prevent issues
    const resetInput = () => {
      event.target.value = '';
    };
    
    if (files.length > 0) {
      console.log(`📁 Files selected: ${files.map(f => f.name).join(', ')}`);
      handleFileUpload(files)
        .then(() => {
          console.log('📤 Upload process completed');
        })
        .catch((error) => {
          console.error('📤 Upload process failed:', error);
        })
        .finally(() => {
          resetInput();
        });
    } else {
      resetInput();
    }
  };

  // Handle drag and drop
  const handleDrop = (event: React.DragEvent) => {
    event.preventDefault();
    setIsDragActive(false);
    
    if (!selectedIndex) return;

    const files = Array.from(event.dataTransfer.files);
    if (files.length > 0) {
      handleFileUpload(files);
    }
  };

  const handleDragOver = (event: React.DragEvent) => {
    event.preventDefault();
  };

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
                <div className="text-center bg-white/5 border border-white/10 rounded-2xl px-6 py-6 backdrop-blur-md group" data-disabled={filteredIndexes.length === 0 ? true : undefined}>
                  {/* Row 1: Label alone */}
                  <div className="w-full mb-3">
                    <Label className="flex items-center gap-2 font-medium select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50 text-white/80 text-sm">Select index</Label>
                  </div>
                  {/* Row 2: Select + Create + Go to Workspace buttons inline */}
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
                            filteredIndexes.length === 0 && "opacity-60 cursor-not-allowed"
                          )}
                          value={selectedIndexId}
                          onChange={(e) => setSelectedIndexId(e.target.value)}
                          disabled={filteredIndexes.length === 0}
                        >
                          <option value="">{filteredIndexes.length ? "Choose an index" : "No accessible index"}</option>
                          {filteredIndexes.map((idx) => (
                            <option key={idx.index_id} value={idx.index_id}>{idx.index_id}</option>
                          ))}
                        </select>
                        <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        onClick={() => selectedIndexId && router.push(`/workspace?index_id=${selectedIndexId}`)}
                        disabled={!selectedIndexId}
                        className="inline-flex items-center justify-center whitespace-nowrap text-sm font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 bg-transparent border-cyan-500/50 text-cyan-400 hover:bg-cyan-500/20 hover:border-cyan-400 hover:text-cyan-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <ArrowRight className="h-4 w-4" /> Go to Workspace
                      </Button>
                      {canCreateIndex && (
                        <Button
                          onClick={() => setOpenCreate(true)}
                          className="inline-flex items-center justify-center whitespace-nowrap text-sm font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 bg-transparent border-emerald-500/50 text-emerald-400 hover:bg-emerald-500/20 hover:border-emerald-400 hover:text-emerald-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <PlusCircle className="h-4 w-4" /> Create an index
                        </Button>
                      )}
                    </div>
                  </div>
                  {filteredIndexes.length === 0 && (
                    <p className="text-emerald-300/80 text-sm mt-3">
                      {indexes.length === 0
                        ? "No index yet — Create your first index to get started."
                        : "No accessible indexes — Contact your administrator for access."}
                    </p>
                  )}
                </div>
              )}

              {/* Upload zone below controls */}
              {!canUploadDocuments ? (
                <div className="relative rounded-2xl border-2 border-dashed p-10 text-center min-h-[240px] mt-6 bg-black/30 border-amber-500/30 overflow-hidden">
                  <div className="relative flex flex-col items-center justify-center py-12 space-y-4">
                    <Upload className="h-12 w-12 text-amber-300/50" />
                    <div className="space-y-2">
                      <p className="text-amber-300/80 font-medium">Upload Permission Required</p>
                      <p className="text-white/50 text-sm">Contact your administrator to enable document upload</p>
                    </div>
                  </div>
                </div>
              ) : loadingIndexes ? (
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
                  onDragOver={handleDragOver}
                  onDrop={handleDrop}
                  className={cn(
                    "relative rounded-2xl border-2 border-dashed p-10 text-center min-h-[240px] cursor-pointer mt-6",
                    "bg-black/30 border-white/20 hover:border-cyan-400/50 hover:bg-cyan-500/5",
                    isDragActive && selectedIndex && "border-cyan-400 bg-cyan-500/10",
                    (!selectedIndex || isUploading) && "opacity-50 cursor-not-allowed pointer-events-none"
                  )}
                  onClick={() => !isUploading && selectedIndex && document.getElementById(fileInputId)?.click()}
                >
                  <GlowingEffect variant="blue" proximity={110} spread={48} borderWidth={2} movementDuration={2} className="opacity-40" />
                  <input 
                    id={fileInputId} 
                    type="file" 
                    multiple 
                    className="hidden"
                    accept={SUPPORTED_EXTENSIONS.join(',')}
                    onChange={handleFileInputChange}
                    disabled={isUploading}
                  />
                  <Upload className="h-10 w-10 text-slate-300 mx-auto mb-3" />
                  <p className="text-base md:text-lg font-medium text-white mb-2">
                    {isUploading ? "Uploading files..." : "Drag and drop files or click to upload"}
                  </p>
                  <p className="text-sm text-slate-400 mb-2">
                    Supports documents (PDF, DOC, TXT), images (PNG, JPG, GIF, TIFF), videos (MP4, MOV, AVI), and audio files (MP3, WAV, FLAC) up to 500MB
                  </p>
                  <p className="text-xs text-slate-500">
                    All files are uploaded directly to secure cloud storage
                  </p>
                  <div className="mt-4 flex gap-3 justify-center">
                    <Button 
                      variant="secondary" 
                      disabled={!selectedIndex || isUploading} 
                      className="bg-white/10 border-white/20 text-white hover:bg-white/15 disabled:opacity-50 disabled:cursor-not-allowed"
                      onClick={() => !isUploading && selectedIndex && document.getElementById(fileInputId)?.click()}
                    >
                      {isUploading ? "Uploading..." : "Browse files"}
                    </Button>
                  </div>
                  {!selectedIndex && (<p className="text-amber-300/80 text-sm mt-3">Please select an index first</p>)}
                  {isUploading && (<p className="text-cyan-300/80 text-sm mt-3">Processing your files...</p>)}
                </div>
              )}
            </div>

            {/* Simple Toast */}
            {toastMessage && (
              <div className={`fixed top-6 right-6 z-[9999] p-4 rounded-xl shadow-2xl border transition-all duration-300 transform min-w-[300px] max-w-md ${
                toastMessage.type === 'success' 
                  ? 'bg-green-600 text-white border-green-500 shadow-green-600/20' 
                  : 'bg-red-600 text-white border-red-500 shadow-red-600/20'
              }`}>
                <div className="flex items-center gap-3">
                  <div className={`w-2 h-2 rounded-full ${
                    toastMessage.type === 'success' ? 'bg-green-300' : 'bg-red-300'
                  }`} />
                  <span className="font-medium">{toastMessage.text}</span>
                </div>
              </div>
            )}
          </div>
        </SidebarInset>
      </SidebarProvider>

      <CreateIndexDialog 
        isOpen={openCreate} 
        onClose={() => setOpenCreate(false)} 
        onSuccess={handleCreateSuccess} 
      />

      {AlertComponent}

    </div>
  );
}


