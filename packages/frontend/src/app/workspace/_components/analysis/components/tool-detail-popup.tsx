"use client";

import { useState } from "react";
import { X, Wrench, FileText, Copy, Check } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { MarkdownRenderer } from "@/components/ui/markdown-renderer";

interface ToolUseContentItem {
    id: string;
    uniqueId?: string;
    type: "tool_use";
    name: string;
    input: string;
    timestamp: number;
}

interface ToolResultContentItem {
    id: string;
    uniqueId?: string;
    type: "tool_result";
    result: string;
    timestamp: number;
    tool_use_id?: string;
}

interface ToolDetailPopupProps {
    isOpen: boolean;
    onClose: () => void;
    toolItem: ToolUseContentItem;
    toolResult?: ToolResultContentItem;
    effectiveInput: string;
}

export function ToolDetailPopup({
    isOpen,
    onClose,
    toolItem,
    toolResult,
    effectiveInput
}: ToolDetailPopupProps) {
    const [copiedSection, setCopiedSection] = useState<string | null>(null);

    const copyToClipboard = async (text: string, section: string) => {
        try {
            await navigator.clipboard.writeText(text);
            setCopiedSection(section);
            setTimeout(() => setCopiedSection(null), 2000);
        } catch (err) {
            console.error('Failed to copy text: ', err);
        }
    };

    const formatInput = () => {
        const rawInput = effectiveInput || toolItem.input || '';
        if (!rawInput.trim() || rawInput === '{}') {
            return '매개변수 없음';
        }
        
        try {
            const parsed = JSON.parse(rawInput);
            return JSON.stringify(parsed, null, 2);
        } catch {
            return rawInput;
        }
    };

    return (
        <AnimatePresence>
            {isOpen && (
                <>
                    {/* Backdrop */}
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100]"
                        onClick={onClose}
                    />
                    
                    {/* Modal */}
                    <div className="fixed inset-0 flex items-center justify-center z-[100] p-4">
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95, y: 20 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.95, y: 20 }}
                            transition={{ duration: 0.2 }}
                            className="relative w-full max-w-3xl max-h-[70vh] overflow-hidden"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <div className="relative backdrop-blur-xl bg-slate-900/95 border border-white/10 rounded-2xl shadow-2xl overflow-hidden">
                                {/* Animated border glow */}
                                <div className="absolute inset-0 rounded-2xl bg-gradient-to-r from-cyan-500/10 via-purple-500/5 to-pink-500/10 opacity-100 blur-sm"></div>
                                
                                {/* Header */}
                                <div className="relative flex items-center justify-between p-6 bg-gradient-to-r from-slate-800/60 via-slate-700/40 to-slate-800/60 border-b border-white/10">
                                    <div className="flex items-center gap-4">
                                        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-cyan-400/20 to-purple-600/20 border border-cyan-400/30 flex items-center justify-center backdrop-blur-sm">
                                            <Wrench className="h-6 w-6 text-cyan-300" />
                                        </div>
                                        <div>
                                            <h2 className="text-xl font-semibold text-white">{toolItem.name}</h2>
                                            <p className="text-sm text-slate-400 mt-1">Information</p>
                                        </div>
                                    </div>
                                    <button
                                        onClick={onClose}
                                        className="w-10 h-10 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 flex items-center justify-center transition-colors"
                                    >
                                        <X className="h-5 w-5 text-slate-300" />
                                    </button>
                                </div>

                                {/* Content */}
                                <div className="relative overflow-y-auto max-h-[50vh]">
                                    <div className="p-6 space-y-6">
                                        {/* Parameters Section */}
                                        <div>
                                            <div className="flex items-center justify-between mb-4">
                                                <div className="flex items-center gap-3">
                                                    <div className="w-8 h-8 rounded-lg bg-gradient-to-r from-cyan-400/15 to-purple-500/15 border border-cyan-400/25 flex items-center justify-center">
                                                        <Wrench className="h-4 w-4 text-cyan-300" />
                                                    </div>
                                                    <h3 className="text-lg font-medium text-white">Execution Parameters</h3>
                                                </div>
                                                <button
                                                    onClick={() => copyToClipboard(formatInput(), 'params')}
                                                    className="flex items-center gap-2 px-3 py-1.5 bg-white/5 hover:bg-white/10 rounded-lg border border-white/10 text-xs text-slate-300 transition-colors"
                                                >
                                                    {copiedSection === 'params' ? (
                                                        <>
                                                            <Check className="h-3 w-3 text-green-400" />
                                                            <span className="text-green-400">Copied</span>
                                                        </>
                                                    ) : (
                                                        <>
                                                            <Copy className="h-3 w-3" />
                                                            <span>Copy</span>
                                                        </>
                                                    )}
                                                </button>
                                            </div>
                                            <div className="bg-black/40 backdrop-blur-sm rounded-xl p-4 border border-white/10">
                                                <pre className="text-xs text-cyan-300 whitespace-pre-wrap break-words font-mono leading-relaxed overflow-x-auto">
                                                    {formatInput()}
                                                </pre>
                                            </div>
                                        </div>

                                        {/* Results Section */}
                                        {toolResult && (
                                            <div>
                                                <div className="flex items-center justify-between mb-4">
                                                    <div className="flex items-center gap-3">
                                                        <div className="w-8 h-8 rounded-lg bg-gradient-to-r from-emerald-400/15 to-blue-500/15 border border-emerald-400/25 flex items-center justify-center">
                                                            <FileText className="h-4 w-4 text-emerald-300" />
                                                        </div>
                                                        <h3 className="text-lg font-medium text-white">Execution Result</h3>
                                                    </div>
                                                    <button
                                                        onClick={() => copyToClipboard(toolResult.result, 'result')}
                                                        className="flex items-center gap-2 px-3 py-1.5 bg-white/5 hover:bg-white/10 rounded-lg border border-white/10 text-xs text-slate-300 transition-colors"
                                                    >
                                                        {copiedSection === 'result' ? (
                                                            <>
                                                                <Check className="h-3 w-3 text-green-400" />
                                                                <span className="text-green-400">Copied</span>
                                                            </>
                                                        ) : (
                                                            <>
                                                                <Copy className="h-3 w-3" />
                                                                <span>Copy</span>
                                                            </>
                                                        )}
                                                    </button>
                                                </div>
                                                <div className="bg-black/40 backdrop-blur-sm rounded-xl p-4 border border-emerald-400/20 max-h-48 overflow-y-auto">
                                                    <div className="text-emerald-100 whitespace-pre-wrap break-words text-xs leading-tight font-mono [&>*]:mb-1 [&>p]:mb-1 [&>ul]:mb-1 [&>ol]:mb-1 [&>h1]:mb-1 [&>h2]:mb-1 [&>h3]:mb-1 [&>h4]:mb-1 [&>h5]:mb-1 [&>h6]:mb-1">
                                                        <MarkdownRenderer content={toolResult.result} />
                                                    </div>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </motion.div>
                    </div>
                </>
            )}
        </AnimatePresence>
    );
}