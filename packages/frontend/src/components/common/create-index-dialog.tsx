"use client";

import React, { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { PlusCircle, CheckCircle, Loader2 } from "lucide-react";
import { indicesApi } from "@/lib/api";
import { useAlert } from "@/components/ui/alert";

export interface CreateIndexDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (index: any) => void;
}

interface CreateIndexForm {
  index_id: string;
  description: string;
  owner_name: string;
}

export function CreateIndexDialog({ isOpen, onClose, onSuccess }: CreateIndexDialogProps) {
  const [creating, setCreating] = useState(false);
  const [createForm, setCreateForm] = useState<CreateIndexForm>({
    index_id: "",
    description: "",
    owner_name: ""
  });
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string>("");
  const { showWarning, AlertComponent } = useAlert();

  const handleClose = () => {
    setCreateForm({ index_id: "", description: "", owner_name: "" });
    setSuccess(false);
    setError("");
    setCreating(false);
    onClose();
  };

  const handleCreateIndex = async () => {
    setError("");
    if (!createForm.index_id || !createForm.owner_name) return;
    setCreating(true);
    
    try {
      const created = await indicesApi.create({
        index_id: createForm.index_id,
        description: createForm.description,
        owner_name: createForm.owner_name,
        owner_id: '00001',
      });
      
      setSuccess(true);
      
      setTimeout(() => {
        onSuccess(created);
        handleClose();
      }, 1600);
    } catch (e: any) {
      console.error('Create index failed', e);
      setError(e?.message || 'Failed to create index');
    } finally {
      setCreating(false);
    }
  };

  return (
    <>
      {AlertComponent}
      <Dialog open={isOpen} onOpenChange={handleClose}>
        <DialogContent className="!w-[50vw] !max-w-none !sm:max-w-none max-h-[75vh] p-0 border-0 bg-transparent overflow-hidden">
          <DialogHeader className="sr-only">
            <DialogTitle>Create Index</DialogTitle>
            <DialogDescription>Create a new index (workspace)</DialogDescription>
          </DialogHeader>
          <div className="flex h-[70vh]">
          {/* Left panel (visual tone) */}
          <div className="w-1/3 bg-gradient-to-br from-violet-900/95 via-purple-900/95 to-indigo-900/95 backdrop-blur-xl p-8 flex flex-col justify-center relative overflow-hidden">
            <div className="absolute inset-0 opacity-10">
              <div className="absolute top-10 left-10 w-32 h-32 border border-violet-400/30 rounded-full"></div>
              <div className="absolute bottom-20 right-10 w-24 h-24 border border-purple-400/30 rounded-full"></div>
              <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-40 h-40 border border-indigo-400/20 rounded-full"></div>
            </div>
            <div className="relative z-10 space-y-4">
              <div className="w-16 h-16 rounded-2xl bg-violet-500/20 flex items-center justify-center mb-6 backdrop-blur-sm border border-violet-400/20">
                <PlusCircle className="h-8 w-8 text-violet-400" />
              </div>
              <h2 className="text-3xl font-bold text-white mb-3">Create New Index</h2>
              <p className="text-violet-200 text-lg leading-relaxed">Define your workspace to organize documents and media.</p>
            </div>
          </div>

          {/* Right panel (form) */}
          <div className="flex-1 bg-gradient-to-br from-gray-900/90 via-slate-900/90 to-gray-800/90 backdrop-blur-xl p-8 overflow-y-auto">
            <div className="max-w-md mx-auto h-full">
              {success ? (
                <div className="flex flex-col items-center justify-center h-full">
                  <div className="text-center space-y-6">
                    <div className="relative">
                      <div className="rounded-full bg-green-500/20 p-6 animate-bounce border border-green-400/30">
                        <CheckCircle className="h-16 w-16 text-green-400 animate-pulse" />
                      </div>
                      <div className="absolute -inset-4 rounded-full border-2 border-green-400/20 animate-ping"></div>
                    </div>
                    <div className="space-y-3">
                      <h3 className="text-2xl font-bold text-white">Index Created! 🎉</h3>
                      <p className="text-green-200 text-lg">Your workspace is ready</p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="space-y-8 py-8">
                  <div className="text-center">
                    <h3 className="text-2xl font-bold text-white mb-2">Index Details</h3>
                    <p className="text-gray-400">Create an index to start uploading files</p>
                  </div>
                  <div className="space-y-6">
                    <div className="space-y-3">
                      <Label htmlFor="index_id" className="text-gray-200 text-sm font-medium">Index ID *</Label>
                      <Input
                        id="index_id"
                        value={createForm.index_id}
                        onChange={(e) => {
                          const value = e.target.value;

                          // Check for uppercase letters
                          if (/[A-Z]/.test(value)) {
                            showWarning(
                              "Invalid Index Name",
                              "Index names must be lowercase only. Please use lowercase letters."
                            );
                            // Convert to lowercase automatically
                            setCreateForm({ ...createForm, index_id: value.toLowerCase() });
                            return;
                          }

                          // Check for invalid characters (spaces and special characters)
                          // Only allow: lowercase letters, numbers, hyphens, underscores
                          if (/[^a-z0-9_-]/.test(value)) {
                            showWarning(
                              "Invalid Characters",
                              "Index names can only contain lowercase letters, numbers, hyphens (-), and underscores (_). Spaces and special characters are not allowed."
                            );
                            // Remove invalid characters
                            const sanitized = value.replace(/[^a-z0-9_-]/g, '');
                            setCreateForm({ ...createForm, index_id: sanitized });
                            return;
                          }

                          setCreateForm({ ...createForm, index_id: value });
                        }}
                        placeholder="e.g. my-first-index"
                        className="bg-white/5 border-gray-600 text-white placeholder:text-gray-400 focus:border-violet-400 focus:ring-violet-400/20 h-12 rounded-xl"
                      />
                      <p className="text-xs text-white/50">- lowercase letters, numbers, hyphens (-), underscores (_) only<br />- no spaces or special characters; cannot start with '_' or '-'</p>
                    </div>
                    <div className="space-y-3">
                      <Label htmlFor="description" className="text-gray-200 text-sm font-medium">Description</Label>
                      <Input 
                        id="description" 
                        value={createForm.description} 
                        onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })} 
                        placeholder="Describe this index" 
                        className="bg-white/5 border-gray-600 text-white placeholder:text-gray-400 focus:border-violet-400 focus:ring-violet-400/20 h-12 rounded-xl" 
                      />
                    </div>
                    <div className="space-y-3">
                      <Label htmlFor="owner" className="text-gray-200 text-sm font-medium">Owner *</Label>
                      <Input 
                        id="owner" 
                        value={createForm.owner_name} 
                        onChange={(e) => setCreateForm({ ...createForm, owner_name: e.target.value })} 
                        placeholder="Your name" 
                        className="bg-white/5 border-gray-600 text-white placeholder:text-gray-400 focus:border-violet-400 focus:ring-violet-400/20 h-12 rounded-xl" 
                      />
                    </div>
                    {error && (<p className="text-xs text-amber-300/90">{error}</p>)}
                  </div>
                  <div className="flex gap-3 pt-6">
                    <Button 
                      variant="outline" 
                      onClick={handleClose} 
                      className="flex-1 border-gray-600 text-gray-300 bg-gray-800/50 hover:bg-gray-700/70 hover:border-gray-500 h-12 rounded-xl"
                    >
                      Cancel
                    </Button>
                    <Button 
                      onClick={handleCreateIndex} 
                      disabled={!createForm.index_id || !createForm.owner_name || creating} 
                      className="flex-1 bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-700 hover:to-purple-700 text-white border-0 h-12 rounded-xl"
                    >
                      {creating ? (
                        <span className="flex items-center gap-2">
                          <Loader2 className="h-4 w-4 animate-spin" /> Creating...
                        </span>
                      ) : (
                        <span className="flex items-center gap-2">
                          <PlusCircle className="h-4 w-4" /> Create Index
                        </span>
                      )}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
    </>
  );
}