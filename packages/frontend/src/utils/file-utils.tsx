import React from 'react';
import { FileText, Image as ImageIcon, Video, Music, File } from 'lucide-react';

export interface FileTypeInfo {
  category: string;
  icon: React.ReactNode;
  color: string;
}

// File type mappings
const FILE_TYPE_MAPPINGS = {
  // Videos
  video: {
    extensions: ['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm', '3gp'],
    category: 'Video',
    color: 'text-red-400'
  },
  // Audio
  audio: {
    extensions: ['mp3', 'wav', 'flac', 'm4a', 'aac', 'ogg', 'wma', 'aiff'],
    category: 'Audio', 
    color: 'text-green-400'
  },
  // Images
  image: {
    extensions: ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'tif', 'webp'],
    category: 'Image',
    color: 'text-blue-400'
  },
  // Documents
  document: {
    extensions: ['pdf', 'doc', 'docx', 'txt', 'rtf', 'odt', 'dwg', 'dxf'],
    category: 'Document',
    color: 'text-cyan-400'
  }
};

/**
 * Get file extension from filename
 */
export const getFileExtension = (fileName: string): string => {
  if (!fileName || typeof fileName !== 'string') {
    return '';
  }
  return fileName.toLowerCase().split('.').pop() || '';
};

/**
 * Determine file type category based on extension
 */
export const getFileTypeInfo = (fileName: string): FileTypeInfo => {
  const extension = getFileExtension(fileName);
  
  for (const [type, config] of Object.entries(FILE_TYPE_MAPPINGS)) {
    if (config.extensions.includes(extension)) {
      return {
        category: config.category,
        icon: getIconByType(type, config.color),
        color: config.color
      };
    }
  }
  
  // Default fallback
  return {
    category: 'File',
    icon: <File className="text-slate-400" />,
    color: 'text-slate-400'
  };
};

/**
 * Get icon component by file type
 */
const getIconByType = (type: string, colorClass: string): React.ReactNode => {
  const iconProps = { className: colorClass };
  
  switch (type) {
    case 'video':
      return <Video {...iconProps} />;
    case 'audio':
      return <Music {...iconProps} />;
    case 'image':
      return <ImageIcon {...iconProps} />;
    case 'document':
      return <FileText {...iconProps} />;
    default:
      return <File {...iconProps} />;
  }
};

/**
 * Get file icon with specific size classes
 */
export const getFileIcon = (fileName: string, sizeClass: string = 'h-4 w-4'): React.ReactNode => {
  if (!fileName || typeof fileName !== 'string') {
    // Return default file icon for invalid filenames
    return React.createElement(File, {
      className: `${sizeClass} text-gray-400 flex-shrink-0`
    });
  }
  const typeInfo = getFileTypeInfo(fileName);
  return React.cloneElement(typeInfo.icon as React.ReactElement, {
    className: `${sizeClass} ${typeInfo.color} flex-shrink-0`
  } as any);
};

/**
 * Get file type category name
 */
export const getFileTypeCategory = (fileName: string): string => {
  if (!fileName || typeof fileName !== 'string') {
    return 'Unknown';
  }
  return getFileTypeInfo(fileName).category;
};

/**
 * Check if file type is supported by BDA
 */
export const isBDASupported = (fileName: string): boolean => {
  if (!fileName || typeof fileName !== 'string') {
    return false;
  }
  const extension = getFileExtension(fileName);
  const bdaSupportedExtensions = ['pdf', 'dwg', 'dxf', 'jpg', 'jpeg', 'png'];
  return bdaSupportedExtensions.includes(extension);
};

/**
 * Get processing type for workflow (matches backend logic)
 */
export const getProcessingType = (fileName: string): string => {
  if (!fileName || typeof fileName !== 'string') {
    return 'unknown';
  }
  
  const extension = getFileExtension(fileName);
  
  if (['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm', '3gp'].includes(extension)) {
    return 'video';
  }
  
  if (['mp3', 'wav', 'flac', 'm4a', 'aac', 'ogg', 'wma', 'aiff'].includes(extension)) {
    return 'audio';
  }
  
  if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'tif', 'webp'].includes(extension)) {
    return 'image';
  }
  
  if (['pdf', 'doc', 'docx', 'txt', 'rtf', 'odt', 'dwg', 'dxf'].includes(extension)) {
    return 'document';
  }
  
  return 'unknown';
};

/**
 * Format file size for display
 */
export const formatFileSize = (bytes: number | string | undefined): string => {
  if (!bytes) return 'Unknown';
  
  const size = typeof bytes === 'string' ? parseInt(bytes, 10) : bytes;
  if (isNaN(size)) return 'Unknown';

  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let unitIndex = 0;
  let fileSize = size;

  while (fileSize >= 1024 && unitIndex < units.length - 1) {
    fileSize /= 1024;
    unitIndex++;
  }

  return `${fileSize.toFixed(1)} ${units[unitIndex]}`;
};

/**
 * Get all supported file extensions
 */
export const getSupportedExtensions = (): string[] => {
  const allExtensions: string[] = [];
  
  Object.values(FILE_TYPE_MAPPINGS).forEach(config => {
    allExtensions.push(...config.extensions);
  });
  
  return allExtensions.map(ext => `.${ext}`);
};

/**
 * Check if file extension is supported
 */
export const isFileSupported = (fileName: string): boolean => {
  if (!fileName || typeof fileName !== 'string') {
    return false;
  }
  const extension = getFileExtension(fileName);
  const supportedExtensions = getSupportedExtensions().map(ext => ext.substring(1)); // Remove dots
  return supportedExtensions.includes(extension);
};

/**
 * Get HTML input accept attribute string for all supported file types
 */
export const getAcceptAttributeString = (): string => {
  const mimeTypes = [
    // Generic types for broader compatibility
    'image/*',
    'video/*', 
    'audio/*',
    // Specific document types
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'text/plain',
    'application/rtf',
    'application/vnd.oasis.opendocument.text'
  ];
  
  const extensions = getSupportedExtensions();
  
  return [...mimeTypes, ...extensions].join(',');
};

/**
 * Get react-dropzone accept object for all supported file types
 */
export const getDropzoneAcceptObject = () => {
  return {
    // Documents
    'application/pdf': ['.pdf'],
    'application/msword': ['.doc'],
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
    'text/plain': ['.txt'],
    'application/rtf': ['.rtf'],
    'application/vnd.oasis.opendocument.text': ['.odt'],
    'application/dwg': ['.dwg'],
    'application/dxf': ['.dxf'],
    
    // Images
    'image/*': ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', '.webp'],
    
    // Videos
    'video/*': ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm', '.3gp'],
    
    // Audio
    'audio/*': ['.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.wma', '.aiff']
  };
};

/**
 * Truncate filename with smart ellipsis placement
 * Keeps extension and part of the name visible
 */
export const truncateFilename = (fileName: string, maxLength: number = 30): string => {
  if (!fileName || typeof fileName !== 'string') {
    return 'Unknown file';
  }

  // If filename is already short enough, return as is
  if (fileName.length <= maxLength) {
    return fileName;
  }

  // Split filename and extension
  const lastDotIndex = fileName.lastIndexOf('.');
  if (lastDotIndex === -1) {
    // No extension, just truncate from the end
    return fileName.substring(0, maxLength - 3) + '...';
  }

  const name = fileName.substring(0, lastDotIndex);
  const extension = fileName.substring(lastDotIndex);

  // If extension is too long, truncate the whole thing
  if (extension.length >= maxLength - 3) {
    return fileName.substring(0, maxLength - 3) + '...';
  }

  // Calculate available space for the name part
  const availableSpace = maxLength - extension.length - 3; // 3 for "..."

  if (availableSpace <= 0) {
    return fileName.substring(0, maxLength - 3) + '...';
  }

  // Truncate name part and add ellipsis
  const truncatedName = name.substring(0, availableSpace);
  return truncatedName + '...' + extension;
};