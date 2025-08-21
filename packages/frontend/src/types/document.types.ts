// Document related common types

export interface Document {
    document_id: string;
    upload_id: string;
    index_id: string;
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
    description?: string;
    download_url?: string;
    file_uri?: string;
    statistics: {
        table_count: string;
        figure_count: string;
        hyperlink_count: string;
        element_count: string;
    };
    bda_metadata_uri: string;
    representation: {
        markdown: string;
    };
    page_images?: PageImage[];
    analysis_stats?: {
        total_pages: number;
        completed_pages: number;
    };
}

export interface PageImage {
    page_number: string | number;
    page_index?: string | number;
    image_url?: string;
    image_uri?: string;
    file_uri?: string | null;
    image_file_uri?: string;
    image_s3_path?: string;
    page_status?: string;
    analysis_completed_at?: string;
    analysis_steps_count?: string | number;
}

export interface AnalysisDocument {
    opensearch_doc_id: string;
    score: number | null;
    index_id: string;
    document_id: string;
    page_number?: number;
    page_index?: number | null;
    segment_id?: string;
    segment_index?: number | null;
    tool_name: string;
    content: string;
    analysis_query: string;
    vector_dimensions: number;
    file_uri?: string;
    file_path?: string;
    image_file_uri?: string;
    image_path?: string;
    execution_time: number | null;
    created_at: string;
    data_structure: string;
}

export interface UploadFile {
    id: string;
    name: string;
    type: string;
    size: number;
    status: 'pending' | 'uploading' | 'success' | 'error' | 'conflict';
    progress: number;
    error?: string;
    file: File;
    originalName?: string;
    isLargeFile?: boolean;
    documentId?: string;
}

export interface DuplicateFileDialog {
    file: UploadFile | null;
    conflictingFileName: string;
    isOpen: boolean;
}

export interface ErrorDialog {
    isOpen: boolean;
    title: string;
    message: string;
    error?: Error;
}

export interface ConfirmDialog {
    isOpen: boolean;
    title: string;
    message: string;
    onConfirm: () => void;
    onCancel: () => void;
}

export interface UploadToast {
    id: string;
    type: 'upload' | 'processing';
    title: string;
    message: string;
    progress?: number;
    status: 'pending' | 'processing' | 'success' | 'error';
    timestamp: number;
    documentId?: string;
}

// Complex toast types for backup files
export interface UploadToastItem {
    id: string;
    fileName: string;
    fileType: string;
    status: "UPLOADING" | "SUCCESS" | "ERROR";
    progress: number;
    error?: string;
}

export interface ProcessingToastItem {
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

// Type guard functions
export const isDocument = (obj: any): obj is Document => {
    return obj && typeof obj.document_id === 'string' && typeof obj.file_name === 'string';
};

export const isAnalysisDocument = (obj: any): obj is AnalysisDocument => {
    return obj && typeof obj.opensearch_doc_id === 'string' && typeof obj.tool_name === 'string';
};

export const isUploadFile = (obj: any): obj is UploadFile => {
    return obj && typeof obj.id === 'string' && obj.file instanceof File;
}; 