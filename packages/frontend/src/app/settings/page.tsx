"use client";

import React, { useState } from "react";
import { useBranding } from "@/contexts/branding-context";
import MCPToolManager from "./_components/mcp-tool-manager";
import { BrandingSettings } from "./_components/branding-settings";
import { useRouter } from "next/navigation";
import { 
    Plug, 
    FileText,
    Paintbrush
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
    SidebarProvider,
    SidebarInset,
    SidebarTrigger,
} from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/common/app-sidebar";
import { ChatBackground } from "@/components/ui/chat-background";

interface SettingsMenuItem {
    id: string;
    name: string;
    icon: React.ComponentType<{ className?: string }>;
    description: string;
}

const settingsMenu: SettingsMenuItem[] = [
    {
        id: "branding",
        name: "Branding",
        icon: Paintbrush,
        description: "Customize company logo and branding"
    },
    {
        id: "mcp-tools",
        name: "MCP Tools",
        icon: Plug,
        description: "Manage MCP servers and tools"
    },
    {
        id: "license",
        name: "License",
        icon: FileText,
        description: "Amazon Software License and terms of use"
    }
];

export default function SettingsPage() {
    const router = useRouter();
    const [selectedMenu, setSelectedMenu] = useState("branding");
    const { settings, loading } = useBranding();

    const renderContent = () => {
        switch (selectedMenu) {
            case "branding":
                return <BrandingSettings />;
            case "mcp-tools":
                return (
                    <div className="bg-card rounded-xl border border-border">
                        <MCPToolManager />
                    </div>
                );
            case "license":
                return (
                    <div className="p-6 bg-card rounded-xl border border-border">
                        <h2 className="text-xl font-semibold mb-4 text-card-foreground">License</h2>
                        <div className="bg-muted rounded-lg p-4 border border-border">
                            <h3 className="text-lg font-medium text-card-foreground mb-3">Amazon Software License</h3>
                            <div className="text-sm text-muted-foreground leading-relaxed whitespace-pre-line font-mono">
                                {`Copyright 2025 Amazon.com, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.`}
                            </div>
                        </div>
                    </div>
                );
            default:
                return <BrandingSettings />;
        }
    };

    return (
        <div className="min-h-screen bg-black text-white">
            <SidebarProvider className="bg-black" defaultOpen>
                <AppSidebar />
                <SidebarInset className="bg-black relative">
                    <ChatBackground />
                    {/* Top header with sidebar toggle */}
                    <div className="absolute top-0 left-0 right-0 z-40 flex items-center px-3 py-3 bg-black/50 backdrop-blur-sm border-b border-white/10">
                        <SidebarTrigger className="hidden md:flex bg-black/40 border border-white/10 hover:bg-white/10" />
                    </div>

                    <div className="flex-1 flex flex-col overflow-hidden h-[100svh] pt-16">
                        <div className="h-[calc(100vh-64px)]">
                            <div className="flex w-full h-full text-white">
                                {/* Settings inner navigation */}
                                <div className="w-80 bg-white/5 border-r border-white/10 overflow-y-auto h-full">
                                    <div className="p-6">
                                        <div className="flex items-center gap-2 mb-6">
                                            <h1 className="text-xl font-bold text-white">Settings</h1>
                                            {!loading && settings.version && (
                                                <span className="text-[10px] text-gray-300 bg-white/5 border border-white/10 rounded px-2 py-0.5">v{settings.version}</span>
                                            )}
                                        </div>
                                        <nav className="space-y-2">
                                            {settingsMenu.map((item) => {
                                                const Icon = item.icon;
                                                const isActive = selectedMenu === item.id;
                                                return (
                                                    <button
                                                        key={item.id}
                                                        onClick={() => setSelectedMenu(item.id)}
                                                        className={cn(
                                                            "w-full text-left p-3 rounded-lg transition-colors group",
                                                            isActive 
                                                                ? "bg-cyan-600/20 border border-cyan-500/30" 
                                                                : "hover:bg-white/10 border border-transparent"
                                                        )}
                                                    >
                                                        <div className="flex items-start gap-3">
                                                            <Icon className={cn(
                                                                "h-5 w-5 mt-0.5 flex-shrink-0",
                                                                isActive 
                                                                    ? "text-cyan-400" 
                                                                    : "text-white/60 group-hover:text-white/80"
                                                            )} />
                                                            <div className="min-w-0">
                                                                <p className={cn(
                                                                    "font-medium text-sm",
                                                                    isActive 
                                                                        ? "text-cyan-300" 
                                                                        : "text-white/80 group-hover:text-white"
                                                                )}>
                                                                    {item.name}
                                                                </p>
                                                                <p className={cn(
                                                                    "text-xs mt-1",
                                                                    isActive 
                                                                        ? "text-cyan-300/70" 
                                                                        : "text-white/50 group-hover:text-white/70"
                                                                )}>
                                                                    {item.description}
                                                                </p>
                                                            </div>
                                                        </div>
                                                    </button>
                                                );
                                            })}
                                        </nav>
                                    </div>
                                </div>
                                {/* Settings content */}
                                <div className="flex-1 overflow-auto h-full">
                                    <div className="p-6 h-full">
                                        {renderContent()}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </SidebarInset>
            </SidebarProvider>
        </div>
    );
}