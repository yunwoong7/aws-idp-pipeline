"""
ConversationManager - Manage conversation history
"""
import logging
from typing import Dict, List, Union, Optional
from datetime import datetime, timezone
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage

from .prompt import prompt_manager
from .utils import normalize_content

logger = logging.getLogger(__name__)


class ConversationManager:
    """
    Class to manage conversation history per thread
    """
    
    def __init__(self, debug_mode: bool = False):
        """
        Initialize ConversationManager
        
        Args:
            debug_mode: Whether to enable debug mode
        """
        self.conversation_history: Dict[str, List[Dict]] = {}
        self.debug_mode = debug_mode

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
        
        # Initialize thread history
        if thread_id not in self.conversation_history:
            self.conversation_history[thread_id] = []
            
        # Add current user messages to history (only pure conversation, excluding system messages)
        if current_user_messages:
            for msg in current_user_messages:
                content = normalize_content(msg.content)
                if content:
                    # Check for duplicates: whether the same message already exists
                    if (not self.conversation_history[thread_id] or 
                        self.conversation_history[thread_id][-1].get("content") != content or
                        self.conversation_history[thread_id][-1].get("role") != "user"):
                        self.conversation_history[thread_id].append({
                            "role": "user",
                            "content": content
                        })
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
        
        # Add only pure conversation from conversation history (do not store system messages)
        for msg in self.conversation_history.get(thread_id, []):
            content = normalize_content(msg.get("content"))
            if not content:
                continue
                
            # Ensure only 'user' and 'assistant' roles are stored in conversation_history
            if msg["role"] == "user":
                final_conversation.append(HumanMessage(content=content))
            elif msg["role"] == "assistant":
                final_conversation.append(AIMessage(content=content))
            # Ignore system messages or other messages (already added once at the top)
        
        # Debug logging
        if self.debug_mode:
            pure_history_count = len(self.conversation_history.get(thread_id, []))
            final_conversation_count = len(final_conversation)
            logger.info(f"Pure conversation history: {pure_history_count} messages")
            logger.info(f"Final constructed conversation: {final_conversation_count} messages (system prompt 1 + conversation {pure_history_count} messages)")
            
        return final_conversation

    def add_user_message_to_history(self, thread_id: str, messages: List[BaseMessage]) -> None:
        """
        Add user messages to conversation history (only pure conversation)
        
        Args:
            thread_id: Thread identifier
            messages: List of messages to process (system messages are never stored)
        """
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
                    # Check for duplicates: whether the same message already exists
                    if (message_history and 
                        message_history[-1].get("role") == "user" and 
                        normalize_content(message_history[-1].get("content")) == content):
                        logger.debug("Duplicate user message detected - do not add to history")
                        continue
                    
                    # Store only pure user conversation
                    message_history.append({
                        "role": "user",  # Only store pure user messages (not system)
                        "content": content
                    })
                    logger.debug(f"Added user message to pure conversation history (length: {len(content)})")

    def add_assistant_message_to_history(self, thread_id: str, message: Union[AIMessage, str]) -> None:
        """
        Add assistant message to conversation history (only pure conversation)
        
        Args:
            thread_id: Thread ID
            message: Assistant message (system messages are never stored)
        """
        # Do not store system messages
        if isinstance(message, SystemMessage):
            logger.debug("System messages are never stored in conversation history")
            return
        
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
        
        # Store only pure conversation (only 'user' and 'assistant' roles allowed)
        self.conversation_history[thread_id].append({
            "role": "assistant",  # Only
            "content": content
        })
        
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
        Clear conversation history
        
        Args:
            thread_id: Specific thread ID (None for full cleanup)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if thread_id:
                # Clear specific thread history
                if thread_id in self.conversation_history:
                    del self.conversation_history[thread_id]
                    logger.info(f"Cleared conversation history for thread {thread_id}")
                return True
            else:
                # Clear all conversation history
                self.conversation_history.clear()
                logger.info("Cleared all conversation history")
                return True
                
        except Exception as e:
            logger.error(f"Error in clearing conversation history: {e}")
            return False

    def get_conversation_history(self, thread_id: str) -> List[Dict]:
        """
        Return conversation history for a specific thread
        
        Args:
            thread_id: Thread ID
            
        Returns:
            List of conversation history
        """
        return self.conversation_history.get(thread_id, [])

    def get_conversation_context(self, thread_id: str, max_history: int = 6) -> str:
        """
        Return conversation context as a string
        
        Args:
            thread_id: Thread ID
            max_history: Maximum history count
            
        Returns:
            Conversation context string
        """
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
        Return number of active threads
        
        Returns:
            Number of active threads
        """
        return len(self.conversation_history)

    def get_total_message_count(self) -> int:
        """
        Return total number of messages
        
        Returns:
            Total number of messages
        """
        total = 0
        for thread_messages in self.conversation_history.values():
            total += len(thread_messages)
        return total