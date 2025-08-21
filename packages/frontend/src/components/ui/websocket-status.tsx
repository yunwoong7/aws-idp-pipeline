'use client';

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Wifi, WifiOff, Loader2, AlertCircle, CheckCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useWebSocketStatus } from '@/contexts/websocket-context';

interface WebSocketStatusProps {
  className?: string;
  showDetails?: boolean;
  position?: 'top-right' | 'top-left' | 'bottom-right' | 'bottom-left';
}

/**
 * WebSocket 연결 상태를 표시하는 컴포넌트
 * 
 * 기능:
 * - 연결 상태 아이콘 및 텍스트 표시
 * - 자동 숨김/표시
 * - 재연결 시도 횟수 표시
 * - 수신된 메시지 통계
 */
export function WebSocketStatus({ 
  className,
  showDetails = false,
  position = 'top-right'
}: WebSocketStatusProps) {
  const { 
    isConnected, 
    isConnecting, 
    error, 
    reconnectAttempts,
    showConnectionStatus,
    messagesReceived,
    lastUpdateTime
  } = useWebSocketStatus();

  // 상태에 따른 아이콘과 메시지 결정
  const getStatusInfo = () => {
    if (isConnecting) {
      return {
        icon: <Loader2 className="h-4 w-4 animate-spin" />,
        text: reconnectAttempts > 0 ? `재연결 중... (${reconnectAttempts}/5)` : '연결 중...',
        bgColor: 'bg-blue-500/90',
        textColor: 'text-white',
        borderColor: 'border-blue-400'
      };
    }
    
    if (error) {
      return {
        icon: <AlertCircle className="h-4 w-4" />,
        text: `연결 오류: ${error}`,
        bgColor: 'bg-red-500/90',
        textColor: 'text-white',
        borderColor: 'border-red-400'
      };
    }
    
    if (isConnected) {
      return {
        icon: <CheckCircle className="h-4 w-4" />,
        text: '실시간 연결됨',
        bgColor: 'bg-green-500/90',
        textColor: 'text-white',
        borderColor: 'border-green-400'
      };
    }
    
    return {
      icon: <WifiOff className="h-4 w-4" />,
      text: '연결 끊김',
      bgColor: 'bg-gray-500/90',
      textColor: 'text-white',
      borderColor: 'border-gray-400'
    };
  };

  const statusInfo = getStatusInfo();

  // 포지션 클래스 결정
  const getPositionClasses = () => {
    switch (position) {
      case 'top-left':
        return 'top-4 left-4';
      case 'bottom-left':
        return 'bottom-4 left-4';
      case 'bottom-right':
        return 'bottom-4 right-4';
      default:
        return 'top-4 right-4';
    }
  };

  // 간단한 상태 표시 (항상 표시)
  const SimpleStatus = () => (
    <div className={cn(
      "flex items-center gap-2 px-3 py-2 rounded-lg border backdrop-blur-sm transition-all duration-300",
      statusInfo.bgColor,
      statusInfo.textColor,
      statusInfo.borderColor,
      className
    )}>
      {statusInfo.icon}
      <span className="text-sm font-medium">{statusInfo.text}</span>
    </div>
  );

  // 상세 상태 표시 (조건부 표시)
  const DetailedStatus = () => (
    <AnimatePresence>
      {showConnectionStatus && (
        <motion.div
          initial={{ opacity: 0, y: -20, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -20, scale: 0.9 }}
          transition={{ duration: 0.3, ease: "easeOut" }}
          className={cn(
            "fixed z-50",
            getPositionClasses()
          )}
        >
          <div className={cn(
            "flex flex-col gap-2 p-4 rounded-lg border backdrop-blur-sm shadow-lg min-w-[250px]",
            statusInfo.bgColor,
            statusInfo.textColor,
            statusInfo.borderColor,
            className
          )}>
            {/* 메인 상태 */}
            <div className="flex items-center gap-3">
              {statusInfo.icon}
              <span className="font-medium">{statusInfo.text}</span>
            </div>
            
            {/* 상세 정보 */}
            {showDetails && (
              <div className="mt-2 pt-2 border-t border-white/20 space-y-1">
                <div className="flex justify-between text-xs opacity-90">
                  <span>수신 메시지:</span>
                  <span>{messagesReceived.toLocaleString()}개</span>
                </div>
                {lastUpdateTime && (
                  <div className="flex justify-between text-xs opacity-90">
                    <span>마지막 업데이트:</span>
                    <span>{lastUpdateTime.toLocaleTimeString()}</span>
                  </div>
                )}
                {reconnectAttempts > 0 && (
                  <div className="flex justify-between text-xs opacity-90">
                    <span>재연결 시도:</span>
                    <span>{reconnectAttempts}/5</span>
                  </div>
                )}
              </div>
            )}
            
            {/* 연결 상태 표시기 */}
            <div className="flex items-center gap-2 mt-1">
              <div className={cn(
                "w-2 h-2 rounded-full",
                isConnected ? "bg-green-300 animate-pulse" : 
                isConnecting ? "bg-blue-300 animate-bounce" : 
                "bg-red-300"
              )} />
              <span className="text-xs opacity-75">
                {isConnected ? 'LIVE' : isConnecting ? 'CONNECTING' : 'OFFLINE'}
              </span>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );

  return showDetails ? <DetailedStatus /> : <SimpleStatus />;
}

/**
 * 간단한 WebSocket 연결 상태 인디케이터
 */
export function WebSocketIndicator({ className }: { className?: string }) {
  const { isConnected, isConnecting } = useWebSocketStatus();
  
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className={cn(
        "w-2 h-2 rounded-full transition-colors duration-300",
        isConnected ? "bg-green-500 animate-pulse" : 
        isConnecting ? "bg-yellow-500 animate-bounce" : 
        "bg-red-500"
      )} />
      <span className="text-xs text-muted-foreground">
        {isConnected ? 'LIVE' : isConnecting ? 'CONNECTING' : 'OFFLINE'}
      </span>
    </div>
  );
}

/**
 * WebSocket 연결 상태를 헤더에 표시하는 컴포넌트
 */
export function WebSocketHeaderStatus() {
  const { isConnected, isConnecting, error } = useWebSocketStatus();
  
  if (isConnected && !error) {
    return null; // 정상 연결 시에는 표시하지 않음
  }
  
  return (
    <div className="flex items-center gap-2 px-3 py-1 bg-yellow-500/10 border border-yellow-500/20 rounded-md">
      {isConnecting ? (
        <Loader2 className="h-3 w-3 animate-spin text-yellow-500" />
      ) : (
        <WifiOff className="h-3 w-3 text-red-500" />
      )}
      <span className="text-xs text-muted-foreground">
        {isConnecting ? '실시간 연결 중...' : '실시간 업데이트 불가'}
      </span>
    </div>
  );
}