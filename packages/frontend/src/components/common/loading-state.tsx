"use client";

import { motion } from "framer-motion";

interface LoadingStateProps {
    message?: string;
    className?: string;
    size?: 'sm' | 'md' | 'lg';
    variant?: 'default' | 'minimal';
}

export function LoadingState({ 
    message = "Loading...", 
    className = "",
    size = 'md',
    variant = 'default'
}: LoadingStateProps) {
    const sizeClasses = {
        sm: 'h-8 w-8',
        md: 'h-16 w-16', 
        lg: 'h-24 w-24'
    };

    const textSizeClasses = {
        sm: 'text-sm',
        md: 'text-lg',
        lg: 'text-xl'
    };

    if (variant === 'minimal') {
        return (
            <div className={`flex items-center justify-center ${className}`}>
                <div className={`animate-spin rounded-full ${sizeClasses[size]} border-4 border-white/20 border-t-cyan-500`}></div>
                {message && (
                    <span className={`ml-3 text-white/70 ${textSizeClasses[size]}`}>
                        {message}
                    </span>
                )}
            </div>
        );
    }

    return (
        <div className={`flex-1 flex items-center justify-center bg-black h-full ${className}`}>
            <motion.div 
                className="text-center"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.5 }}
            >
                <div className="relative mb-6">
                    <div className={`animate-spin rounded-full ${sizeClasses[size]} border-4 border-white/20 border-t-cyan-500 mx-auto`}></div>
                    <div className={`absolute inset-0 rounded-full ${sizeClasses[size]} border-4 border-transparent border-t-sky-400 animate-ping mx-auto`}></div>
                </div>
                <motion.p 
                    className={`text-white/70 ${textSizeClasses[size]}`}
                    animate={{ opacity: [0.5, 1, 0.5] }}
                    transition={{ duration: 2, repeat: Infinity }}
                >
                    {message}
                </motion.p>
            </motion.div>
        </div>
    );
}