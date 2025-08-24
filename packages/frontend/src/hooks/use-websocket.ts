import { useEffect, useRef, useState, useCallback } from 'react';

export interface WebSocketMessage {
  type: 'real_time_update' | 'connection_status' | 'error' | 'ping' | 'pong' | 'upload_completion';
  table?: 'documents' | 'pages';
  event?: 'insert' | 'modify' | 'remove';
  data?: any;
  old_data?: any;
  timestamp?: number;
  message?: string;
  document_id?: string;
  file_name?: string;
  status?: 'success' | 'error';
}

export interface UseWebSocketOptions {
  autoConnect?: boolean;
  reconnectAttempts?: number;
  reconnectInterval?: number;
  onMessage?: (message: WebSocketMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
  indexId?: string;
  enabled?: boolean; // WebSocket 연결 활성화/비활성화
}

export interface UseWebSocketReturn {
  isConnected: boolean;
  isConnecting: boolean;
  error: string | null;
  connect: () => void;
  disconnect: () => void;
  sendMessage: (message: any) => void;
  lastMessage: WebSocketMessage | null;
  reconnectAttempts: number;
}

/**
 * WebSocket 연결을 관리하는 커스텀 훅
 * 
 * 기능:
 * - 자동 연결/재연결
 * - 인덱스별 메시지 필터링
 * - 연결 상태 관리
 * - 에러 처리
 */
export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    autoConnect = true,
    reconnectAttempts: maxReconnectAttempts = 5,
    reconnectInterval = 3000,
    onMessage,
    onConnect,
    onDisconnect,
    onError,
    indexId,
    enabled = true // 기본값은 활성화
  } = options;
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const shouldReconnectRef = useRef(true);

  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const heartbeatRef = useRef<NodeJS.Timeout | null>(null);

  // WebSocket URL 생성
  const getWebSocketUrl = useCallback(() => {
    const baseUrl = process.env.NEXT_PUBLIC_WEBSOCKET_URL || 'wss://lmu7b0u1s5.execute-api.us-west-2.amazonaws.com/dev';
    const params = new URLSearchParams();
    console.log('WebSocket environment URL:', process.env.NEXT_PUBLIC_WEBSOCKET_URL);
    console.log('WebSocket base URL:', baseUrl);
    
    if (indexId) {
      params.append('index_id', indexId);
    }
    
    // 사용자 ID는 향후 인증 시스템과 연동 예정
    params.append('user_id', 'anonymous');
    
    const url = `${baseUrl}?${params.toString()}`;
    console.log('WebSocket URL generated:', url);
    return url;
  }, [indexId]);

  // WebSocket 연결
  const connect = useCallback(() => {
    if (!enabled) {
      console.log('WebSocket: Connection disabled');
      setIsConnected(false);
      setIsConnecting(false);
      setError(null);
      return;
    }

    if (!indexId) {
      console.log('WebSocket: No index selected');
      return;
    }

    // 로컬 개발 환경에서도 WebSocket 연결 시도
    console.log('WebSocket: Attempting connection in', process.env.NODE_ENV, 'environment');

    if (wsRef.current?.readyState === WebSocket.CONNECTING || 
        wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('WebSocket: Already connected or connecting');
      return;
    }

    setIsConnecting(true);
    setError(null);

    try {
      const url = getWebSocketUrl();
      console.log('WebSocket: Connecting to', url);
      
      // 브라우저 WebSocket 지원 확인
      if (typeof WebSocket === 'undefined') {
        throw new Error('WebSocket is not supported in this browser');
      }
      
      // WebSocket 연결 시도 (추가 옵션 없이)
      console.log('WebSocket: Creating WebSocket instance');
      const ws = new WebSocket(url);
      wsRef.current = ws;
      
      // 브라우저 호환성 체크
      console.log('WebSocket: Browser support check', {
        WebSocketSupported: typeof WebSocket !== 'undefined',
        protocol: ws.protocol,
        extensions: ws.extensions,
        binaryType: ws.binaryType
      });
      
      // 연결 타임아웃 설정 (10초)
      const connectionTimeout = setTimeout(() => {
        if (ws.readyState === WebSocket.CONNECTING) {
          console.error('WebSocket: Connection timeout');
          ws.close();
          setError('WebSocket 연결 시간 초과');
          setIsConnecting(false);
        }
      }, 10000);

      ws.onopen = () => {
        clearTimeout(connectionTimeout);
        console.log('WebSocket: Connected successfully');
        setIsConnected(true);
        setIsConnecting(false);
        setError(null);
        setReconnectAttempts(0);
        shouldReconnectRef.current = true;
        
        // 하트비트 시작 (30초마다 ping)
        if (heartbeatRef.current) {
          clearInterval(heartbeatRef.current);
        }
        heartbeatRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 30000);
        
        onConnect?.();
      };

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          
          // ping/pong 메시지는 로그하지 않음
          if (message.type !== 'pong' && message.type !== 'ping') {
            console.log('WebSocket: Message received', message);
            setLastMessage(message);
            onMessage?.(message);
          }
        } catch (err) {
          console.warn('WebSocket: Failed to parse message', err);
          // 메시지 파싱 실패는 심각한 에러가 아니므로 에러 상태 설정하지 않음
        }
      };

      ws.onclose = (event) => {
        clearTimeout(connectionTimeout);
        console.log('WebSocket: Disconnected', {
          code: event.code,
          reason: event.reason,
          wasClean: event.wasClean,
          url: getWebSocketUrl()
        });
        
        setIsConnected(false);
        setIsConnecting(false);
        wsRef.current = null;
        
        // 하트비트 정리
        if (heartbeatRef.current) {
          clearInterval(heartbeatRef.current);
          heartbeatRef.current = null;
        }
        
        onDisconnect?.();

        // 에러 코드별 처리
        if (event.code === 1006) {
          console.warn('WebSocket: Connection failed with code 1006 - possible causes: network issues, server not available, CORS problems');
          setError('WebSocket 서버에 연결할 수 없습니다. 네트워크 상태를 확인해주세요.');
        } else if (event.code === 1002) {
          console.error('WebSocket: Protocol error');
          setError('WebSocket 프로토콜 오류가 발생했습니다.');
        } else if (event.code === 1003) {
          console.error('WebSocket: Invalid data received');
          setError('잘못된 데이터를 받았습니다.');
        }

        // 정상적인 종료가 아니고 재연결이 필요한 경우
        if (shouldReconnectRef.current && 
            event.code !== 1000 && 
            event.code !== 1001 && // Going Away (탭 전환 등)
            reconnectAttempts < maxReconnectAttempts) {
          
          const delay = Math.min(reconnectInterval * Math.pow(1.5, reconnectAttempts), 30000); // 최대 30초
          console.log(`WebSocket: Reconnecting in ${delay}ms (attempt ${reconnectAttempts + 1}/${maxReconnectAttempts})`);
          
          reconnectTimeoutRef.current = setTimeout(() => {
            setReconnectAttempts(prev => prev + 1);
            connect();
          }, delay);
        } else if (reconnectAttempts >= maxReconnectAttempts) {
          setError('최대 재연결 시도 횟수를 초과했습니다');
        }
      };

      ws.onerror = (event) => {
        clearTimeout(connectionTimeout);
        // console.error 대신 console.warn 사용하여 브라우저 에러 방지
        console.warn('WebSocket: Connection failed', {
          url: getWebSocketUrl(),
          readyState: ws.readyState,
          timestamp: new Date().toISOString()
        });
        
        // 에러 상태만 조용히 설정
        setError(`WebSocket 연결 실패: ${ws.readyState === 3 ? 'CLOSED' : 'UNKNOWN_STATE'}`);
        setIsConnecting(false);
        
        // onError 콜백도 에러를 throw하지 않도록 안전하게 처리
        try {
          onError?.(event);
        } catch (err) {
          // 콜백 에러도 조용히 처리
        }
      };

    } catch (err) {
      console.warn('WebSocket: Connection failed', err);
      setError('WebSocket 연결 실패');
      setIsConnecting(false);
    }
  }, [
    indexId,
    getWebSocketUrl,
    reconnectAttempts,
    maxReconnectAttempts,
    reconnectInterval,
    onConnect,
    onDisconnect,
    onError,
    onMessage,
    enabled
  ]);

  // WebSocket 연결 해제
  const disconnect = useCallback(() => {
    console.log('WebSocket: Disconnecting');
    shouldReconnectRef.current = false;
    
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close(1000, 'Manual disconnect');
      wsRef.current = null;
    }

    setIsConnected(false);
    setIsConnecting(false);
    setReconnectAttempts(0);
  }, []);

  // 메시지 전송
  const sendMessage = useCallback((message: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify(message));
        console.log('WebSocket: Message sent', message);
      } catch (err) {
        console.warn('WebSocket: Failed to send message', err);
        // 메시지 전송 실패는 일시적 문제일 수 있으므로 에러 상태 설정하지 않음
      }
    } else {
      console.warn('WebSocket: Cannot send message - not connected');
      // 연결되지 않은 상태에서의 메시지 전송 시도는 에러 상태 설정하지 않음
    }
  }, []);

  // 인덱스 변경 시 재연결
  useEffect(() => {
    let isCancelled = false;
    
    if (enabled && autoConnect && indexId) {
      // 이미 같은 인덱스로 연결되어 있으면 재연결하지 않음
      const currentUrl = getWebSocketUrl();
      if (wsRef.current?.url === currentUrl && wsRef.current?.readyState === WebSocket.OPEN) {
        console.log('WebSocket: Already connected to same index, skipping reconnection');
        return;
      }
      
      // 기존 연결이 있으면 먼저 해제
      if (wsRef.current) {
        console.log('WebSocket: Disconnecting existing connection for new index');
        disconnect();
      }
      
      // 새 인덱스로 연결 (디바운스)
      const timer = setTimeout(() => {
        if (!isCancelled) {
          console.log('WebSocket: Connecting to new index:', indexId);
          connect();
        }
      }, 500); // 500ms 지연으로 빠른 재연결 방지
      
      return () => {
        isCancelled = true;
        clearTimeout(timer);
      };
    } else if (!indexId || !enabled) {
      // 인덱스가 없거나 비활성화되면 연결 해제
      disconnect();
    }
    
    return () => {
      isCancelled = true;
    };
  }, [indexId, autoConnect, enabled]);

  // 컴포넌트 언마운트 시 정리
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  // 페이지 가시성 변경 시 처리 (탭 전환 등)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden) {
        // 페이지가 숨겨졌을 때는 연결 유지하되 하트비트 일시정지
        console.log('WebSocket: Page hidden, pausing heartbeat');
        if (heartbeatRef.current) {
          clearInterval(heartbeatRef.current);
          heartbeatRef.current = null;
        }
      } else {
        // 페이지가 다시 보일 때 연결 상태 확인 및 하트비트 재시작
        console.log('WebSocket: Page visible, checking connection');
        if (enabled && autoConnect && indexId) {
          if (isConnected && wsRef.current?.readyState === WebSocket.OPEN) {
            // 연결되어 있으면 하트비트만 재시작
            if (!heartbeatRef.current) {
              heartbeatRef.current = setInterval(() => {
                if (wsRef.current?.readyState === WebSocket.OPEN) {
                  wsRef.current.send(JSON.stringify({ type: 'ping' }));
                }
              }, 30000);
            }
          } else if (!isConnecting) {
            // 연결이 끊어져 있으면 재연결
            connect();
          }
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [enabled, autoConnect, indexId, isConnected, isConnecting, connect]);

  return {
    isConnected,
    isConnecting,
    error,
    connect,
    disconnect,
    sendMessage,
    lastMessage,
    reconnectAttempts
  };
}