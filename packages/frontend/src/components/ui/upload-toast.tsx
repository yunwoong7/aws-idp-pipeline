import React, { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { X, Upload, CheckCircle, AlertCircle, Clock, FileText, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";

// 백업 파일의 복잡한 토스트 타입들
interface UploadToastItem {
    id: string;
    fileName: string;
    fileType: string;
    status: "UPLOADING" | "SUCCESS" | "ERROR";
    progress: number;
    error?: string;
}

interface ProcessingToastItem {
    id: string;
    documentId: string;
    fileName: string;
    status: "PROCESSING" | "COMPLETED" | "ERROR";
    currentStep: string;
    stepLabel: string;
    progress: number;
    totalSteps: number;
    currentStepIndex: number;
    error?: string;
}

// 백업 파일의 CircleProgress 컴포넌트
const CircleProgress = ({ progress }: { progress: number }) => {
    const normalizedProgress = Math.min(Math.max(0, progress), 100);
    const circumference = 2 * Math.PI * 10;
    const offset = circumference - (normalizedProgress / 100) * circumference;

    return (
        <div className="relative h-5 w-5">
            <svg className="h-5 w-5 -rotate-90" viewBox="0 0 24 24">
                <circle
                    className="stroke-slate-600"
                    strokeWidth="3"
                    fill="none"
                    r="10"
                    cx="12"
                    cy="12"
                />
                <circle
                    className="stroke-blue-400 transition-all duration-300"
                    strokeWidth="3"
                    strokeLinecap="round"
                    fill="none"
                    r="10"
                    cx="12"
                    cy="12"
                    strokeDasharray={circumference}
                    strokeDashoffset={offset}
                />
            </svg>
        </div>
    );
};

// 백업 파일의 StatusIcon 컴포넌트
const StatusIcon = ({ status }: { status: UploadToastItem["status"] }) => {
    if (status === "SUCCESS") return <CheckCircle className="w-5 h-5 text-emerald-400" />;
    if (status === "ERROR") return <AlertCircle className="w-5 h-5 text-red-400" />;
    return null;
};

// 백업 파일의 UploadItemRow 컴포넌트
const UploadItemRow = ({
    item,
    onRemove,
}: {
    item: UploadToastItem;
    onRemove: (id: string) => void;
}) => (
    <div className="flex max-w-[280px] items-center justify-between py-2">
        <div className="flex items-center gap-2 min-w-0 flex-1">
            <FileText
                className={cn(
                    "w-5 h-5 text-red-400",
                    item.status === "UPLOADING" && "opacity-50"
                )}
            />
            <span
                className="truncate text-sm text-slate-300 cursor-default"
                title={item.fileName}
            >
                {item.fileName}
            </span>
        </div>

        <div className="flex items-center gap-1 ml-2">
            {item.status === "UPLOADING" ? (
                <div className="relative group">
                    <CircleProgress progress={item.progress} />
                    <button
                        onClick={() => onRemove(item.id)}
                        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center hover:bg-slate-700 rounded-full"
                    >
                        <X className="h-3 w-3 text-slate-400" />
                    </button>
                </div>
            ) : (
                <>
                    <StatusIcon status={item.status} />
                    <button
                        onClick={() => onRemove(item.id)}
                        className="flex items-center justify-center hover:bg-slate-600 hover:text-white size-5 rounded-full cursor-pointer transition-colors"
                    >
                        <X className="h-3 w-3" />
                    </button>
                </>
            )}
        </div>
    </div>
);

// 백업 파일의 DriveUploadToast 컴포넌트
export function DriveUploadToast({
    items,
    onRemoveItem,
    onClearAll,
    className = "fixed bottom-4 right-4 z-50 w-[320px]",
}: {
    items: UploadToastItem[];
    onRemoveItem: (id: string) => void;
    onClearAll: () => void;
    className?: string;
}) {
    const [isExpanded, setIsExpanded] = useState(true);
    const uploadingCount = items.filter(
        (item) => item.status === "UPLOADING"
    ).length;

    if (items.length === 0) return null;

    return (
        <div className={className}>
            <div className="bg-slate-800/95 backdrop-blur-sm rounded-xl shadow-xl border border-slate-700/50">
                <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/50">
                    <span className="text-sm font-semibold text-slate-100">
                        {uploadingCount > 0
                            ? `Uploading ${uploadingCount} files`
                            : "Upload Complete"}
                    </span>
                    <div className="flex items-center gap-1">
                        <button
                            onClick={() => setIsExpanded(!isExpanded)}
                            className="p-1 rounded transition-colors hover:bg-slate-700"
                            title={isExpanded ? "Collapse" : "Expand"}
                        >
                            {isExpanded ? (
                                <ChevronDown className="h-4 w-4 text-slate-200" />
                            ) : (
                                <ChevronUp className="h-4 w-4 text-slate-200" />
                            )}
                        </button>
                        <button
                            onClick={onClearAll}
                            className="p-1 hover:bg-slate-700 rounded transition-colors"
                            title="Clear All"
                        >
                            <X className="h-4 w-4 text-slate-200" />
                        </button>
                    </div>
                </div>
                {isExpanded && (
                    <div className="max-h-64 overflow-y-auto">
                        {items.map((item) => (
                            <div
                                key={item.id}
                                className="group px-4 hover:bg-slate-700/50 transition-colors"
                            >
                                <UploadItemRow item={item} onRemove={onRemoveItem} />
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

// 백업 파일의 ProcessingStatusIcon
const ProcessingStatusIcon = ({ status }: { status: ProcessingToastItem["status"] }) => {
    if (status === "COMPLETED") return <CheckCircle className="w-5 h-5 text-emerald-400" />;
    if (status === "ERROR") return <AlertCircle className="w-5 h-5 text-red-400" />;
    return <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />;
};

// 백업 파일의 ProcessingStepIndicator
const ProcessingStepIndicator = ({ 
    currentStepIndex, 
    totalSteps, 
    currentStep 
}: { 
    currentStepIndex: number; 
    totalSteps: number; 
    currentStep: string;
}) => {
    return (
        <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-blue-400" />
            <div className="flex items-center gap-1">
                {Array.from({ length: totalSteps }, (_, index) => (
                    <div
                        key={index}
                        className={cn(
                            "w-1.5 h-1.5 rounded-full transition-colors duration-300",
                            index <= currentStepIndex 
                                ? index === currentStepIndex 
                                    ? "bg-blue-400" 
                                    : "bg-emerald-400"
                                : "bg-slate-600"
                        )}
                    />
                ))}
            </div>
        </div>
    );
};

// 백업 파일의 ProcessingItemRow
const ProcessingItemRow = ({
    item,
    onRemove,
}: {
    item: ProcessingToastItem;
    onRemove: (id: string) => void;
}) => (
    <div className="flex max-w-[300px] items-center justify-between py-3">
        <div className="flex items-center gap-3 min-w-0 flex-1">
            <div className="flex-shrink-0">
                <ProcessingStatusIcon status={item.status} />
            </div>
            <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1">
                    <span className="truncate text-sm font-medium text-slate-200" title={item.fileName}>
                        {item.fileName}
                    </span>
                </div>
                <div className="text-xs text-slate-400 mb-2">
                    {item.stepLabel}
                </div>
                <ProcessingStepIndicator 
                    currentStepIndex={item.currentStepIndex}
                    totalSteps={item.totalSteps}
                    currentStep={item.currentStep}
                />
            </div>
        </div>
        <button
            onClick={() => onRemove(item.id)}
            className="flex-shrink-0 ml-2 p-1 hover:bg-slate-600 rounded transition-colors"
        >
            <X className="h-3 w-3 text-slate-400" />
        </button>
    </div>
);

// 백업 파일의 DocumentProcessingToast
export function DocumentProcessingToast({
    items,
    onRemoveItem,
    onClearAll,
    className = "fixed bottom-4 right-4 z-50 w-[350px]",
}: {
    items: ProcessingToastItem[];
    onRemoveItem: (id: string) => void;
    onClearAll: () => void;
    className?: string;
}) {
    const [isExpanded, setIsExpanded] = useState(true);
    const processingCount = items.filter(
        (item) => item.status === "PROCESSING"
    ).length;

    if (items.length === 0) return null;

    return (
        <div className={className}>
            <div className="bg-slate-800/95 backdrop-blur-sm rounded-xl shadow-xl border border-slate-700/50">
                <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/50">
                    <span className="text-sm font-semibold text-slate-100">
                        {processingCount > 0
                            ? `Processing ${processingCount} documents`
                            : "Processing Complete"}
                    </span>
                    <div className="flex items-center gap-1">
                        <button
                            onClick={() => setIsExpanded(!isExpanded)}
                            className="p-1 rounded transition-colors hover:bg-slate-700"
                            title={isExpanded ? "Collapse" : "Expand"}
                        >
                            {isExpanded ? (
                                <ChevronDown className="h-4 w-4 text-slate-200" />
                            ) : (
                                <ChevronUp className="h-4 w-4 text-slate-200" />
                            )}
                        </button>
                        <button
                            onClick={onClearAll}
                            className="p-1 hover:bg-slate-700 rounded transition-colors"
                            title="Clear All"
                        >
                            <X className="h-4 w-4 text-slate-200" />
                        </button>
                    </div>
                </div>
                {isExpanded && (
                    <div className="max-h-64 overflow-y-auto">
                        {items.map((item) => (
                            <div
                                key={item.id}
                                className="group px-4 hover:bg-slate-700/50 transition-colors"
                            >
                                <ProcessingItemRow item={item} onRemove={onRemoveItem} />
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

// 이전 버전과의 호환성을 위한 기본 UploadToast
export function UploadToast({ toast, onRemove }: { toast: any; onRemove: (id: string) => void; }) {
    return (
        <div className="fixed bottom-4 right-4 z-50">
            <Card className="w-[350px] bg-slate-800 border-slate-700">
                <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                        <span className="text-sm text-slate-200">{toast.message || "Upload in progress"}</span>
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onRemove(toast.id)}
                            className="h-6 w-6 p-0"
                        >
                            <X className="h-3 w-3" />
                        </Button>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}

// Export the types for use in other components
export type { UploadToastItem, ProcessingToastItem }; 