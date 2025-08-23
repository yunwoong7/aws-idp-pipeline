"""
ConversationManager - Manage conversation history
"""
import logging
import time
import os
from typing import Dict, List, Union, Optional
from datetime import datetime, timezone
from collections import OrderedDict
from threading import RLock
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage

from .prompt import prompt_manager
from .utils import normalize_content

logger = logging.getLogger(__name__)


class ConversationManager:
    """
    Thread-safe class to manage conversation history per thread with memory optimization
    """
    
    def __init__(self, debug_mode: bool = False, max_threads: int = 100, max_messages_per_thread: int = 50):
        """
        Initialize ConversationManager with memory management
        
        Args:
            debug_mode: Whether to enable debug mode
            max_threads: Maximum number of threads to keep in memory
            max_messages_per_thread: Maximum messages per thread
        """
        self._lock = RLock()
        self.conversation_history: OrderedDict[str, List[Dict]] = OrderedDict()
        self.thread_last_access: Dict[str, float] = {}
        self.debug_mode = debug_mode
        self.max_threads = max_threads
        self.max_messages_per_thread = max_messages_per_thread
        
        logger.info(f"ConversationManager initialized - max_threads: {max_threads}, max_messages_per_thread: {max_messages_per_thread}")

    def prepare_conversation(
        self, 
        thread_id: str, 
        input_messages: List[BaseMessage], 
        index_id: Optional[str] = None,
        document_id: Optional[str] = None,
        segment_id: Optional[str] = None
    ) -> List[BaseMessage]:
        """
        Prepare conversation history - Fix duplicate system prompt issue
        
        Args:
            thread_id: Thread ID
            input_messages: List of input messages
            index_id: Index ID (optional)
            
        Returns:
            Prepared conversation message list
        """
        # Add current user messages to conversation_history (only pure conversation)
        current_user_messages = [msg for msg in input_messages if isinstance(msg, HumanMessage)]
        
        # Thread-safe initialization and cleanup
        with self._lock:
            self._update_thread_access(thread_id)
            if thread_id not in self.conversation_history:
                self.conversation_history[thread_id] = []
            self._cleanup_old_threads()
            
        # Add current user messages to history (thread-safe)
        if current_user_messages:
            with self._lock:
                for msg in current_user_messages:
                    content = normalize_content(msg.content)
                    if content:
                        # Check for duplicates
                        if (not self.conversation_history[thread_id] or 
                            self.conversation_history[thread_id][-1].get("content") != content or
                            self.conversation_history[thread_id][-1].get("role") != "user"):
                            self.conversation_history[thread_id].append({
                                "role": "user",
                                "content": content,
                                "timestamp": time.time()
                            })
                            self._trim_thread_messages(thread_id)
        print(f"index_id: {index_id}, document_id: {document_id}, segment_id: {segment_id}")

        # Create system prompt only once (do not duplicate)
        system_prompt_text = prompt_manager.get_prompt(
            "agent_profile", 
            DATETIME=datetime.now(tz=timezone.utc).isoformat(),
            INDEX_ID=index_id or "unknown",
            DOCUMENT_ID=document_id or "unknown",
            SEGMENT_ID=segment_id or "unknown",
            QUERY="",
            CONVERSATION_HISTORY="",
            CONTENT="",
            REFERENCES=""
        )["system_prompt"]
        
        # Construct final conversation list
        # Add system message only once at the beginning
        # Then add only pure conversation (Human/AI)
        final_conversation = [SystemMessage(content=system_prompt_text)]
        
        # Add conversation history (thread-safe read)
        with self._lock:
            thread_messages = self.conversation_history.get(thread_id, [])
            for msg in thread_messages:
                content = normalize_content(msg.get("content"))
                if not content:
                    continue
                    
                # Ensure only 'user' and 'assistant' roles are stored
                if msg["role"] == "user":
                    final_conversation.append(HumanMessage(content=content))
                elif msg["role"] == "assistant":
                    final_conversation.append(AIMessage(content=content))
                # Ignore system messages or other messages
        
        # Debug logging
        if self.debug_mode:
            pure_history_count = len(self.conversation_history.get(thread_id, []))
            final_conversation_count = len(final_conversation)
            logger.info(f"Pure conversation history: {pure_history_count} messages")
            logger.info(f"Final constructed conversation: {final_conversation_count} messages (system prompt 1 + conversation {pure_history_count} messages)")
            
        return final_conversation

    def add_user_message_to_history(self, thread_id: str, messages: List[BaseMessage]) -> None:
        """
        Add user messages to conversation history (thread-safe)
        
        Args:
            thread_id: Thread identifier
            messages: List of messages to process (system messages are never stored)
        """
        with self._lock:
            self._update_thread_access(thread_id)
            # Check if thread history exists
            if thread_id not in self.conversation_history:
                self.conversation_history[thread_id] = []
            
            # Extract message history for this thread
            message_history = self.conversation_history[thread_id]
            
            # Add user messages to history (only pure conversation)
            for msg in messages:
                # System messages are never stored
                if isinstance(msg, SystemMessage):
                    logger.debug("System messages are never stored in user conversation history")
                    continue
                    
                # Process only user messages
                if isinstance(msg, HumanMessage):
                    content = normalize_content(msg.content)
                    if content:  # Skip empty messages
                        # Check for duplicates
                        if (message_history and 
                            message_history[-1].get("role") == "user" and 
                            normalize_content(message_history[-1].get("content")) == content):
                            logger.debug("Duplicate user message detected - do not add to history")
                            continue
                        
                        # Store only pure user conversation
                        message_history.append({
                            "role": "user",
                            "content": content,
                            "timestamp": time.time()
                        })
                        logger.debug(f"Added user message to pure conversation history (length: {len(content)})")
                        self._trim_thread_messages(thread_id)

    def add_assistant_message_to_history(self, thread_id: str, message: Union[AIMessage, str]) -> None:
        """
        Add assistant message to conversation history (thread-safe)
        
        Args:
            thread_id: Thread ID
            message: Assistant message (system messages are never stored)
        """
        # Do not store system messages
        if isinstance(message, SystemMessage):
            logger.debug("System messages are never stored in conversation history")
            return
        
        with self._lock:
            self._update_thread_access(thread_id)
            # Initialize thread history
            if thread_id not in self.conversation_history:
                self.conversation_history[thread_id] = []
            
            # Extract message content
            content = ""
            if isinstance(message, AIMessage):
                content = normalize_content(message.content)
            else:
                content = normalize_content(message)
            
            # Skip empty messages
            if not content:
                logger.debug("Empty messages are never stored in conversation history")
                return
            
            # Enhanced duplicate check: check recent messages
            recent_messages = self.conversation_history[thread_id][-3:]  # Check only recent 3 messages
            for recent_msg in reversed(recent_messages):
                if (recent_msg["role"] == "assistant" and 
                    normalize_content(recent_msg["content"]) == content):
                    logger.info("Duplicate assistant message detected - do not add to history")
                    return
            
            # Store only pure conversation
            self.conversation_history[thread_id].append({
                "role": "assistant",
                "content": content,
                "timestamp": time.time()
            })
            
            # Trim messages if needed
            self._trim_thread_messages(thread_id)
            
            # Enhanced logging
            total_messages = len(self.conversation_history[thread_id])
            logger.info(f"Added assistant message to pure conversation history (length: {len(content)}, total messages: {total_messages})")
            
            if self.debug_mode:
                # Check role distribution in conversation history
                user_count = sum(1 for msg in self.conversation_history[thread_id] if msg["role"] == "user")
                assistant_count = sum(1 for msg in self.conversation_history[thread_id] if msg["role"] == "assistant")
                logger.info(f"Pure conversation history composition: user {user_count} messages, assistant {assistant_count} messages")

    def clear_conversation_history(self, thread_id: str = None) -> bool:
        """
        Clear conversation history (thread-safe)
        
        Args:
            thread_id: Specific thread ID (None for full cleanup)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self._lock:
                if thread_id:
                    # Clear specific thread history
                    if thread_id in self.conversation_history:
                        del self.conversation_history[thread_id]
                        if thread_id in self.thread_last_access:
                            del self.thread_last_access[thread_id]
                        logger.info(f"Cleared conversation history for thread {thread_id}")
                    return True
                else:
                    # Clear all conversation history
                    self.conversation_history.clear()
                    self.thread_last_access.clear()
                    logger.info("Cleared all conversation history")
                    return True
                    
        except Exception as e:
            logger.error(f"Error in clearing conversation history: {e}")
            return False

    def get_conversation_history(self, thread_id: str) -> List[Dict]:
        """
        Return conversation history for a specific thread (thread-safe)
        
        Args:
            thread_id: Thread ID
            
        Returns:
            List of conversation history
        """
        with self._lock:
            self._update_thread_access(thread_id)
            return self.conversation_history.get(thread_id, [])

    def get_conversation_context(self, thread_id: str, max_history: int = 6) -> str:
        """
        Return conversation context as a string (thread-safe)
        
        Args:
            thread_id: Thread ID
            max_history: Maximum history count
            
        Returns:
            Conversation context string
        """
        with self._lock:
            self._update_thread_access(thread_id)
            if thread_id not in self.conversation_history:
                return ""
            
            history = self.conversation_history[thread_id]
            if not history:
                return ""
            
            # Get recent history
            recent_history = history[-max_history:]
            
            history_items = []
            for item in recent_history:
                role = item["role"]
                content = item["content"][:300] + "..." if len(item["content"]) > 300 else item["content"]
                history_items.append(f"{role.title()}: {content}")
            
            return "\n".join(history_items)

    def get_thread_count(self) -> int:
        """
        Return number of active threads (thread-safe)
        
        Returns:
            Number of active threads
        """
        with self._lock:
            return len(self.conversation_history)

    def get_total_message_count(self) -> int:
        """
        Return total number of messages (thread-safe)
        
        Returns:
            Total number of messages
        """
        with self._lock:
            total = 0
            for thread_messages in self.conversation_history.values():
                total += len(thread_messages)
            return total
    
    def _update_thread_access(self, thread_id: str) -> None:
        """
        Update last access time for a thread (internal method)
        
        Args:
            thread_id: Thread ID
        """
        self.thread_last_access[thread_id] = time.time()
        # Move to end in OrderedDict (LRU behavior)
        if thread_id in self.conversation_history:
            self.conversation_history.move_to_end(thread_id)
    
    def _trim_thread_messages(self, thread_id: str) -> None:
        """
        Trim messages for a specific thread if it exceeds the limit
        
        Args:
            thread_id: Thread ID
        """
        if thread_id in self.conversation_history:
            messages = self.conversation_history[thread_id]
            if len(messages) > self.max_messages_per_thread:
                # Keep only the most recent messages
                self.conversation_history[thread_id] = messages[-self.max_messages_per_thread:]
                logger.info(f"Trimmed thread {thread_id} to {self.max_messages_per_thread} messages")
    
    def _cleanup_old_threads(self) -> None:
        """
        Remove old threads if we exceed the maximum thread count
        """
        if len(self.conversation_history) > self.max_threads:
            # Remove oldest threads (LRU)
            threads_to_remove = len(self.conversation_history) - self.max_threads
            for _ in range(threads_to_remove):
                oldest_thread, _ = self.conversation_history.popitem(last=False)
                if oldest_thread in self.thread_last_access:
                    del self.thread_last_access[oldest_thread]
                logger.info(f"Removed old thread {oldest_thread} to maintain memory limits")
    
    def get_memory_stats(self) -> Dict[str, int]:
        """
        Return memory usage statistics
        
        Returns:
            Dictionary with memory statistics
        """
        with self._lock:
            return {
                "total_threads": len(self.conversation_history),
                "total_messages": sum(len(messages) for messages in self.conversation_history.values()),
                "max_threads": self.max_threads,
                "max_messages_per_thread": self.max_messages_per_thread,
                "memory_usage_percent": round((len(self.conversation_history) / self.max_threads) * 100, 2)
            }