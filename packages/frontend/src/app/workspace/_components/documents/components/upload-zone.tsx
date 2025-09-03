import React, { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { GlowingEffect } from "@/components/ui/glowing-effect";
import { cn } from "@/lib/utils";
import { Upload, X, CheckCircle, AlertCircle } from "lucide-react";
import { UploadFile } from "@/types/document.types";
import { getFileIcon } from "@/utils/file-utils";

interface UploadZoneProps {
  showUploadZone: boolean;
  uploadFiles: UploadFile[];
  isUploading: boolean;
  isDragActive: boolean;
  getRootProps: () => any;
  getInputProps: () => any;
  removeFile: (fileId: string) => void;
  handleDuplicateFile?: (file: UploadFile) => void;
  formatFileSize: (size: number) => string;
  startUpload: () => void;
  onClose?: () => void;
}

export function UploadZone({
  showUploadZone,
  uploadFiles,
  isUploading,
  isDragActive,
  getRootProps,
  getInputProps,
  removeFile,
  handleDuplicateFile,
  formatFileSize,
  startUpload,
  onClose
}: UploadZoneProps) {
  const pendingFiles = uploadFiles.filter(f => f.status === 'pending');
  const conflictFiles = uploadFiles.filter(f => f.status === 'conflict');
  const uploadingFiles = uploadFiles.filter(f => f.status === 'uploading');
  const hasFiles = uploadFiles.length > 0;

  // 업로드 종료 시점에만 자동 닫기 (재오픈 시 즉시 닫히는 문제 방지)
  const prevUploadingRef = useRef(false);
  const prevFilesCountRef = useRef(0);
  useEffect(() => {
    const justFinishedUploading = prevUploadingRef.current && !isUploading;
    const filesClearedNow = prevFilesCountRef.current > 0 && uploadFiles.length === 0;
    if (justFinishedUploading && filesClearedNow) {
      onClose?.();
    }
    prevUploadingRef.current = isUploading;
    prevFilesCountRef.current = uploadFiles.length;
  }, [isUploading, uploadFiles.length, onClose]);

  return (
    <AnimatePresence>
      {showUploadZone && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.3 }}
          className="mb-6"
        >
          {/* Close button */}
          {onClose && (
            <div className="flex justify-end mb-2">
              <Button
                onClick={onClose}
                size="sm"
                variant="ghost"
                className="h-8 w-8 p-0 text-slate-400 hover:text-white hover:bg-slate-700"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          )}
          
          <div 
            {...getRootProps()} 
            className={cn(
              "relative border-2 border-dashed border-white/20 hover:border-cyan-500/50 rounded-lg p-6 transition-colors cursor-pointer bg-black hover:bg-cyan-500/5",
                            isDragActive 
                ? "border-cyan-400 bg-cyan-500/10" 
                : "",
              isUploading && "opacity-50 cursor-not-allowed"
            )}
          >
            {/* Glowing Effect for Upload Zone */}
            <GlowingEffect
              variant="blue"
              proximity={100}
              spread={40}
              borderWidth={2}
              movementDuration={2}
              className="opacity-40"
              disabled={isUploading}
            />
            
            <input {...getInputProps()} />
            <div className="text-center">
              <Upload className="h-12 w-12 text-slate-400 mx-auto mb-4" />
              <p className="text-lg font-medium text-white mb-2">
                Drag and drop files or click to upload
              </p>
              <p className="text-sm text-slate-400">
                Supports documents (PDF, DOC, TXT), images (PNG, JPG, GIF, TIFF), videos (MP4, MOV, AVI), and audio files (MP3, WAV, FLAC) up to 500MB<br/>
                <span className="text-xs">All files are uploaded directly to secure cloud storage</span>
              </p>
            </div>
          </div>

          {/* Uploaded file list */}
          {hasFiles && (
            <div className="mt-4 space-y-3">
              {uploadFiles.map((file) => (
                                    <div key={file.id} className="bg-black rounded-lg p-3 border border-white/[0.1]">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      {getFileIcon(file.name, "h-4 w-4")}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-white truncate">
                          {file.name}
                        </p>
                        <p className="text-xs text-slate-400">
                          {formatFileSize(file.size)}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {file.status === 'pending' && (
                        <Button
                          onClick={() => removeFile(file.id)}
                          size="sm"
                          variant="ghost"
                          className="h-6 w-6 p-0 text-slate-400 hover:text-white"
                        >
                          <X className="h-3 w-3" />
                        </Button>
                      )}
                      {file.status === 'conflict' && (
                        <div className="flex items-center gap-2">
                          <Badge className="bg-orange-500/20 text-orange-400 border-orange-500/30 text-xs">
                            Duplicate
                          </Badge>
                          <Button
                            onClick={() => handleDuplicateFile && handleDuplicateFile(file)}
                            size="sm"
                            className="h-6 px-2 text-xs bg-orange-600 hover:bg-orange-700 text-white"
                          >
                            Resolve
                          </Button>
                        </div>
                      )}
                      {file.status === 'uploading' && (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-blue-400">
                            Uploading...
                          </span>
                        </div>
                      )}
                      {file.status === 'success' && (
                        <div className="flex items-center gap-2">
                          <CheckCircle className="h-4 w-4 text-emerald-400" />
                          <span className="text-xs text-emerald-400">Complete</span>
                        </div>
                      )}
                      {file.status === 'error' && (
                        <div className="flex items-center gap-2">
                          <AlertCircle className="h-4 w-4 text-red-400" />
                          <span className="text-xs text-red-400">Error</span>
                          <Button
                            onClick={() => removeFile(file.id)}
                            size="sm"
                            variant="ghost"
                            className="h-6 w-6 p-0 text-slate-400 hover:text-white"
                          >
                            <X className="h-3 w-3" />
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Upload controls */}
          {hasFiles && (
            <div className="mt-4 flex items-center justify-between">
              <div className="text-sm text-slate-400">
                {pendingFiles.length > 0 && (
                  <span>{pendingFiles.length} file{pendingFiles.length > 1 ? 's' : ''} ready to upload</span>
                )}
                {conflictFiles.length > 0 && (
                  <span className="text-orange-400">
                    {conflictFiles.length} file{conflictFiles.length > 1 ? 's' : ''} need{conflictFiles.length === 1 ? 's' : ''} resolution
                  </span>
                )}
                {uploadingFiles.length > 0 && (
                  <span className="text-blue-400">
                    {uploadingFiles.length} file{uploadingFiles.length > 1 ? 's' : ''} uploading...
                  </span>
                )}
              </div>
              <div className="flex gap-2">
                <Button
                  onClick={startUpload}
                  disabled={isUploading || pendingFiles.length === 0 || conflictFiles.length > 0}
                  className="bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50"
                  size="sm"
                >
                  {isUploading ? 'Uploading...' : 'Upload Files'}
                </Button>
              </div>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
} 