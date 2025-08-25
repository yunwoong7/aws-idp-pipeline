'use client';

import { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useBranding } from '@/contexts/branding-context';
import { Upload, RotateCcw, Save, ImageIcon } from 'lucide-react';
import { brandingApi } from '@/lib/api';
import { useAlert } from '@/components/ui/alert';

export function BrandingSettings() {
  const { settings, refreshSettings, loading } = useBranding();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { showSuccess, showError, AlertComponent } = useAlert();

  const [formData, setFormData] = useState({
    companyName: settings.companyName,
    description: settings.description,
  });
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // When settings change, update the form data
  useEffect(() => {
    setFormData({
      companyName: settings.companyName,
      description: settings.description,
    });
    // Reset preview when settings change (e.g., after save/reset)
    setPreviewUrl(null);
  }, [settings.companyName, settings.description]);


  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      // Validate image file
      if (!file.type.startsWith('image/')) {
        showError('Invalid File Type', '이미지 파일만 업로드할 수 있습니다.');
        return;
      }

      // Validate file size (5MB limit)
      if (file.size > 5 * 1024 * 1024) {
        showError('File Too Large', '파일 크기는 5MB 이하여야 합니다.');
        return;
      }

      setSelectedFile(file);
      // Create a temporary preview URL for immediate display
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
    }
  };

  const handleSave = async () => {
    try {
      setIsSubmitting(true);

      const formDataToSend = new FormData();
      formDataToSend.append('companyName', formData.companyName);
      formDataToSend.append('description', formData.description);
      
      if (selectedFile) {
        formDataToSend.append('logoFile', selectedFile);
      }

      await brandingApi.updateSettings(formDataToSend);

      showSuccess('Settings Saved', 'Settings saved successfully.');
      
      // Refresh settings
      await refreshSettings();
      
      // Reset file selection
      setSelectedFile(null);
      // Bust preview and cached logo by updating previewUrl
      setPreviewUrl(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (error) {
      console.error('Error saving settings:', error);
      showError('Save Failed', error instanceof Error ? error.message : 'Error saving settings.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReset = async () => {
    try {
      setIsSubmitting(true);

      await brandingApi.resetSettings();

      showSuccess('Settings Reset', 'Settings reset successfully.');
      
      // Refresh settings and update form data
      await refreshSettings();
      
      // Reset file selection
      setSelectedFile(null);
      setPreviewUrl(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (error) {
      console.error('Error resetting settings:', error);
      showError('Reset Failed', error instanceof Error ? error.message : 'Error resetting settings.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleFileButtonClick = () => {
    fileInputRef.current?.click();
  };

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Branding Settings</CardTitle>
          <CardDescription>Customize your company logo, name, and description.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <div className="text-muted-foreground">Loading settings...</div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Branding Settings</CardTitle>
        <CardDescription>Customize your company logo, name, and description.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Current Logo Preview + Upload Button */}
        <div className="space-y-2">
          <Label>Current Logo</Label>
          <div className="flex items-center space-x-4">
            {(previewUrl || settings.logoUrl) ? (
              <img
                src={previewUrl || settings.logoUrl}
                alt="Current Logo"
                className="h-16 w-16 object-contain border rounded-lg"
                onError={(e) => {
                  const target = e.target as HTMLImageElement;
                  target.src = '/default_logo.png';
                }}
              />
            ) : (
              <div className="h-16 w-16 border rounded-lg flex items-center justify-center">
                <ImageIcon className="h-8 w-8 text-muted-foreground" />
              </div>
            )}

            {/* Upload controls near current logo */}
            <div className="flex items-center space-x-2">
              <button
                type="button"
                onClick={handleFileButtonClick}
                disabled={isSubmitting}
                className="py-2 inline-flex items-center justify-center whitespace-nowrap text-sm font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 bg-transparent border-slate-500/50 text-slate-400 hover:bg-slate-500/20 hover:border-slate-400 hover:text-slate-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Upload />
                Select File
              </button>
              {selectedFile && (
                <span className="text-sm text-muted-foreground">
                  {selectedFile.name}
                </span>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleFileSelect}
                className="hidden"
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">Upload PNG, JPG, or GIF files. Maximum 5MB</p>
        </div>

        {/* Company Name (allow up to 2 lines) */}
        <div className="space-y-2">
          <Label htmlFor="companyName">Company Name</Label>
          <Textarea
            id="companyName"
            value={formData.companyName}
            onChange={(e) => {
              const raw = e.target.value.replace(/\r\n/g, '\n');
              const limited = raw.split('\n').slice(0, 2).join('\n');
              handleInputChange('companyName', limited);
            }}
            placeholder="Enter your company name (max 2 lines)"
            rows={2}
          />
          <p className="text-xs text-muted-foreground">최대 2줄까지 입력 가능. 줄바꿈(Enter)으로 구분됩니다.</p>
        </div>

        {/* Description */}
        <div className="space-y-2">
          <Label htmlFor="description">Description</Label>
          <Textarea
            id="description"
            value={formData.description}
            onChange={(e) => handleInputChange('description', e.target.value)}
            placeholder="Enter your company or service description"
            rows={3}
          />
        </div>

        {/* (moved) Logo Upload controls are now near Current Logo */}

        {/* Buttons */}
        <div className="flex justify-start gap-3 pt-4">
          <button
            onClick={handleSave}
            disabled={isSubmitting}
            className="py-2 inline-flex items-center justify-center whitespace-nowrap text-sm font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 bg-transparent border-emerald-500/50 text-emerald-400 hover:bg-emerald-500/20 hover:border-emerald-400 hover:text-emerald-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-emerald-400"></div>
                Saving...
              </>
            ) : (
              <>
                <Save />
                Save
              </>
            )}
          </button>
          <button
            onClick={handleReset}
            disabled={isSubmitting}
            className="py-2 inline-flex items-center justify-center whitespace-nowrap text-sm font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 bg-transparent border-slate-500/50 text-slate-400 hover:bg-slate-500/20 hover:border-slate-400 hover:text-slate-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-slate-400"></div>
                  Restoring...
              </>
            ) : (
              <>
                <RotateCcw />
                Restore to Default
              </>
            )}
          </button>
        </div>
      </CardContent>
      
      {/* Alert Dialog Component */}
      {AlertComponent}
    </Card>
  );
}