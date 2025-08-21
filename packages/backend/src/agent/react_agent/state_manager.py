"""
State management utility functions for ReAct Agent
"""
import os
import logging
from typing import List, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from .state.model import State

logger = logging.getLogger(__name__)


def should_summarize(state: State) -> bool:
    """
    check if the message count exceeds the threshold (to avoid infinite loop)
    
    Args:
        state: current state
        
    Returns:
        whether summary is needed
    """
    SUMMARIZATION_THRESHOLD = int(os.getenv("SUMMARIZATION_THRESHOLD", "12"))
    
    current_count = len(state.messages)
    
    # avoid duplicate summary if already marked as needed
    if state.needs_summarization:
        return False
    
    # check if there are enough new messages since the last summary (minimum 6)
    messages_since_last_summary = current_count - state.last_summarization_at
    
    return current_count >= SUMMARIZATION_THRESHOLD and messages_since_last_summary >= 6


def get_messages_for_summarization(state: State) -> List[BaseMessage]:
    """
    return messages to summarize (excluding last 4)
    
    Args:
        state: current state
        
    Returns:
        list of messages to summarize
    """
    if len(state.messages) < 6:
        return []
    return state.messages[:-4]  # keep last 4 messages


def remove_image_data_from_content(content: Any) -> Any:
    """
    remove image data from message content
    
    Args:
        content: message content
        
    Returns:
        content with image data removed
    """
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        cleaned_content = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "image_url":
                    # remove image URL information and keep only text
                    cleaned_content.append({
                        "type": "text",
                        "text": "[image data removed]"
                    })
                else:
                    cleaned_content.append(item)
            else:
                cleaned_content.append(item)
        return cleaned_content
    else:
        return content


def prepare_messages_for_summary(messages: List[BaseMessage]) -> str:
    """
    convert messages to text for summary
    
    Args:
        messages: list of messages to summarize
        
    Returns:
        text content for summary
    """
    text_content = []
    
    for msg in messages:
        if isinstance(msg, (HumanMessage, AIMessage)):
            # remove image data
            cleaned_content = remove_image_data_from_content(msg.content)
            
            if isinstance(cleaned_content, str):
                text_content.append(f"{msg.__class__.__name__}: {cleaned_content}")
            else:
                # if list, extract only text
                text_parts = []
                for item in cleaned_content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                if text_parts:
                    text_content.append(f"{msg.__class__.__name__}: {' '.join(text_parts)}")
    
    return "\n".join(text_content)


def create_summary_prompt(conversation_text: str) -> str:
    """
    create prompt for conversation summary
    
    Args:
        conversation_text: conversation content
        
    Returns:
        summary prompt
    """
    return f"""
Please summarize the following conversation briefly. It should include key questions, answers, and conclusions.

Conversation content:
{conversation_text}

Summary:
"""