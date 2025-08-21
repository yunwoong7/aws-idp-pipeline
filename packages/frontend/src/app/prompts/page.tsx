"use client";

import React, { useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/common/app-sidebar";
import { Upload, Save, FileText } from "lucide-react";
import { cn } from "@/lib/utils";

type VersionItem = {
  id: string;
  name: string;
  createdAt: string;
  system_prompt: string;
  instruction: string;
};

export default function PromptManagementPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Editors
  const [systemPrompt, setSystemPrompt] = useState<string>("");
  const [instruction, setInstruction] = useState<string>("");
  const [title, setTitle] = useState<string>("Untitled Prompt");
  const [systemOpen, setSystemOpen] = useState<boolean>(false);
  const [instructionOpen, setInstructionOpen] = useState<boolean>(true);

  // Versioning (local only for now)
  const [versions, setVersions] = useState<VersionItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Highlight {{ }} placeholders
  const highlight = useMemo(() => {
    return (text: string) =>
      (text || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\{\{(.*?)\}\}/g, (_m, p1) => `<span class=\"text-cyan-300 bg-cyan-500/10 border border-cyan-400/30 rounded px-1 py-0.5\">{{${p1}}}</span>`)
        .replace(/\n/g, "<br/>");
  }, []);

  const validateBeforeSave = (): string | null => {
    // Required placeholders notice from user:
    // system_prompt must include {{DATETIME}}
    // instruction must include {{QUERY}}, {{PREVIOUS_ANALYSIS}}, {{REFERENCES}}
    const missing: string[] = [];
    if (!/\{\{\s*DATETIME\s*\}\}/.test(systemPrompt)) missing.push("system_prompt: {{DATETIME}}");
    if (!/\{\{\s*QUERY\s*\}\}/.test(instruction)) missing.push("instruction: {{QUERY}}");
    if (!/\{\{\s*PREVIOUS_ANALYSIS\s*\}\}/.test(instruction)) missing.push("instruction: {{PREVIOUS_ANALYSIS}}");
    if (!/\{\{\s*REFERENCES\s*\}\}/.test(instruction)) missing.push("instruction: {{REFERENCES}}");
    if (missing.length > 0) {
      return `필수 플레이스홀더 누락: ${missing.join(", ")}`;
    }
    return null;
  };

  const handleSaveVersion = () => {
    setError(null);
    setSuccessMsg(null);
    const err = validateBeforeSave();
    if (err) {
      setError(err);
      return;
    }
    const newVersion: VersionItem = {
      id: `${Date.now()}`,
      name: `${title} - v${versions.length + 1}`,
      createdAt: new Date().toISOString(),
      system_prompt: systemPrompt,
      instruction,
    };
    setVersions((prev) => [newVersion, ...prev]);
    setSuccessMsg("저장되었습니다 (로컬 버전)");
    setTimeout(() => setSuccessMsg(null), 1500);
  };

  const handleImportYaml = (file: File) => {
    // Design only: load text preview into editors
    const reader = new FileReader();
    reader.onload = () => {
      const txt = String(reader.result || "");
      // Simple heuristic: split into two sections by markers if present, else put all into instruction
      // In production, parse YAML and map accordingly
      const hasSys = txt.toLowerCase().includes("system_prompt:");
      const hasInstr = txt.toLowerCase().includes("instruction:");
      if (hasSys || hasInstr) {
        const sysMatch = txt.match(/system_prompt:\s*([\s\S]*?)(\n[a-z_]+:|$)/i);
        const instrMatch = txt.match(/instruction:\s*([\s\S]*?)(\n[a-z_]+:|$)/i);
        if (sysMatch) setSystemPrompt(sysMatch[1].trim());
        if (instrMatch) setInstruction(instrMatch[1].trim());
      } else {
        setInstruction(txt);
      }
      setTitle(file.name.replace(/\.(yaml|yml)$/i, ""));
    };
    reader.readAsText(file);
  };

  return (
    <div className="min-h-screen bg-black">
      <SidebarProvider className="bg-black" defaultOpen>
        <AppSidebar />

        <SidebarInset className="bg-black relative">
          <SidebarTrigger className="absolute left-3 top-3 z-40 hidden md:flex bg-black/40 border border-white/10 hover:bg-white/10" />

          <div className="flex-1 flex flex-col overflow-hidden h-[100svh] text-white">
            <div className="h-[calc(100vh-56px)]">
              <div className="flex w-full h-full">
                {/* Main editors */}
                <div className="flex-1 p-6 flex flex-col gap-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <FileText className="w-5 h-5 text-cyan-400" />
                      <input
                        className="bg-transparent border-b border-white/20 focus:border-cyan-400 outline-none text-xl font-semibold px-2 py-1"
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        className="px-3 py-2 text-sm rounded-md bg-white/10 hover:bg-white/20 border border-white/15 flex items-center gap-2"
                        onClick={() => fileInputRef.current?.click()}
                      >
                        <Upload className="w-4 h-4" /> Import YAML
                      </button>
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".yaml,.yml"
                        className="hidden"
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          if (f) handleImportYaml(f);
                        }}
                      />
                      <button
                        className="px-3 py-2 text-sm rounded-md bg-cyan-600/20 hover:bg-cyan-600/30 border border-cyan-500/30 flex items-center gap-2"
                        onClick={handleSaveVersion}
                      >
                        <Save className="w-4 h-4" /> Save Version
                      </button>
                    </div>
                  </div>

                  {error && (
                    <div className="text-red-300 bg-red-500/10 border border-red-500/30 rounded p-2 text-sm">{error}</div>
                  )}
                  {successMsg && (
                    <div className="text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded p-2 text-sm">{successMsg}</div>
                  )}

                  {/* System Prompt Editor (collapsible) */}
                  <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
                    <button
                      type="button"
                      className="w-full px-4 py-3 text-left text-sm text-white/80 flex items-center justify-between hover:bg-white/10"
                      onClick={() => setSystemOpen((v) => !v)}
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">System Prompt</span>
                        <span className="text-xs text-cyan-300">필수 포함: {'{{DATETIME}}'}</span>
                      </div>
                      <span className="text-white/60 text-xs">{systemOpen ? '접기' : '펼치기'}</span>
                    </button>
                    {systemOpen && (
                      <div className="border-t border-white/10">
                        <textarea
                          className="bg-transparent p-4 min-h-[200px] outline-none text-white/90 w-full resize-y"
                          placeholder="Write system prompt..."
                          value={systemPrompt}
                          onChange={(e) => setSystemPrompt(e.target.value)}
                        />
                      </div>
                    )}
                  </div>

                  {/* Instruction Editor (collapsible) */}
                  <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden flex flex-col flex-1">
                    <button
                      type="button"
                      className="w-full px-4 py-3 text-left text-sm text-white/80 flex items-center justify-between hover:bg-white/10"
                      onClick={() => setInstructionOpen((v) => !v)}
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">Instruction</span>
                        <span className="text-xs text-cyan-300">필수 포함: {'{{QUERY}}'}, {'{{PREVIOUS_ANALYSIS}}'}, {'{{REFERENCES}}'}</span>
                      </div>
                      <span className="text-white/60 text-xs">{instructionOpen ? '접기' : '펼치기'}</span>
                    </button>
                    {instructionOpen && (
                      <div className="border-t border-white/10 flex-1 min-h-[55vh]">
                        <textarea
                          className="bg-transparent p-4 h-full min-h-[55vh] outline-none text-white/90 w-full resize-none"
                          placeholder="Write instruction..."
                          value={instruction}
                          onChange={(e) => setInstruction(e.target.value)}
                        />
                      </div>
                    )}
                  </div>

                  {/* Helper note */}
                  <div className="text-xs text-white/60">
                    현재 구조상 system_prompt에는 {'{{DATETIME}}'} 이 포함되어야 하고, instruction에는 {'{{QUERY}}'}, {'{{PREVIOUS_ANALYSIS}}'}, {'{{REFERENCES}}'} 가 포함되어야 합니다. 저장 시 검증합니다.
                  </div>
                </div>

                {/* Versions (right column removed per request) */}
              </div>
            </div>
          </div>
        </SidebarInset>
      </SidebarProvider>
    </div>
  );
}





