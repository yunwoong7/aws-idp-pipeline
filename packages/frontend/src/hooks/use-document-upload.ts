import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { useToast } from "@/hooks/use-toast";
import { documentApi } from "@/lib/api";
import { UploadFile, Document, DuplicateFileDialog, ErrorDialog, ConfirmDialog, UploadToast } from "@/types/document.types";
import { UploadToastItem, ProcessingToastItem } from '@/components/ui/upload-toast';
import { getDropzoneAcceptObject } from '@/utils/file-utils';

// 파일 크기 제한 상수 (AWS API Gateway 실제 제한에 맞춰 조정)
const MAX_REGULAR_FILE_SIZE = 4 * 1024 * 1024; // 4MB (안전한 크기)
const MAX_LARGE_FILE_SIZE = 500 * 1024 * 1024; // 500MB (대용량 직접 업로드)
const MAX_REGULAR_FILE_SIZE_MB = 4;
const MAX_LARGE_FILE_SIZE_MB = 500;

export interface UseDocumentUploadReturn {
    // Upload files
    uploadFiles: UploadFile[];
    setUploadFiles: React.Dispatch<React.SetStateAction<UploadFile[]>>;
    isUploading: boolean;
    hasActiveUploads: boolean;
    
    // Dropzone
    getRootProps: ReturnType<typeof useDropzone>['getRootProps'];
    getInputProps: ReturnType<typeof useDropzone>['getInputProps'];
    isDragActive: boolean;
    onDrop: (acceptedFiles: File[]) => void;
    
    // Upload actions
    startUpload: () => Promise<void>;
    removeFile: (fileId: string) => void;
    handleDuplicateFile: (file: UploadFile) => void;
    
    // Dialog states
    duplicateFileDialog: DuplicateFileDialog;
    errorDialog: ErrorDialog;
    confirmDialog: ConfirmDialog;
    uploadToasts: UploadToast[];
    
    // Dialog handlers
    handleDuplicateFileDialog: (dialog: DuplicateFileDialog) => void;
    setErrorDialog: (dialog: ErrorDialog) => void;
    setConfirmDialog: (dialog: ConfirmDialog) => void;
    removeUploadToast: (id: string) => void;
    
    // Complex toast system like backup file
    uploadToastItems: UploadToastItem[];
    processingToastItems: ProcessingToastItem[];
    removeToastItem: (id: string) => void;
    clearAllToastItems: () => void;
    removeProcessingToastItem: (id: string) => void;
    clearAllProcessingToastItems: () => void;
    
    // Utility functions
    formatFileSize: (bytes: number) => string;
    
    // Dialog handlers
    handleReplaceFile: () => void;
    handleKeepBothFiles: () => void;
    handleCancelUpload: () => void;
}

export const useDocumentUpload = (options: {
    documents?: Document[];
    onUploadComplete?: () => void;
    indexId: string;
}): UseDocumentUploadReturn => {
    const { toast } = useToast();
    const { documents = [], onUploadComplete, indexId } = options;
    
    // Upload files state
    const [uploadFiles, setUploadFiles] = useState<UploadFile[]>([]);
    const [isUploading, setIsUploading] = useState(false);
    
    // Complex toast system from backup file
    const [uploadToastItems, setUploadToastItems] = useState<UploadToastItem[]>([]);
    const [processingToastItems, setProcessingToastItems] = useState<ProcessingToastItem[]>([]);
    
    // Dialog states
    const [duplicateFileDialog, setDuplicateFileDialog] = useState<DuplicateFileDialog>({
        isOpen: false,
        file: null,
        conflictingFileName: ''
    });
    
    const [errorDialog, setErrorDialog] = useState<ErrorDialog>({
        isOpen: false,
        title: '',
        message: '',
        error: undefined
    });
    
    const [confirmDialog, setConfirmDialog] = useState<ConfirmDialog>({
        isOpen: false,
        title: '',
        message: '',
        onConfirm: () => {},
        onCancel: () => {}
    });
    const [uploadToasts, setUploadToasts] = useState<UploadToast[]>([]);

    // 중복 파일명 체크 - 백업 파일에서 가져온 로직
    const checkForDuplicateFileName = useCallback((fileName: string): boolean => {
        const existingNames = documents.map(doc => doc.file_name);
        return existingNames.includes(fileName);
    }, [documents]);

    // 파일 드롭 처리 - 통일된 Presigned URL 업로드 방식
    const onDrop = useCallback((acceptedFiles: File[]) => {
        // 파일 크기 제한 체크 (500MB까지 지원)
        const validFiles = acceptedFiles.filter(file => file.size <= MAX_LARGE_FILE_SIZE);
        const oversizedFiles = acceptedFiles.filter(file => file.size > MAX_LARGE_FILE_SIZE);
        
        // 크기 초과 파일 안내
        if (oversizedFiles.length > 0) {
            const fileNames = oversizedFiles.map(f => f.name).join(', ');
            toast({
                title: "File Too Large",
                description: `${oversizedFiles.length} file(s) exceed the ${MAX_LARGE_FILE_SIZE_MB}MB limit: ${fileNames}. Please use smaller files.`,
                variant: "destructive",
            });
        }
        
        if (validFiles.length === 0) return;
        
        const newFiles: UploadFile[] = validFiles.map(file => {
            const isDuplicate = checkForDuplicateFileName(file.name);
            
            return {
                id: `${file.name}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
                name: file.name,
                type: file.type,
                size: file.size,
                status: isDuplicate ? 'conflict' as const : 'pending' as const,
                progress: 0,
                file: file,
                isLargeFile: false // 모든 파일이 통일된 방식으로 처리되므로 불필요
            };
        });

        setUploadFiles(prev => [...prev, ...newFiles]);

        // 중복 파일이 있으면 첫 번째 중복 파일에 대해 다이얼로그 표시
        const firstConflict = newFiles.find(f => f.status === 'conflict');
        if (firstConflict) {
            setDuplicateFileDialog({
                isOpen: true,
                file: firstConflict,
                conflictingFileName: firstConflict.name
            });
        }
    }, [checkForDuplicateFileName, toast]);

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        accept: getDropzoneAcceptObject(),
        maxSize: MAX_LARGE_FILE_SIZE, // 500MB 대용량 파일 지원
        disabled: isUploading
    });

    // 백엔드를 통한 직접 업로드 (CORS 문제 해결)
    const uploadFileViaBackend = async (file: UploadFile, toastId?: string) => {
        try {
            // 업로드 시작
            setUploadFiles(prev => prev.map(f => 
                f.id === file.id 
                    ? { ...f, status: 'uploading' as const, progress: 5 }
                    : f
            ));

            if (!indexId) {
                throw new Error('indexId is required for file upload');
            }
            
            // 파일 크기에 따라 적절한 업로드 방법 선택
            const isLargeFile = file.size > 50 * 1024 * 1024; // 50MB 이상은 청킹 업로드
            
            let uploadResult;
            if (isLargeFile) {
                // 대용량 파일: 청킹 업로드 (진행률 지원)
                uploadResult = await documentApi.uploadLargeDocumentViaBackend(
                    file.file,
                    indexId,
                    (progress) => {
                        setUploadFiles(prev => prev.map(f => 
                            f.id === file.id 
                                ? { ...f, progress: 5 + (progress * 0.9) } // 5-95%
                                : f
                        ));

                        if (toastId) {
                            setUploadToastItems(prev => prev.map(item => 
                                item.id === toastId 
                                    ? { ...item, progress: 5 + (progress * 0.9) }
                                    : item
                            ));
                        }
                    }
                );
            } else {
                // 일반 파일: 단순 업로드
                uploadResult = await documentApi.uploadDocumentViaBackend(
                    file.file,
                    indexId,
                    ''
                );

                // 진행률 시뮬레이션 (실제 진행률 추적이 없는 경우)
                setUploadFiles(prev => prev.map(f => 
                    f.id === file.id 
                        ? { ...f, progress: 90 }
                        : f
                ));

                if (toastId) {
                    setUploadToastItems(prev => prev.map(item => 
                        item.id === toastId 
                            ? { ...item, progress: 90 }
                            : item
                    ));
                }
            }

            // document_id 저장
            setUploadFiles(prev => prev.map(f => 
                f.id === file.id 
                    ? { ...f, documentId: uploadResult.document_id, progress: 100 }
                    : f
            ));

            // 성공 처리
            setUploadFiles(prev => prev.map(f => 
                f.id === file.id 
                    ? { ...f, status: 'success' as const, progress: 100 }
                    : f
            ));

            // 토스트 아이템 성공 상태로 업데이트
            if (toastId) {
                setUploadToastItems(prev => prev.map(item => 
                    item.id === toastId 
                        ? { ...item, status: 'SUCCESS', progress: 100 }
                        : item
                ));
            }

            return uploadResult;

        } catch (error) {
            
            let errorMessage = 'File upload failed';
            if (error instanceof Error) {
                errorMessage = error.message;
            }
            
            // 실패 처리
            setUploadFiles(prev => prev.map(f => 
                f.id === file.id 
                    ? { ...f, status: 'error' as const, error: errorMessage }
                    : f
            ));

            if (toastId) {
                setUploadToastItems(prev => prev.map(item => 
                    item.id === toastId 
                        ? { ...item, status: 'ERROR', error: errorMessage }
                        : item
                ));
            }

            throw error;
        }
    };


    // 업로드 시작 - 통일된 Presigned URL 방식
    const startUpload = useCallback(async () => {
        const filesToUpload = uploadFiles.filter(f => f.status === 'pending');
        
        if (filesToUpload.length === 0) {
            toast({
                title: 'No files to upload',
                description: 'Please add files to upload.',
                variant: 'default'
            });
            return;
        }

        setIsUploading(true);

        try {
            // 모든 파일에 대해 백엔드 직접 업로드 방식 사용 (CORS 문제 해결)
            const uploadPromises = filesToUpload.map(file => {
                const toastId = `upload-${file.id}`;
                
                // 토스트 아이템 생성
                const uploadToastItem: UploadToastItem = {
                    id: toastId,
                    fileName: file.name,
                    fileType: file.type,
                    status: 'UPLOADING',
                    progress: 0
                };

                setUploadToastItems(prev => [...prev, uploadToastItem]);
                
                return uploadFileViaBackend(file, toastId);
            });
            
            const results = await Promise.all(uploadPromises);
            
            // 업로드 완료 후 성공한 파일들 제거
            setUploadFiles(prev => prev.filter(f => f.status !== 'success'));
            
            // 처리 토스트 아이템들 추가
            results.forEach((result, index) => {
                if (result && result.document_id) {
                    const file = filesToUpload[index];
                    const processingToastItem: ProcessingToastItem = {
                        id: `processing-${result.document_id}`,
                        documentId: result.document_id,
                        fileName: file.name,
                        status: 'PROCESSING',
                        currentStep: 'Document Processing',
                        stepLabel: 'Processing document...',
                        progress: 0,
                        totalSteps: 5,
                        currentStepIndex: 0
                    };

                    setProcessingToastItems(prev => [...prev, processingToastItem]);
                }
            });
            
            if (onUploadComplete) {
                onUploadComplete();
            }
        } catch (error) {
            
            toast({
                title: 'Upload Error',
                description: 'Some files failed to upload. Please try again.',
                variant: 'destructive'
            });
        } finally {
            setIsUploading(false);
        }
    }, [uploadFiles, onUploadComplete, toast]);

    // 파일 제거
    const removeFile = useCallback((fileId: string) => {
        setUploadFiles(prev => prev.filter(f => f.id !== fileId));
    }, []);

    // Dialog handler functions
    const handleDuplicateFileDialog = useCallback((dialog: DuplicateFileDialog) => {
        setDuplicateFileDialog(dialog);
    }, []);

    const removeUploadToast = useCallback((id: string) => {
        setUploadToasts(prev => prev.filter(toast => toast.id !== id));
    }, []);

    // 중복 파일 처리
    const handleDuplicateFile = useCallback((file: UploadFile) => {
        setDuplicateFileDialog({
            isOpen: true,
            file,
            conflictingFileName: file.name
        });
    }, []);

    // 중복 파일 대화상자 처리
    const handleReplaceFile = useCallback(() => {
        if (!duplicateFileDialog.file) return;
        
        // 파일 상태를 pending으로 변경하여 업로드 진행
        setUploadFiles(prev => prev.map(f => 
            f.id === duplicateFileDialog.file!.id 
                ? { ...f, status: 'pending' as const }
                : f
        ));
        
        setDuplicateFileDialog({
            isOpen: false,
            file: null,
            conflictingFileName: ''
        });
    }, [duplicateFileDialog]);

    const handleKeepBothFiles = useCallback(() => {
        if (!duplicateFileDialog.file) return;
        
        // 파일 상태를 pending으로 변경하여 업로드 진행
        setUploadFiles(prev => prev.map(f => 
            f.id === duplicateFileDialog.file!.id 
                ? { ...f, status: 'pending' as const }
                : f
        ));
        
        setDuplicateFileDialog({
            isOpen: false,
            file: null,
            conflictingFileName: ''
        });
    }, [duplicateFileDialog]);

    const handleCancelUpload = useCallback(() => {
        if (!duplicateFileDialog.file) return;
        
        // 파일 제거
        setUploadFiles(prev => prev.filter(f => f.id !== duplicateFileDialog.file!.id));
        
        setDuplicateFileDialog({
            isOpen: false,
            file: null,
            conflictingFileName: ''
        });
    }, [duplicateFileDialog]);

    // 토스트 관리 함수들
    const removeToastItem = useCallback((id: string) => {
        setUploadToastItems(prev => prev.filter(item => item.id !== id));
    }, []);

    const clearAllToastItems = useCallback(() => {
        setUploadToastItems([]);
    }, []);

    const removeProcessingToastItem = useCallback((id: string) => {
        setProcessingToastItems(prev => prev.filter(item => item.id !== id));
    }, []);

    const clearAllProcessingToastItems = useCallback(() => {
        setProcessingToastItems([]);
    }, []);

    // 파일 크기 포맷팅
    const formatFileSize = useCallback((bytes: number) => {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }, []);

    // 진행 중인 업로드가 있는지 확인
    const hasActiveUploads = isUploading || uploadToastItems.length > 0 || processingToastItems.length > 0;

    return {
        // Upload files
        uploadFiles,
        setUploadFiles,
        isUploading,
        hasActiveUploads,
        
        // Dropzone
        getRootProps,
        getInputProps,
        isDragActive,
        onDrop,
        
        // Upload actions
        startUpload,
        removeFile,
        handleDuplicateFile,
        
        // Complex toast system
        uploadToastItems,
        processingToastItems,
        removeToastItem,
        clearAllToastItems,
        removeProcessingToastItem,
        clearAllProcessingToastItems,
        
        // Dialog states
        duplicateFileDialog,
        errorDialog,
        confirmDialog,
        uploadToasts,
        
        // Dialog handlers
        handleDuplicateFileDialog,
        setErrorDialog,
        setConfirmDialog,
        removeUploadToast,
        
        // Utility functions
        formatFileSize,
        
        // Dialog handlers
        handleReplaceFile,
        handleKeepBothFiles,
        handleCancelUpload
    };
}; 