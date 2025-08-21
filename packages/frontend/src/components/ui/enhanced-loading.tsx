"use client";

import { motion } from "framer-motion";

interface EnhancedLoadingProps {
    size?: "sm" | "md" | "lg";
    message?: string;
    showMessage?: boolean;
}

export function EnhancedLoading({ 
    size = "md", 
    message = "Loading...", 
    showMessage = true 
}: EnhancedLoadingProps) {
    const sizeConfig = {
        sm: { ring: "h-8 w-8", text: "text-sm" },
        md: { ring: "h-12 w-12", text: "text-base" },
        lg: { ring: "h-16 w-16", text: "text-lg" }
    };

    const config = sizeConfig[size];

    return (
        <motion.div 
            className="text-center"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5 }}
        >
            <div className="relative mb-4">
                <div className={`animate-spin rounded-full border-4 border-slate-600 border-t-blue-500 mx-auto ${config.ring}`}></div>
                <div className={`absolute inset-0 rounded-full border-4 border-transparent border-t-blue-400 animate-ping mx-auto ${config.ring}`}></div>
            </div>
            {showMessage && (
                <motion.p 
                    className={`text-slate-400 ${config.text}`}
                    animate={{ opacity: [0.5, 1, 0.5] }}
                    transition={{ duration: 2, repeat: Infinity }}
                >
                    {message}
                </motion.p>
            )}
        </motion.div>
    );
}

// 페이지 전체 로딩 (대시보드용)
export function FullPageLoading({ message = "로딩 중입니다..." }: { message?: string }) {
    return (
        <div className="flex-1 flex items-center justify-center bg-gradient-to-br from-slate-900 via-blue-900 to-slate-800 h-full">
            <EnhancedLoading size="lg" message={message} />
        </div>
    );
}

// 인라인 로딩 (작은 컴포넌트용)
export function InlineLoading({ message = "Loading..." }: { message?: string }) {
    return (
        <div className="flex items-center justify-center py-8">
            <EnhancedLoading size="sm" message={message} />
        </div>
    );
}

// 오버레이 로딩 (이미지 뷰어용)
export function OverlayLoading({ message = "Loading..." }: { message?: string }) {
    return (
        <div className="absolute inset-0 bg-slate-900/75 backdrop-blur-sm flex items-center justify-center">
            <EnhancedLoading size="md" message={message} />
        </div>
    );
}