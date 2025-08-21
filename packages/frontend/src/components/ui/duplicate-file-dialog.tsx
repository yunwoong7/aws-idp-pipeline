import React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { UploadFile } from "@/types/document.types";

interface DuplicateFileDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  file: UploadFile | null;
  conflictingFileName: string;
  onKeepBoth: () => void;
  onReplace: () => void;
  onSkip: () => void;
}

export function DuplicateFileDialog({
  open,
  onOpenChange,
  file,
  conflictingFileName,
  onKeepBoth,
  onReplace,
  onSkip,
}: DuplicateFileDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Duplicate File Detected</DialogTitle>
          <DialogDescription>
            A file named "{conflictingFileName}" already exists. What would you like to do?
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onSkip}>
            Skip
          </Button>
          <Button variant="outline" onClick={onReplace}>
            Replace
          </Button>
          <Button onClick={onKeepBoth}>
            Keep Both
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
} 