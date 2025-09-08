"""
Conversation management for Strands Analysis Agent
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class ConversationManager:
    """Manager for conversation history and context"""
    
    def __init__(self):
        self.conversations = {}
        self.max_history_length = 20  # Keep last 20 messages per thread
    
    def get_history(self, thread_id: str) -> str:
        """Get formatted conversation history for a thread"""
        if thread_id not in self.conversations:
            return ""
        
        history = self.conversations[thread_id]
        formatted_history = []
        
        for msg in history[-self.max_history_length:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            timestamp = msg.get("timestamp", "")
            
            formatted_history.append(f"{role}: {content}")
        
        return "\n".join(formatted_history)
    
    def add_message(self, thread_id: str, role: str, content: str):
        """Add a message to conversation history"""
        if thread_id not in self.conversations:
            self.conversations[thread_id] = []
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        
        self.conversations[thread_id].append(message)
        
        # Trim history if too long
        if len(self.conversations[thread_id]) > self.max_history_length * 2:
            self.conversations[thread_id] = self.conversations[thread_id][-self.max_history_length:]
        
        logger.debug(f"Added message to thread {thread_id}: {role}")
    
    def get_messages(self, thread_id: str) -> List[Dict[str, Any]]:
        """Get raw messages for a thread"""
        return self.conversations.get(thread_id, [])
    
    def clear_history(self, thread_id: str):
        """Clear history for a specific thread"""
        if thread_id in self.conversations:
            del self.conversations[thread_id]
            logger.info(f"Cleared history for thread: {thread_id}")
    
    def clear_all(self):
        """Clear all conversation history"""
        self.conversations.clear()
        logger.info("Cleared all conversation history")
    
    def get_thread_ids(self) -> List[str]:
        """Get all active thread IDs"""
        return list(self.conversations.keys())