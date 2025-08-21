'use client';

import React, { createContext, useContext, useCallback, useState, useEffect } from 'react';
import { useWebSocket, WebSocketMessage, UseWebSocketReturn } from '@/hooks/use-websocket';
import { useToast } from '@/hooks/use-toast';

interface DocumentUpdate {
  document_id: string;
  project_id: string;
  status?: string;
  processing_status?: string;
  [key: string]: any;
}

interface PageUpdate {
  page_id: string;
  project_id: string;
  document_id: string;
  page_status?: string;
  analysis_completed_at?: string;
  [key: string]: any;
}

interface WebSocketContextType extends UseWebSocketReturn {
  // 이벤트 핸들러 등록/해제
  onDocumentUpdate: (handler: (update: DocumentUpdate, event: 'insert' | 'modify' | 'remove') => void) => () => void;
  onPageUpdate: (handler: (update: PageUpdate, event: 'insert' | 'modify' | 'remove') => void) => () => void;
  onAnyUpdate: (handler: (message: WebSocketMessage) => void) => () => void;
  
  // 연결 상태 표시
  showConnectionStatus: boolean;
  setShowConnectionStatus: (show: boolean) => void;
  
  // 통계
  messagesReceived: number;
  lastUpdateTime: Date | null;
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined);

interface WebSocketProviderProps {
  children: React.ReactNode;
  showToastOnError?: boolean;
  showToastOnReconnect?: boolean;
}

/**
 * WebSocket 컨텍스트 프로바이더
 * 
 * 기능:
 * - 애플리케이션 전체에서 WebSocket 연결 상태 공유
 * - 문서/페이지 업데이트 이벤트 핸들러 관리
 * - 에러 및 재연결 알림
 * - 연결 상태 표시
 */
export function WebSocketProvider({ 
  children, 
  showToastOnError = true,
  showToastOnReconnect = true 
}: WebSocketProviderProps) {
  const { toast } = useToast();
  const [showConnectionStatus, setShowConnectionStatus] = useState(false);
  const [messagesReceived, setMessagesReceived] = useState(0);
  const [lastUpdateTime, setLastUpdateTime] = useState<Date | null>(null);
  
  // 이벤트 핸들러들을 저장하는 ref
  const documentHandlersRef = React.useRef<Set<(update: DocumentUpdate, event: 'insert' | 'modify' | 'remove') => void>>(new Set());
  const pageHandlersRef = React.useRef<Set<(update: PageUpdate, event: 'insert' | 'modify' | 'remove') => void>>(new Set());
  const anyUpdateHandlersRef = React.useRef<Set<(message: WebSocketMessage) => void>>(new Set());

  // WebSocket 훅 사용
  const webSocket = useWebSocket({
    autoConnect: true,
    reconnectAttempts: process.env.NODE_ENV === 'development' ? 1 : 3, // 개발 환경에서는 재연결 시도 최소화
    reconnectInterval: 5000,
    onMessage: useCallback((message: WebSocketMessage) => {
      console.log('WebSocket Context: Message received', message);
      
      setMessagesReceived(prev => prev + 1);
      setLastUpdateTime(new Date());

      // 타입별 핸들러 호출
      if (message.type === 'real_time_update') {
        if (message.table === 'documents' && message.data && message.event) {
          documentHandlersRef.current.forEach(handler => {
            try {
              handler(message.data as DocumentUpdate, message.event as 'insert' | 'modify' | 'remove');
            } catch (error) {
              console.error('WebSocket Context: Document handler error', error);
            }
          });
        } else if (message.table === 'pages' && message.data && message.event) {
          pageHandlersRef.current.forEach(handler => {
            try {
              handler(message.data as PageUpdate, message.event as 'insert' | 'modify' | 'remove');
            } catch (error) {
              console.error('WebSocket Context: Page handler error', error);
            }
          });
        }
      }

      // 모든 업데이트 핸들러 호출
      anyUpdateHandlersRef.current.forEach(handler => {
        try {
          handler(message);
        } catch (error) {
          console.error('WebSocket Context: Any update handler error', error);
        }
      });
    }, []),
    
    onConnect: useCallback(() => {
      console.log('WebSocket Context: Connected');
      // 연결 성공 toast 제거 - 사용자에게 불필요한 알림
    }, []),
    
    onDisconnect: useCallback(() => {
      console.log('WebSocket Context: Disconnected');
    }, []),
    
    onError: useCallback((error: Event) => {
      console.error('WebSocket Context: Error', error);
      // 에러 toast도 제거 - 자동 재연결로 충분
    }, [])
  });

  // 문서 업데이트 핸들러 등록
  const onDocumentUpdate = useCallback((handler: (update: DocumentUpdate, event: 'insert' | 'modify' | 'remove') => void) => {
    documentHandlersRef.current.add(handler);
    
    // 해제 함수 반환
    return () => {
      documentHandlersRef.current.delete(handler);
    };
  }, []);

  // 페이지 업데이트 핸들러 등록
  const onPageUpdate = useCallback((handler: (update: PageUpdate, event: 'insert' | 'modify' | 'remove') => void) => {
    pageHandlersRef.current.add(handler);
    
    // 해제 함수 반환
    return () => {
      pageHandlersRef.current.delete(handler);
    };
  }, []);

  // 모든 업데이트 핸들러 등록
  const onAnyUpdate = useCallback((handler: (message: WebSocketMessage) => void) => {
    anyUpdateHandlersRef.current.add(handler);
    
    // 해제 함수 반환
    return () => {
      anyUpdateHandlersRef.current.delete(handler);
    };
  }, []);

  // 연결 상태 표시 자동 관리
  useEffect(() => {
    if (webSocket.isConnecting || webSocket.error) {
      setShowConnectionStatus(true);
    } else if (webSocket.isConnected) {
      // 연결 성공 후 3초 뒤에 상태 표시 숨김
      const timer = setTimeout(() => {
        setShowConnectionStatus(false);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [webSocket.isConnected, webSocket.isConnecting, webSocket.error]);

  const contextValue: WebSocketContextType = {
    ...webSocket,
    onDocumentUpdate,
    onPageUpdate,
    onAnyUpdate,
    showConnectionStatus,
    setShowConnectionStatus,
    messagesReceived,
    lastUpdateTime,
  };

  return (
    <WebSocketContext.Provider value={contextValue}>
      {children}
    </WebSocketContext.Provider>
  );
}

/**
 * WebSocket 컨텍스트를 사용하는 훅
 */
export function useWebSocketContext(): WebSocketContextType {
  const context = useContext(WebSocketContext);
  if (context === undefined) {
    throw new Error('useWebSocketContext must be used within a WebSocketProvider');
  }
  return context;
}

/**
 * 문서 업데이트만 구독하는 훅
 */
export function useDocumentUpdates() {
  const { onDocumentUpdate } = useWebSocketContext();
  
  return useCallback((handler: (update: DocumentUpdate, event: 'insert' | 'modify' | 'remove') => void) => {
    return onDocumentUpdate(handler);
  }, [onDocumentUpdate]);
}

/**
 * 페이지 업데이트만 구독하는 훅
 */
export function usePageUpdates() {
  const { onPageUpdate } = useWebSocketContext();
  
  return useCallback((handler: (update: PageUpdate, event: 'insert' | 'modify' | 'remove') => void) => {
    return onPageUpdate(handler);
  }, [onPageUpdate]);
}

/**
 * WebSocket 연결 상태만 사용하는 훅
 */
export function useWebSocketStatus() {
  const { 
    isConnected, 
    isConnecting, 
    error, 
    reconnectAttempts,
    showConnectionStatus,
    setShowConnectionStatus,
    messagesReceived,
    lastUpdateTime
  } = useWebSocketContext();
  
  return {
    isConnected,
    isConnecting,
    error,
    reconnectAttempts,
    showConnectionStatus,
    setShowConnectionStatus,
    messagesReceived,
    lastUpdateTime,
  };
}