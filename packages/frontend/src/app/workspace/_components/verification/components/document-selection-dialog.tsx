"use client";

import React, { useState, useEffect, useCallback } from "react";
import { X, FileText, Search, Loader2, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { documentApi } from "@/lib/api";
import { Document } from "@/types/document.types";
import { motion, AnimatePresence } from "framer-motion";

interface DocumentSelectionDialogProps {
  isOpen: boolean;
  onClose: () => void;
  indexId?: string;
  title: string;
  description: string;
  selectionMode: "single" | "multiple";
  selectedDocuments: Document[];
  disabledDocuments: Document[];
  onSelectionChange: (documents: Document[]) => void;
  onConfirm: (documents: Document[]) => void;
}

export function DocumentSelectionDialog({
  isOpen,
  onClose,
  indexId,
  title,
  description,
  selectionMode,
  selectedDocuments,
  disabledDocuments,
  onSelectionChange,
  onConfirm
}: DocumentSelectionDialogProps) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [localSelection, setLocalSelection] = useState<Document[]>(selectedDocuments);

  const loadDocuments = useCallback(async () => {
    if (!indexId) return;
    
    setLoading(true);
    try {
      const response = await documentApi.getDocuments(true, false, indexId);
      setDocuments(response.documents || []);
    } catch (error) {
      console.error("Failed to load documents:", error);
    } finally {
      setLoading(false);
    }
  }, [indexId]);

  // Load documents
  useEffect(() => {
    if (isOpen && indexId) {
      loadDocuments();
    }
  }, [isOpen, indexId, loadDocuments]);

  // Update local selection when external selection changes
  useEffect(() => {
    setLocalSelection(selectedDocuments);
  }, [selectedDocuments]);

  // Filter documents based on search
  const filteredDocuments = documents.filter(doc =>
    doc.file_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (doc.description && doc.description.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  // Check if document is disabled
  const isDocumentDisabled = (document: Document) => {
    return disabledDocuments.some(disabled => disabled.document_id === document.document_id);
  };

  // Check if document is selected
  const isDocumentSelected = (document: Document) => {
    return localSelection.some(selected => selected.document_id === document.document_id);
  };

  // Handle document selection
  const handleDocumentClick = (document: Document) => {
    if (isDocumentDisabled(document)) return;

    let newSelection: Document[];
    
    if (selectionMode === "single") {
      newSelection = isDocumentSelected(document) ? [] : [document];
    } else {
      if (isDocumentSelected(document)) {
        newSelection = localSelection.filter(doc => doc.document_id !== document.document_id);
      } else {
        newSelection = [...localSelection, document];
      }
    }

    setLocalSelection(newSelection);
    onSelectionChange(newSelection);
  };

  // Handle confirm
  const handleConfirm = () => {
    onConfirm(localSelection);
    onClose();
  };

  // Format file size
  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  // Format date
  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('ko-KR', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      
      {/* Dialog */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ duration: 0.2 }}
        className="relative w-full max-w-4xl max-h-[80vh] mx-4 backdrop-blur-xl border border-white/20 rounded-2xl shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <div>
            <h2 className="text-xl font-bold text-white">{title}</h2>
            <p className="text-white/60 text-sm mt-1">{description}</p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="text-white/70 hover:text-white hover:bg-white/10"
          >
            <X className="h-5 w-5" />
          </Button>
        </div>

        {/* Search */}
        <div className="p-4 border-b border-white/10">
          <div className="relative">
            <Search className="absolute left-3 top-3 h-4 w-4 text-white/40" />
            <Input
              placeholder="Search documents..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10 bg-white/5 border-white/20 text-white placeholder-white/40 focus:border-indigo-400/50"
            />
          </div>
          <div className="flex items-center justify-between mt-3">
            <span className="text-white/60 text-sm">
              {localSelection.length} selected{selectionMode === "multiple" ? ` / total ${filteredDocuments.length}` : ""}
            </span>
            {selectionMode === "multiple" && localSelection.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setLocalSelection([]);
                  onSelectionChange([]);
                }}
                className="text-white/60 hover:text-white hover:bg-white/10"
              >
                Clear all
              </Button>
            )}
          </div>
        </div>

        {/* Documents List */}
        <div className="flex-1 min-h-0">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="flex flex-col items-center gap-3">
                <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
                <p className="text-white/60">Loading documents...</p>
              </div>
            </div>
          ) : filteredDocuments.length === 0 ? (
            <div className="flex items-center justify-center h-64">
              <div className="flex flex-col items-center gap-3">
                <FileText className="h-12 w-12 text-white/40" />
                <p className="text-white/60">
                  {searchTerm ? "No documents found matching your search" : "No available documents"}
                </p>
              </div>
            </div>
          ) : (
            <ScrollArea className="h-[400px] p-4">
              <div className="space-y-2">
                {filteredDocuments.map((document) => {
                  const isSelected = isDocumentSelected(document);
                  const isDisabled = isDocumentDisabled(document);
                  
                  return (
                    <motion.div
                      key={document.document_id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className={`p-4 rounded-xl border transition-all duration-200 cursor-pointer group ${
                        isDisabled
                          ? 'bg-white/5 border-white/10 opacity-50 cursor-not-allowed'
                          : isSelected
                          ? 'bg-gradient-to-r from-indigo-500/20 to-purple-500/20 border-indigo-400/30 shadow-lg'
                          : 'bg-white/5 border-white/10 hover:bg-white/10 hover:border-white/20'
                      }`}
                      onClick={() => handleDocumentClick(document)}
                    >
                      <div className="flex items-center gap-3">
                        {/* Selection Indicator */}
                        <div className={`flex-shrink-0 w-5 h-5 rounded-full border-2 transition-colors flex items-center justify-center ${
                          isDisabled
                            ? 'border-white/20 bg-white/5'
                            : isSelected
                            ? 'border-indigo-400 bg-indigo-400'
                            : 'border-white/30 group-hover:border-indigo-400/50'
                        }`}>
                          {isSelected && <Check className="h-3 w-3 text-white" />}
                        </div>

                        {/* Document Icon */}
                        <div className={`flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center ${
                          document.file_type === 'pdf'
                            ? 'bg-red-500/20 text-red-400'
                            : 'bg-blue-500/20 text-blue-400'
                        }`}>
                          <FileText className="h-5 w-5" />
                        </div>

                        {/* Document Info */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <h3 className={`font-medium truncate max-w-[300px] ${
                              isDisabled ? 'text-white/40' : 'text-white'
                            }`} title={document.file_name}>
                              {document.file_name}
                            </h3>
                            <Badge className={`text-xs ${
                              document.file_type === 'pdf'
                                ? 'bg-red-500/20 text-red-400 border-red-500/30'
                                : 'bg-blue-500/20 text-blue-400 border-blue-500/30'
                            }`}>
                              {document.file_type.toUpperCase()}
                            </Badge>
                          </div>
                          <div className="flex items-center gap-4 mt-1 text-sm text-white/60">
                            <span>{formatFileSize(document.file_size)}</span>
                            <span>{formatDate(document.created_at)}</span>
                            <div className={`flex items-center gap-1`}>
                              <div className={`w-2 h-2 rounded-full ${
                                document.status === 'completed' ? 'bg-emerald-500' : 'bg-yellow-500'
                              }`} />
                              <span className="capitalize">{document.status}</span>
                            </div>
                          </div>
                          {document.description && (
                            <p className={`text-sm mt-2 truncate max-w-[400px] ${
                              isDisabled ? 'text-white/30' : 'text-white/60'
                            }`} title={document.description}>
                              {document.description}
                            </p>
                          )}
                        </div>

                        {isDisabled && (
                          <div className="flex-shrink-0 text-white/40 text-sm">
                            Already selected
                          </div>
                        )}
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </ScrollArea>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-white/10">
          <div className="text-sm text-white/60">
            {selectionMode === "single" 
              ? "Select one document" 
              : `Select multiple documents (${localSelection.length} selected)`
            }
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              onClick={onClose}
              className="text-white/70 hover:text-white hover:bg-white/10"
            >
              Cancel
            </Button>
            <Button
              onClick={handleConfirm}
              disabled={localSelection.length === 0}
              className="bg-gradient-to-r from-indigo-500 to-purple-500 hover:from-indigo-600 hover:to-purple-600 text-white font-medium"
            >
              Confirm Selection
            </Button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}