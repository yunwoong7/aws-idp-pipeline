"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { cn } from "@/lib/utils";

interface ResizablePanelProps {
    children: [React.ReactNode, React.ReactNode]; // [leftPanel, rightPanel]
    defaultLeftWidth?: number; // 기본 왼쪽 패널 너비 (%)
    minLeftWidth?: number; // 최소 왼쪽 패널 너비 (%)
    maxLeftWidth?: number; // 최대 왼쪽 패널 너비 (%)
    className?: string;
    onResize?: (leftWidth: number) => void;
}

export function ResizablePanel({
    children,
    defaultLeftWidth = 50,
    minLeftWidth = 20,
    maxLeftWidth = 80,
    className,
    onResize
}: ResizablePanelProps) {
    const [leftWidth, setLeftWidth] = useState(defaultLeftWidth);
    const [isDragging, setIsDragging] = useState(false);
    const containerRef = useRef<HTMLDivElement>(null);
    const rafRef = useRef<number | undefined>(undefined);

    const updateWidth = useCallback((clientX: number) => {
        if (!containerRef.current) return;

        const containerRect = containerRef.current.getBoundingClientRect();
        const containerWidth = containerRect.width;
        const relativeX = clientX - containerRect.left;
        const newLeftWidth = Math.max(
            minLeftWidth,
            Math.min(maxLeftWidth, (relativeX / containerWidth) * 100)
        );

        setLeftWidth(newLeftWidth);
        onResize?.(newLeftWidth);
    }, [minLeftWidth, maxLeftWidth, onResize]);

    const handleMouseDown = useCallback((e: React.MouseEvent) => {
        e.preventDefault();
        setIsDragging(true);
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
    }, []);

    const handleMouseMove = useCallback((e: MouseEvent) => {
        if (!isDragging) return;
        
        if (rafRef.current) {
            cancelAnimationFrame(rafRef.current);
        }
        
        rafRef.current = requestAnimationFrame(() => {
            updateWidth(e.clientX);
        });
    }, [isDragging, updateWidth]);

    const handleMouseUp = useCallback(() => {
        setIsDragging(false);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        
        if (rafRef.current) {
            cancelAnimationFrame(rafRef.current);
        }
    }, []);

    // 전역 마우스 이벤트 리스너 등록
    useEffect(() => {
        if (isDragging) {
            document.addEventListener('mousemove', handleMouseMove);
            document.addEventListener('mouseup', handleMouseUp);
            
            return () => {
                document.removeEventListener('mousemove', handleMouseMove);
                document.removeEventListener('mouseup', handleMouseUp);
            };
        }
    }, [isDragging, handleMouseMove, handleMouseUp]);

    // 컴포넌트 언마운트 시 정리
    useEffect(() => {
        return () => {
            if (rafRef.current) {
                cancelAnimationFrame(rafRef.current);
            }
        };
    }, []);

    const [leftPanel, rightPanel] = children;
    const rightWidth = 100 - leftWidth;

    return (
        <div 
            ref={containerRef}
            className={cn("flex h-full w-full relative", className)}
        >
            {/* 왼쪽 패널 */}
            <div 
                className="flex-shrink-0 h-full overflow-hidden"
                style={{ width: `${leftWidth}%` }}
            >
                {leftPanel}
            </div>

            {/* 리사이즈 핸들러 */}
            <div
                className={cn(
                    "relative w-1 bg-gradient-to-b from-cyan-500/40 via-slate-500/30 to-cyan-600/40 cursor-col-resize flex-shrink-0 group hover:w-2 transition-all duration-200",
                    isDragging && "w-2 bg-gradient-to-b from-cyan-400/60 via-slate-400/40 to-cyan-500/60"
                )}
                onMouseDown={handleMouseDown}
            >
                {/* 핸들러 시각적 효과 */}
                <div className="absolute inset-y-0 left-0 w-full bg-gradient-to-b from-cyan-400/20 to-slate-400/20 opacity-0 group-hover:opacity-100 transition-opacity duration-200" />
                
                {/* 핸들러 아이콘 (중앙) */}
                <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                    <div className="bg-slate-900/90 backdrop-blur-sm rounded-md p-1 shadow-lg border border-white/10">
                        <svg className="w-3 h-3 text-white/70" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l4-4 4 4M8 15l4 4 4-4" />
                        </svg>
                    </div>
                </div>

                {/* 확장된 드래그 영역 (보이지 않음) */}
                <div className="absolute inset-y-0 -left-2 -right-2 cursor-col-resize" />
            </div>

            {/* 오른쪽 패널 */}
            <div 
                className="flex-1 h-full overflow-hidden"
                style={{ width: `${rightWidth}%` }}
            >
                {rightPanel}
            </div>
        </div>
    );
}