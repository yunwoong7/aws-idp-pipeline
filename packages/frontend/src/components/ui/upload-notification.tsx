'use client';

import React, { useState, useEffect } from 'react';
import { CheckCircle, XCircle, X } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface UploadNotification {
  id: string;
  message: string;
  status: 'success' | 'error';
  document_id?: string;
  file_name?: string;
  timestamp: number;
}

interface UploadNotificationProps {
  notification: UploadNotification;
  onDismiss: (id: string) => void;
  autoHide?: boolean;
  autoHideDelay?: number;
}

export function UploadNotificationItem({
  notification,
  onDismiss,
  autoHide = true,
  autoHideDelay = 5000
}: UploadNotificationProps) {
  const [isVisible, setIsVisible] = useState(true);
  const [isRemoving, setIsRemoving] = useState(false);

  useEffect(() => {
    if (autoHide) {
      const timer = setTimeout(() => {
        handleDismiss();
      }, autoHideDelay);

      return () => clearTimeout(timer);
    }
  }, [autoHide, autoHideDelay]);

  const handleDismiss = () => {
    setIsRemoving(true);
    setTimeout(() => {
      setIsVisible(false);
      onDismiss(notification.id);
    }, 300);
  };

  if (!isVisible) return null;

  const isSuccess = notification.status === 'success';

  return (
    <div
      className={cn(
        "flex items-center gap-3 p-4 mb-2 bg-card border rounded-lg shadow-lg transition-all duration-300 ease-in-out",
        isRemoving && "translate-x-full opacity-0",
        isSuccess 
          ? "border-green-500/20 bg-green-500/5" 
          : "border-red-500/20 bg-red-500/5"
      )}
    >
      {/* 상태 아이콘 */}
      <div className={cn(
        "flex-shrink-0",
        isSuccess ? "text-green-500" : "text-red-500"
      )}>
        {isSuccess ? (
          <CheckCircle className="h-5 w-5" />
        ) : (
          <XCircle className="h-5 w-5" />
        )}
      </div>

      {/* 메시지 내용 */}
      <div className="flex-1 min-w-0">
        <p className={cn(
          "text-sm font-medium",
          isSuccess ? "text-green-700 dark:text-green-300" : "text-red-700 dark:text-red-300"
        )}>
          {notification.message}
        </p>
        {notification.file_name && (
          <p className="text-xs text-muted-foreground mt-1">
            파일: {notification.file_name}
          </p>
        )}
      </div>

      {/* 닫기 버튼 */}
      <button
        onClick={handleDismiss}
        className="flex-shrink-0 p-1 hover:bg-background/50 rounded-md transition-colors"
        aria-label="알림 닫기"
      >
        <X className="h-4 w-4 text-muted-foreground" />
      </button>
    </div>
  );
}

interface UploadNotificationContainerProps {
  notifications: UploadNotification[];
  onDismiss: (id: string) => void;
  maxNotifications?: number;
  position?: 'top-right' | 'top-center' | 'top-left';
}

export function UploadNotificationContainer({
  notifications,
  onDismiss,
  maxNotifications = 5,
  position = 'top-center'
}: UploadNotificationContainerProps) {
  // 최신 알림만 표시
  const displayNotifications = notifications.slice(-maxNotifications);

  if (displayNotifications.length === 0) return null;

  const positionClasses = {
    'top-right': 'top-4 right-4',
    'top-center': 'top-4 left-1/2 -translate-x-1/2',
    'top-left': 'top-4 left-4'
  };

  return (
    <div className={cn(
      "fixed z-50 w-full max-w-sm",
      positionClasses[position]
    )}>
      {displayNotifications.map((notification) => (
        <UploadNotificationItem
          key={notification.id}
          notification={notification}
          onDismiss={onDismiss}
        />
      ))}
    </div>
  );
}