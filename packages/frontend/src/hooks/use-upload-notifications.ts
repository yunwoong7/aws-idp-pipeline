'use client';

import { useState, useCallback, useEffect } from 'react';
import { useWebSocketContext } from '@/contexts/websocket-context';
import { UploadNotification } from '@/components/ui/upload-notification';

interface UseUploadNotificationsOptions {
  maxNotifications?: number;
  autoRemove?: boolean;
  autoRemoveDelay?: number;
}

export function useUploadNotifications(options: UseUploadNotificationsOptions = {}) {
  const {
    maxNotifications = 5,
    autoRemove = true,
    autoRemoveDelay = 8000
  } = options;

  const [notifications, setNotifications] = useState<UploadNotification[]>([]);
  const { onAnyUpdate } = useWebSocketContext();

  // 알림 추가
  const addNotification = useCallback((notification: Omit<UploadNotification, 'id'>) => {
    const newNotification: UploadNotification = {
      ...notification,
      id: `upload_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    };

    setNotifications(prev => {
      const updated = [...prev, newNotification];
      // 최대 개수 초과 시 오래된 알림 제거
      return updated.slice(-maxNotifications);
    });

    // 자동 제거
    if (autoRemove) {
      setTimeout(() => {
        removeNotification(newNotification.id);
      }, autoRemoveDelay);
    }

    return newNotification.id;
  }, [maxNotifications, autoRemove, autoRemoveDelay]);

  // 알림 제거
  const removeNotification = useCallback((id: string) => {
    setNotifications(prev => prev.filter(notification => notification.id !== id));
  }, []);

  // 모든 알림 제거
  const clearNotifications = useCallback(() => {
    setNotifications([]);
  }, []);

  // WebSocket 메시지 구독
  useEffect(() => {
    const unsubscribe = onAnyUpdate((message) => {
      if (message.type === 'upload_completion') {
        addNotification({
          message: message.message || '파일 처리가 완료되었습니다.',
          status: message.status || 'success',
          document_id: message.document_id,
          file_name: message.file_name,
          timestamp: message.timestamp || Date.now()
        });
      }
    });

    return unsubscribe;
  }, [onAnyUpdate, addNotification]);

  return {
    notifications,
    addNotification,
    removeNotification,
    clearNotifications
  };
}