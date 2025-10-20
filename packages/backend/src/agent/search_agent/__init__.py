"""
Search Agent with Strands Agents as Tools Pattern
"""
from .agent import SearchAgent
from .config import config
from .conversation_manager import ConversationManager

__all__ = [
    'SearchAgent',
    'config',
    'ConversationManager'
]
