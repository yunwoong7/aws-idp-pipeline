import { useEffect, useRef, useState } from 'react';
import { Message } from '@/types/chat.types';

export function useChatScroll(messages: Message[], isStreaming: boolean) {
    const [userHasScrolled, setUserHasScrolled] = useState(false);
    const [showScrollButton, setShowScrollButton] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const isNearBottomRef = useRef(true);

    // 하단으로 스크롤하는 함수
    const scrollToBottom = (smooth = true) => {
        if (messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({
                behavior: smooth ? 'smooth' : 'auto',
                block: 'end'
            });
            setUserHasScrolled(false);
            isNearBottomRef.current = true;
        }
    };

    // 스크롤 위치 감지 함수
    const handleScroll = () => {
        if (!scrollContainerRef.current) return;
        
        const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
        const isNearBottom = scrollHeight - scrollTop - clientHeight < 150;
        
        setShowScrollButton(!isNearBottom);
        
        if (!isNearBottom && !userHasScrolled) {
            setUserHasScrolled(true);
        } else if (isNearBottom && userHasScrolled) {
            setUserHasScrolled(false);
        }
        
        isNearBottomRef.current = isNearBottom;
    };

    // 메시지 내용 변경 시에도 자동 스크롤 (스트리밍 중 실시간 스크롤)
    useEffect(() => {
        if (isStreaming && messages.length > 0) {
            const lastMessage = messages[messages.length - 1];
            if (lastMessage?.isStreaming && (!userHasScrolled || isNearBottomRef.current)) {
                // 실시간으로 스크롤하되 더 짧은 지연시간 사용
                const scrollTimeout = setTimeout(() => scrollToBottom(false), 30);
                return () => clearTimeout(scrollTimeout);
            }
        }
    }, [messages.map(m => m.contentItems.map(item => 
        item.type === 'text' ? `${item.id}-${item.content.length}-${item.timestamp}` : item.id
    ).join(',')), isStreaming, userHasScrolled]);

    // 메시지 변경 시 자동 스크롤 (새 메시지 추가 시)
    useEffect(() => {
        if (messages.length > 0) {
            // 스트리밍 중이거나 사용자가 하단 근처에 있으면 자동 스크롤
            if (isStreaming || (!userHasScrolled || isNearBottomRef.current)) {
                scrollToBottom();
            }
        }
    }, [messages.length, userHasScrolled, isStreaming]);

    // 스트리밍 시작 시 스크롤
    useEffect(() => {
        if (isStreaming) {
            scrollToBottom();
        }
    }, [isStreaming]);

    // 스크롤 이벤트 리스너 등록
    useEffect(() => {
        const scrollContainer = scrollContainerRef.current;
        if (scrollContainer) {
            scrollContainer.addEventListener('scroll', handleScroll);
            return () => {
                scrollContainer.removeEventListener('scroll', handleScroll);
            };
        }
    }, []);

    return {
        messagesEndRef,
        scrollContainerRef,
        showScrollButton,
        scrollToBottom,
        handleScroll
    };
}