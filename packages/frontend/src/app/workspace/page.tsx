"use client";

import { useState, useCallback, useEffect, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from 'next/navigation';
import {
    SidebarProvider,
    SidebarInset,
    SidebarTrigger,
} from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/common/app-sidebar";
import { ArrowLeft, FileText, BarChart3, Search, AlertCircle, MessageCircle, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAlert } from "@/components/ui/alert";
import { motion } from "framer-motion";
import { useAuth } from "@/contexts/auth-context";

// Import new tab components
import { DocumentsTab } from "./_components/documents/documents-tab";
import { AnalysisTab } from "./_components/analysis/analysis-tab";
import { SearchTab } from "./_components/search/search-tab";
import { VerificationTab } from "./_components/verification/verification-tab";

// Import existing components for dialogs
import { PdfViewerDialog } from "@/components/ui/pdf-viewer-dialog";
import { DocumentDetailDialog } from "./_components/documents/components/document-detail-dialog";
import { systemApi, documentApi } from "@/lib/api";
import { ChatBackground } from "@/components/ui/chat-background";

// Import types for persistent state
import type { Message, AttachedContent, FileAttachment } from "@/types/chat.types";
import { Document } from "@/types/document.types";
import { useDocumentDetail } from "@/hooks/use-document-detail";

// Types for persistent state across tabs
interface PersistentAnalysisState {
    selectedDocument: Document | null;
    imageZoom: number;
    imageRotation: number;
    imagePosition: { x: number; y: number };
    messages: Message[];
    input: string;
    attachments: FileAttachment[];
    attachedContent: AttachedContent[];
    selectedSegment: number;
    isChatStarted: boolean;
}

// Search tab state interface (from search-tab.tsx)
interface SearchMessage {
    id: string;
    sender: "user" | "ai";
    content: string;
    timestamp: number;
    plan?: any;
    references?: any[];
    isStreaming?: boolean;
}

interface PersistentSearchState {
    messages: SearchMessage[];
    input: string;
    currentPhase: "idle" | "planning" | "executing" | "responding";
    toolCollapsed: Record<string, boolean>;
    isChatStarted: boolean;
}

// Verification tab state interface
interface PersistentVerificationState {
    sourceDocuments: Document[];
    targetDocument: Document | null;
    messages: any[];
    verificationResults: any[];
    isVerifying: boolean;
    isChatStarted: boolean;
}

function WorkspacePageContent() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const selectedIndexId = searchParams.get('index_id') || '';
    const tabParam = searchParams.get('tab') as 'documents' | 'analysis' | 'search' | 'verification' | null;
    const { showInfo, AlertComponent } = useAlert();
    const { hasTabAccess } = useAuth();

    // Determine first available tab
    const getFirstAvailableTab = (): 'documents' | 'analysis' | 'search' | 'verification' => {
        const tabs: Array<'documents' | 'analysis' | 'search' | 'verification'> = ['documents', 'analysis', 'search', 'verification'];
        return tabs.find(tab => hasTabAccess(tab)) || 'search';
    };

    // Initialize tab from URL param or first available tab
    const initialTab = (tabParam && hasTabAccess(tabParam)) ? tabParam : getFirstAvailableTab();

    // Tab state
    const [activeTab, setActiveTab] = useState<'documents' | 'analysis' | 'search' | 'verification'>(initialTab);
    
    // PDF viewer state
    const [showPdfViewer, setShowPdfViewer] = useState(false);
    const [selectedDocumentForViewer, setSelectedDocumentForViewer] = useState<Document | null>(null);
    
    // Document detail dialog state using useDocumentDetail hook
    const documentDetailHook = useDocumentDetail(selectedIndexId);

    // Persistent state for Analysis tab (survives tab switches)
    const [persistentAnalysisState, setPersistentAnalysisState] = useState<PersistentAnalysisState>({
        selectedDocument: null,
        imageZoom: 1,
        imageRotation: 0,
        imagePosition: { x: 0, y: 0 },
        messages: [],
        input: "",
        attachments: [],
        attachedContent: [],
        selectedSegment: 0,
        isChatStarted: false,
    });

    // Persistent state for Search tab (survives tab switches)
    const [persistentSearchState, setPersistentSearchState] = useState<PersistentSearchState>({
        messages: [],
        input: "",
        currentPhase: "idle",
        toolCollapsed: {},
        isChatStarted: false,
    });

    // Persistent state for Verification tab (survives tab switches)
    const [persistentVerificationState, setPersistentVerificationState] = useState<PersistentVerificationState>({
        sourceDocuments: [],
        targetDocument: null,
        messages: [],
        verificationResults: [],
        isVerifying: false,
        isChatStarted: false,
    });

    // Update handlers for persistent state
    const updateAnalysisState = useCallback((updates: Partial<PersistentAnalysisState>) => {
        setPersistentAnalysisState(prev => ({ ...prev, ...updates }));
    }, []);

    const updateSearchState = useCallback((updates: Partial<PersistentSearchState>) => {
        setPersistentSearchState(prev => ({ ...prev, ...updates }));
    }, []);

    const updateVerificationState = useCallback((updates: Partial<PersistentVerificationState>) => {
        setPersistentVerificationState(prev => ({ ...prev, ...updates }));
    }, []);

    // Handle tab change - preserve document state, optionally clear chat
    const handleTabChange = useCallback((newTab: 'documents' | 'analysis' | 'search' | 'verification') => {
        console.log('🔄 Changing tab from', activeTab, 'to', newTab);
        
        // Option 1: Keep everything persistent (current implementation)
        // Option 2: Clear only chat messages when leaving analysis tab
        // if (activeTab === 'analysis' && newTab !== 'analysis') {
        //     console.log('🧹 Clearing chat messages only');
        //     setPersistentAnalysisState(prev => ({
        //         ...prev,
        //         messages: [],
        //         input: "",
        //         attachments: [],
        //         attachedContent: [],
        //     }));
        // }
        
        setActiveTab(newTab);
    }, [activeTab]);

    // Handle document selection (for chat attachment - future feature)
    const handleDocumentSelect = useCallback((fileName: string, documentId: string) => {
        console.log('Document selected for chat:', { fileName, documentId });
        // TODO: Implement chat attachment logic
    }, []);

    // Handle page attachment (for chat attachment - future feature)
    const handleAttachPage = useCallback((pageInfo: {
        document_id: string;
        page_index: number;
        page_number: number;
        file_name: string;
    }) => {
        console.log('Page attached to chat:', pageInfo);
        // TODO: Implement chat attachment logic
    }, []);

    // Handle analyze document - switch to analysis tab and load document
    const handleAnalyzeDocument = useCallback(async (document: any) => {
        try {
            console.log('🔄 Analyzing document:', document.file_name);
            
            // Reset chat state for new analysis
            await systemApi.reinitialize({
                force: true,
                reload_prompt: true,
                thread_id: `thread_analysis_${document.document_id}_${Date.now()}`
            });
            
            // Update persistent analysis state with the selected document
            updateAnalysisState({
                selectedDocument: document,
                selectedSegment: 0,
                imageZoom: 1,
                imageRotation: 0,
                imagePosition: { x: 0, y: 0 },
                messages: [],
                input: "",
                attachments: [],
                attachedContent: [],
                isChatStarted: false
            });
            
            // Switch to analysis tab
            handleTabChange('analysis');
            
            console.log('✅ Successfully switched to analysis tab with document:', document.file_name);
        } catch (error) {
            console.error('❌ Failed to analyze document:', error);
            alert('문서 분석 준비에 실패했습니다. 다시 시도해주세요.');
        }
    }, [updateAnalysisState, handleTabChange]);

    // Handle PDF opening
    const handlePdfClick = useCallback((document: any) => {
        try {
            console.log('📄 PDF button clicked - document data:', document);

            // Use file_uri or value field
            const fileUri = document.file_uri || document.value;
            if (!fileUri) {
                console.error('File URI is missing.');
                                return;
            }

            console.log('📄 PDF open attempt - file URI:', fileUri);
            
        // Create a minimal Document object for the PDF viewer
            const docForViewer: Document = {
                document_id: document.document_id || fileUri,
                upload_id: document.upload_id || fileUri,
                index_id: selectedIndexId,
                file_name: document.file_name || document.display_name || 'Unknown Document',
                file_type: 'pdf',
                file_size: 0,
                status: 'ready',
                processing_status: 'completed',
                processing_completed_at: null,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
                summary: '',
                description: '',
                download_url: fileUri,
                file_uri: fileUri,
                statistics: {
                    table_count: '0',
                    figure_count: '0', 
                    hyperlink_count: '0',
                    element_count: '0'
                },
                bda_metadata_uri: '',
                representation: { markdown: '' }
            };
            
            setSelectedDocumentForViewer(docForViewer);
            setShowPdfViewer(true);
        } catch (error) {
            console.error('PDF open failed:', error);
        }
    }, [selectedIndexId]);


    // Handle reference click from Search tab - open document detail dialog
    const handleReferenceClick = useCallback(async (reference: any) => {
        try {
            // Determine the target segment - prioritize segment_index over page_index
            const targetSegment = reference.segment_index ?? reference.page_index ?? 0;

            // Create a minimal document object from reference data
            const documentForDetail: Document = {
                document_id: reference.document_id || reference.id || 'unknown',
                upload_id: reference.document_id || reference.id || 'unknown',
                index_id: selectedIndexId,
                file_name: reference.display_name || reference.title || reference.file_name || 'Unknown Document',
                file_type: reference.file_type || 'document',
                file_size: 0,
                status: 'completed',
                processing_status: 'completed',
                processing_completed_at: null,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
                summary: '',
                description: reference.description || reference.value || '',
                download_url: reference.file_uri || reference.image_uri,
                file_uri: reference.file_uri || reference.image_uri,
                statistics: {
                    table_count: '0',
                    figure_count: '0',
                    hyperlink_count: '0',
                    element_count: '0'
                },
                bda_metadata_uri: '',
                representation: { markdown: '' },
            };

            // Open document detail dialog with the target segment (this will call fetchAnalysisData internally)
            documentDetailHook.viewDocument(documentForDetail, undefined, targetSegment);
        } catch (error) {
            console.error('❌ Failed to load document:', error);
            showInfo('Error', 'Failed to load document. Please try again.');
        }
    }, [selectedIndexId, showInfo, documentDetailHook]);

    // Handle browser back button - navigate to indexes page
    useEffect(() => {
        const handlePopState = (event: PopStateEvent) => {
            router.push('/indexes');
        };

        window.addEventListener('popstate', handlePopState);
        window.history.pushState(null, '', window.location.pathname + window.location.search);

        return () => {
            window.removeEventListener('popstate', handlePopState);
        };
    }, [router]);



    return (
        <>
            <div className="h-screen overflow-hidden bg-black text-white">
                    <SidebarProvider className="bg-black h-full" defaultOpen>
                        <AppSidebar />
                    <SidebarInset className="!m-0 !ml-0 !rounded-none !shadow-none bg-black relative h-full overflow-hidden">
                        <ChatBackground />
                        {/* Top header with sidebar toggle, back button, and tabs */}
                        <div className="absolute top-0 left-0 right-0 z-[50] flex items-center justify-between px-3 py-3 bg-black/50 backdrop-blur-sm border-b border-white/10">
                            <div className="flex items-center gap-2">
                                <SidebarTrigger className="hidden md:flex bg-black/40 border border-white/10 hover:bg-white/10" />
                                {/* Back to Indexes button */}
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => router.push('/indexes')}
                                    className="flex items-center gap-2 text-white/70 hover:text-white hover:bg-white/10 border border-white/10"
                                >
                                    <ArrowLeft className="h-4 w-4" />
                                    <span className="hidden sm:inline">Back to Indexes</span>
                                </Button>
                            </div>

                            {/* Tab Navigation */}
                            <div className="flex bg-black/20 rounded-xl border border-white/10 p-1 backdrop-blur-sm">
                                {/* Documents Tab */}
                                {hasTabAccess('documents') && (
                                    <button
                                        onClick={() => handleTabChange('documents')}
                                        className={`relative flex items-center gap-2 px-4 py-2 rounded-lg transition-all duration-300 group ${
                                            activeTab === 'documents'
                                                ? 'text-white'
                                                : 'text-white/60 hover:text-white/80'
                                        }`}
                                    >
                                        {/* Active background with animation */}
                                        {activeTab === 'documents' && (
                                            <motion.div
                                                layoutId="activeTab"
                                                className="absolute inset-0 bg-gradient-to-r from-cyan-500/20 to-sky-500/20 rounded-lg border border-cyan-400/30"
                                                initial={false}
                                                transition={{
                                                    type: "spring",
                                                    stiffness: 500,
                                                    damping: 30
                                                }}
                                            />
                                        )}

                                        <div className="relative flex items-center gap-2">
                                            <div className={`p-1 rounded transition-colors duration-300 ${
                                                activeTab === 'documents'
                                                    ? 'bg-cyan-500/20 text-cyan-300'
                                                    : 'bg-white/10 text-white/70 group-hover:bg-white/20'
                                            }`}>
                                                <FileText className="h-3 w-3" />
                                            </div>
                                            <span className="font-medium text-xs">Documents</span>
                                        </div>
                                    </button>
                                )}

                                {/* Analysis Tab */}
                                {hasTabAccess('analysis') && (
                                    <button
                                        onClick={() => handleTabChange('analysis')}
                                        className={`relative flex items-center gap-2 px-4 py-2 rounded-lg transition-all duration-300 group ${
                                            activeTab === 'analysis'
                                                ? 'text-white'
                                                : 'text-white/60 hover:text-white/80'
                                        }`}
                                    >
                                        {/* Active background with animation */}
                                        {activeTab === 'analysis' && (
                                            <motion.div
                                                layoutId="activeTab"
                                                className="absolute inset-0 bg-gradient-to-r from-purple-500/20 to-violet-500/20 rounded-lg border border-purple-400/30"
                                                initial={false}
                                                transition={{
                                                    type: "spring",
                                                    stiffness: 500,
                                                    damping: 30
                                                }}
                                            />
                                        )}

                                        <div className="relative flex items-center gap-2">
                                            <div className={`p-1 rounded transition-colors duration-300 ${
                                                activeTab === 'analysis'
                                                    ? 'bg-purple-500/20 text-purple-300'
                                                    : 'bg-white/10 text-white/70 group-hover:bg-white/20'
                                            }`}>
                                                <BarChart3 className="h-3 w-3" />
                                            </div>
                                            <span className="font-medium text-xs">Analysis</span>
                                        </div>
                                    </button>
                                )}

                                {/* Search Tab */}
                                {hasTabAccess('search') && (
                                    <button
                                        onClick={() => handleTabChange('search')}
                                        className={`relative flex items-center gap-2 px-4 py-2 rounded-lg transition-all duration-300 group ${
                                            activeTab === 'search'
                                                ? 'text-white'
                                                : 'text-white/60 hover:text-white/80'
                                        }`}
                                    >
                                        {/* Active background with animation */}
                                        {activeTab === 'search' && (
                                            <motion.div
                                                layoutId="activeTab"
                                                className="absolute inset-0 bg-gradient-to-r from-green-500/20 to-emerald-500/20 rounded-lg border border-green-400/30"
                                                initial={false}
                                                transition={{
                                                    type: "spring",
                                                    stiffness: 500,
                                                    damping: 30
                                                }}
                                            />
                                        )}

                                        <div className="relative flex items-center gap-2">
                                            <div className={`p-1 rounded transition-colors duration-300 ${
                                                activeTab === 'search'
                                                    ? 'bg-green-500/20 text-green-300'
                                                    : 'bg-white/10 text-white/70 group-hover:bg-white/20'
                                            }`}>
                                                <Search className="h-3 w-3" />
                                            </div>
                                            <span className="font-medium text-xs">Search</span>
                                        </div>
                                    </button>
                                )}

                                {/* Verification Tab */}
                                {hasTabAccess('verification') && (
                                    <button
                                        onClick={() => handleTabChange('verification')}
                                        className={`relative flex items-center gap-2 px-4 py-2 rounded-lg transition-all duration-300 group ${
                                            activeTab === 'verification'
                                                ? 'text-white'
                                                : 'text-white/60 hover:text-white/80'
                                        }`}
                                    >
                                        {/* Active background with animation */}
                                        {activeTab === 'verification' && (
                                            <motion.div
                                                layoutId="activeTab"
                                                className="absolute inset-0 bg-gradient-to-r from-indigo-500/20 to-purple-500/20 rounded-lg border border-indigo-400/30"
                                                initial={false}
                                                transition={{
                                                    type: "spring",
                                                    stiffness: 500,
                                                    damping: 30
                                                }}
                                            />
                                        )}

                                        <div className="relative flex items-center gap-2">
                                            <div className={`p-1 rounded transition-colors duration-300 ${
                                                activeTab === 'verification'
                                                    ? 'bg-indigo-500/20 text-indigo-300'
                                                    : 'bg-white/10 text-white/70 group-hover:bg-white/20'
                                            }`}>
                                                <CheckCircle className="h-3 w-3" />
                                            </div>
                                            <span className="font-medium text-xs">Verification</span>
                                        </div>
                                    </button>
                                )}

                            </div>

                            {selectedIndexId && (
                                <div className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-emerald-500/15 to-cyan-500/15 border border-emerald-400/20 px-3 py-1 text-xs backdrop-blur-sm">
                                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></div>
                                    <span className="text-emerald-300/70 uppercase tracking-wide">Index</span>
                                    <span className="font-semibold text-emerald-200">{selectedIndexId}</span>
                                </div>
                            )}
                        </div>

                        {/* Main Content with Tabs */}
                        <div className="absolute inset-0 top-16 flex flex-col overflow-hidden z-10">
                            <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as any)} className="h-full flex flex-col">
                                {/* Tab Content - Now takes full remaining height */}
                                <div className="flex-1 overflow-hidden">
                                    {!selectedIndexId ? (
                                        <div className="h-full flex items-center justify-center">
                                            <div className="text-center text-gray-400">
                                                <AlertCircle className="h-16 w-16 mx-auto mb-4 text-gray-500" />
                                                <h3 className="text-xl font-semibold mb-2">No Index Selected</h3>
                                                <p className="text-sm">Please select an index from the indexes page to continue.</p>
                                                <Button
                                                    onClick={() => router.push('/indexes')}
                                                    className="mt-4"
                                                    variant="outline"
                                                >
                                                    Go to Indexes
                                                </Button>
                                            </div>
                                        </div>
                                    ) : (
                                        <>
                                            {hasTabAccess('documents') && (
                                                <TabsContent value="documents" className="h-full m-0 border-0 rounded-none">
                                                    <DocumentsTab
                                                        indexId={selectedIndexId}
                                                        onSelectDocument={handleDocumentSelect}
                                                        onAttachToChat={handleAttachPage}
                                                        onAnalyzeDocument={handleAnalyzeDocument}
                                                    />
                                                </TabsContent>
                                            )}

                                            {hasTabAccess('analysis') && (
                                                <TabsContent value="analysis" className="h-full m-0 border-0 rounded-none">
                                                    <AnalysisTab
                                                        indexId={selectedIndexId}
                                                        persistentState={persistentAnalysisState}
                                                        onStateUpdate={updateAnalysisState}
                                                    />
                                                </TabsContent>
                                            )}

                                            {hasTabAccess('search') && (
                                                <TabsContent value="search" className="h-full m-0 border-0 rounded-none">
                                                    <SearchTab
                                                        indexId={selectedIndexId}
                                                        onOpenPdf={handlePdfClick}
                                                        onAttachToChat={handleAttachPage}
                                                        onReferenceClick={handleReferenceClick}
                                                        persistentState={persistentSearchState}
                                                        onStateUpdate={updateSearchState}
                                                    />
                                                </TabsContent>
                                            )}

                                            {hasTabAccess('verification') && (
                                                <TabsContent value="verification" className="h-full m-0 border-0 rounded-none">
                                                    <VerificationTab
                                                        indexId={selectedIndexId}
                                                        onOpenPdf={handlePdfClick}
                                                        onAttachToChat={handleAttachPage}
                                                        persistentState={persistentVerificationState}
                                                        onStateUpdate={updateVerificationState}
                                                    />
                                                </TabsContent>
                                            )}
                                        </>
                                    )}
                                </div>
                            </Tabs>
                        </div>
                    </SidebarInset>
                </SidebarProvider>
            </div>

            {/* PDF viewer dialog */}
            <PdfViewerDialog 
                isOpen={showPdfViewer} 
                onClose={() => {
                    setShowPdfViewer(false);
                    setSelectedDocumentForViewer(null);
                }}
                document={selectedDocumentForViewer}
                indexId={selectedIndexId}
            />

            {/* Document Detail Dialog */}
            <DocumentDetailDialog
                document={documentDetailHook.selectedDocument}
                open={documentDetailHook.showDetail}
                onOpenChange={(open) => {
                    if (!open) {
                        documentDetailHook.closeDetail();
                    }
                }}
                onClose={documentDetailHook.closeDetail}
                analysisData={documentDetailHook.analysisData}
                selectedSegment={documentDetailHook.selectedSegment}
                totalSegments={
                    documentDetailHook.analysisData.length > 0 
                        ? Math.max(...documentDetailHook.analysisData.map((item: any) => 
                            (typeof item.segment_index === 'number' ? item.segment_index : 
                             typeof item.page_index === 'number' ? item.page_index : 0)
                          ), 0) + 1
                        : (typeof documentDetailHook.selectedDocument?.total_pages === 'number' ? documentDetailHook.selectedDocument.total_pages : 1)
                }
                imageZoom={documentDetailHook.imageZoom}
                imagePosition={documentDetailHook.imagePosition}
                isDragging={documentDetailHook.isDragging}
                currentPageImageUrl={documentDetailHook.currentPageImageUrl}
                analysisLoading={documentDetailHook.analysisLoading}
                imageLoading={documentDetailHook.imageLoading}
                indexId={selectedIndexId}
                imageRotation={documentDetailHook.imageRotation}
                onSegmentChange={documentDetailHook.handleSegmentChange}
                onZoomIn={documentDetailHook.zoomIn}
                onZoomOut={documentDetailHook.zoomOut}
                onRotateLeft={documentDetailHook.rotateLeft}
                onRotateRight={documentDetailHook.rotateRight}
                onResetImage={documentDetailHook.resetImage}
                onMouseDown={documentDetailHook.handleMouseDown}
                onMouseMove={documentDetailHook.handleMouseMove}
                onMouseUp={documentDetailHook.handleMouseUp}
                onAnalysisPopup={documentDetailHook.handleAnalysisPopup}
                onShowPdfViewer={() => setShowPdfViewer(true)}
                segmentStartTimecodes={documentDetailHook.segmentStartTimecodes}
            />

            {/* Alert Component */}
            {AlertComponent}
        </>
    );
}

export default function WorkspacePage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen bg-black text-white flex items-center justify-center">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white mx-auto mb-4"></div>
                    <p className="text-white/70">Loading workspace...</p>
                </div>
            </div>
        }>
            <WorkspacePageContent />
        </Suspense>
    );
}
