"""
MCP-based LangGraph agent package
"""
_available_agents = []

try:
    from .react_agent import ReactAgent  
    _available_agents.append("ReactAgent")
except ImportError:
    ReactAgent = None

try:
    from .search_agent import SearchAgent
    _available_agents.append("SearchAgent")
except ImportError:
    SearchAgent = None

try:
    from .verification_agent import VerificationAgent
    _available_agents.append("VerificationAgent")
except ImportError:
    VerificationAgent = None

__all__ = _available_agents