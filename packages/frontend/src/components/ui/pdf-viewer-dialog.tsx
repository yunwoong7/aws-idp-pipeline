"use client";

import { useEffect, useState } from "react";
import ReactDOM from "react-dom";
import { FileText, X, LoaderIcon } from "lucide-react";
import { documentApi } from "@/lib/api";

interface Document {
    upload_id: string;
    file_name: string;
    file_uri?: string;
    project_id?: string;
}

interface PdfViewerDialogProps {
    isOpen: boolean;
    onClose: () => void;
    document: Document | null;
    indexId?: string;
}

export function PdfViewerDialog({ isOpen, onClose, document, indexId }: PdfViewerDialogProps) {
    const [presignedUrl, setPresignedUrl] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!isOpen || !document?.file_uri) {
            setPresignedUrl(null);
            setError(null);
            return;
        }

        const fetchPresignedUrl = async () => {
            setIsLoading(true);
            setError(null);
            
            try {
                const indexIdParam = indexId || '';
                const response = await documentApi.getPresignedUrlFromS3Uri(document.file_uri!, 3600, indexIdParam);
                setPresignedUrl(response.presigned_url);
            } catch (err) {
                console.error('Failed to get presigned URL for PDF:', err);
                setError(err instanceof Error ? err.message : 'Failed to load PDF');
            } finally {
                setIsLoading(false);
            }
        };

        fetchPresignedUrl();
    }, [isOpen, document?.file_uri, indexId]);

    if (!isOpen) return null;

    // Portal을 사용해서 body에 직접 렌더링하여 쌓임 맥락 문제 해결
    const portalRoot = typeof window !== 'undefined' && typeof window.document !== 'undefined' ? window.document.body : null;
    
    if (!portalRoot) return null;

    return ReactDOM.createPortal(
        <div 
            className="fixed inset-0 bg-black/50 flex items-center justify-center"
            style={{ zIndex: 9999 }}
        >
            <div className="w-[95vw] h-[95vh] bg-slate-900 border border-slate-700 rounded-lg flex flex-col overflow-hidden">
                <div className="px-6 py-3 border-b border-slate-700 flex-shrink-0 bg-slate-800 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <FileText className="h-5 w-5 text-blue-400" />
                        <h2 className="text-white text-lg font-semibold">
                            PDF 문서 - {document?.file_name}
                        </h2>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-slate-400 hover:text-white p-1 rounded"
                    >
                        <X className="h-5 w-5" />
                    </button>
                </div>
                <div className="flex-1 w-full h-full min-h-0">
                    {isLoading ? (
                        <div className="flex items-center justify-center h-full text-slate-400 bg-slate-900">
                            <div className="text-center">
                                <LoaderIcon className="h-16 w-16 mx-auto mb-4 text-blue-400 animate-spin" />
                                <p className="text-sm">PDF 로딩 중...</p>
                                <p className="text-xs mt-2 text-slate-500">
                                    Pre-signed URL을 생성하고 있습니다.
                                </p>
                            </div>
                        </div>
                    ) : error ? (
                        <div className="flex items-center justify-center h-full text-slate-400 bg-slate-900">
                            <div className="text-center">
                                <FileText className="h-16 w-16 mx-auto mb-4 text-red-500" />
                                <p className="text-sm text-red-400">PDF 로딩 실패</p>
                                <p className="text-xs mt-2 text-slate-500">
                                    {error}
                                </p>
                                <p className="text-xs mt-1 text-slate-500">
                                    S3 URI: {document?.file_uri}
                                </p>
                            </div>
                        </div>
                    ) : presignedUrl ? (
                        <iframe
                            src={presignedUrl}
                            className="w-full h-full border-0"
                            title={`PDF - ${document?.file_name}`}
                        />
                    ) : (
                        <div className="flex items-center justify-center h-full text-slate-400 bg-slate-900">
                            <div className="text-center">
                                <FileText className="h-16 w-16 mx-auto mb-4 text-slate-600" />
                                <p className="text-sm">PDF 파일을 찾을 수 없습니다.</p>
                                <p className="text-xs mt-2 text-slate-500">
                                    파일 URI가 제공되지 않았습니다.
                                </p>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>,
        portalRoot
    );
}