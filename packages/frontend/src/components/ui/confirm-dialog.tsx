"use client";

import { AlertTriangle, X } from "lucide-react";
import { Button } from "./button";

interface ConfirmDialogProps {
    isOpen: boolean;
    onClose: () => void;
    onConfirm: () => void;
    title?: string;
    message?: string;
    confirmText?: string;
    cancelText?: string;
    variant?: "default" | "destructive";
}

export function ConfirmDialog({
    isOpen,
    onClose,
    onConfirm,
    title = "Confirm",
    message = "Are you sure you want to continue?",
    confirmText = "Confirm",
    cancelText = "Cancel",
    variant = "default"
}: ConfirmDialogProps) {
    if (!isOpen) return null;

    const handleConfirm = () => {
        onConfirm();
        onClose();
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            {/* 배경 오버레이 */}
            <div 
                className="fixed inset-0 bg-black/50 backdrop-blur-sm" 
                onClick={onClose}
            />
            
            {/* 다이얼로그 */}
            <div className="relative bg-slate-800 border border-slate-700 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
                {/* 닫기 버튼 */}
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 text-slate-400 hover:text-slate-200 transition-colors"
                >
                    <X className="h-4 w-4" />
                </button>

                {/* 아이콘과 제목 */}
                <div className="flex items-center gap-3 mb-4">
                    {variant === "destructive" && (
                        <div className="flex-shrink-0 w-10 h-10 bg-orange-500/20 rounded-full flex items-center justify-center">
                            <AlertTriangle className="h-5 w-5 text-orange-400" />
                        </div>
                    )}
                    <h3 className="text-lg font-semibold text-white">
                        {title}
                    </h3>
                </div>

                {/* 메시지 */}
                <p className="text-slate-300 mb-6">
                    {message}
                </p>

                {/* 버튼들 */}
                <div className="flex justify-end gap-3">
                    <Button
                        variant="ghost"
                        onClick={onClose}
                        className="text-slate-300 hover:text-white hover:bg-slate-700"
                    >
                        {cancelText}
                    </Button>
                    <Button
                        variant={variant === "destructive" ? "destructive" : "default"}
                        onClick={handleConfirm}
                        className={variant === "destructive" 
                            ? "bg-orange-600 hover:bg-orange-700 text-white" 
                            : ""
                        }
                    >
                        {confirmText}
                    </Button>
                </div>
            </div>
        </div>
    );
} 