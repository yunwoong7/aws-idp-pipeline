// Chat related type definitions

export type MessageChunk = {
    type: "text" | "tool_use" | "tool_result" | "image" | "document";
    text?: string;
    name?: string;
    input?: string;
    image_data?: string;
    mime_type?: string;
    id?: string;
    index: number;
    filename?: string;
}

export type StreamData = {
    chunk: MessageChunk[];
    toolCalls: null | unknown;
    metadata: {
        langgraph_node?: string;  // ReactAgent metadata
        strands_node?: string;    // StrandsAgent metadata  
        langgraph_step?: number;  // ReactAgent metadata
        strands_step?: number;    // StrandsAgent metadata
        type: string;
        is_image?: boolean;
        image_data?: string;
        mime_type?: string;
        references?: Reference[];
    }
}

// Content Item Types
export interface TextContentItem {
    id: string;
    type: "text";
    content: string;
    timestamp: number;
    uniqueId?: string;
}

export interface ToolUseContentItem {
    id: string;
    type: "tool_use";
    name: string;
    input: string;
    timestamp: number;
    collapsed?: boolean;
    requiresApproval?: boolean;
    approved?: boolean;
    uniqueId?: string;
}

export interface ToolResultContentItem {
    id: string;
    type: "tool_result";
    result: string;
    timestamp: number;
    collapsed?: boolean;
    tool_use_id?: string;
    uniqueId?: string;
}

export interface ImageContentItem {
    id: string;
    type: "image";
    imageData: string;
    mimeType: string;
    timestamp: number;
    uniqueId?: string;
}

export interface DocumentContentItem {
    id: string;
    type: "document";
    filename: string;
    fileType: string;
    fileSize: number;
    timestamp: number;
    fileUrl?: string;
    fileId?: string;
    uniqueId?: string;
}

export type ContentItem = TextContentItem | ToolUseContentItem | ToolResultContentItem | ImageContentItem | DocumentContentItem;

// File and attachment types
export interface FileAttachment {
    id: string;
    file: File;
    type: string;
    previewUrl?: string;
    fileId?: string;
}

export interface ZoomedImageState {
    isOpen: boolean;
    imageData: string;
    mimeType: string;
}

// Document types
export interface Document {
    document_id: string;
    upload_id: string;
    file_name: string;
    file_type: string;
    file_size: number;
    status: string;
    processing_status: string;
    processing_completed_at: string | null;
    created_at: string;
    updated_at: string;
    summary: string;
    total_pages?: string;
    images_generated?: string;
    description: string;
    file_uri?: string;
}

// Reference types
export interface Reference {
    type: string;
    title: string;
    display_name: string;
    file_name: string;
    page_number: number;
    value: string;
    image_uri: string;
    file_uri: string;
    page_id: string;
    document_id: string;
    project_id: string;
    created_at: string;
    page_index?: number;
    tool_name?: string;
    seq?: number;
    metadata?: {
        [key: string]: any;
    };
    image_presigned_url: string;
    file_presigned_url: string;
}

// Search types
export interface SearchDocument {
    description: string;
    project_id: string;
    file_size: number;
    total_pages: number;
    document_id: string;
    file_name: string;
    status: string;
    file_type: string;
    created_at: string;
    summary: string;
    file_uri: string;
}

export interface SearchResult {
    page_id: string;
    page_index: number;
    project_id: string;
    document_id: string;
    image_uri: string;
    file_uri: string;
    highlight?: {
        [key: string]: string[];
    };
    image_presigned_url: string;
    file_presigned_url: string;
}

export interface SearchResponse {
    success: boolean;
    data: {
        query: string;
        search_type: string;
        total_results: number;
        returned_results: number;
        text_weight: number;
        vector_weight: number;
        results: SearchResult[];
    };
}

// Attached Content types for chat input
export interface DocumentAttachment {
    type: 'document';
    document_id: string;
    file_name: string;
}

export interface ImageAttachment {
    type: 'image';
    document_id: string;
    page_index: number;
    page_number: number;
    file_name: string;
}

export type AttachedContent = (DocumentAttachment | ImageAttachment) & {
    id: string;
};

// Strands Search Agent specific types
export interface StrandsSearchPhase {
    phase: 'routing' | 'execution' | 'response' | 'complete';
    startTime?: number;
    endTime?: number;
    status: 'pending' | 'active' | 'completed';
}

export interface StrandsSearchTask {
    title: string;
    tool_name: string;
    startTime?: number;
    endTime?: number;
    status: 'pending' | 'executing' | 'completed';
    result?: string;
}

// Message types
export interface Message {
    id: string;
    sender: "user" | "ai";
    content: string;
    contentItems: ContentItem[];
    steps?: any[];
    isStreaming?: boolean;
    references?: Reference[];
    attachedContent?: AttachedContent[];
    attachedFiles?: FileAttachment[];
    timestamp?: number;
    // Strands Search Agent specific fields
    strandsPhases?: StrandsSearchPhase[];
    strandsCurrentPhase?: string;
    strandsExecutingTasks?: StrandsSearchTask[];
    strandsResponseTokens?: string;
}

// Chat coordination types
export interface ChatPlan {
    requires_tool: boolean;
    direct_response?: string;
    overview?: string;
    tasks?: Array<{
        title: string;
        tool_name?: string;
        tool_args?: any;
        description?: string;
    }>;
}

export interface ChatCoordinator {
    decision: "direct_response" | "simple_search" | "plan_execute";
    reasoning: string;
}

// UI component prop types
export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
    containerClassName?: string;
    showRing?: boolean;
}

export interface UseAutoResizeTextareaProps {
    minHeight: number;
    maxHeight?: number;
}