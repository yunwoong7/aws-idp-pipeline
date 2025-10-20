"""
Strands Analysis Agent - Strands SDK based implementation
"""
import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import AnalysisAgent

__all__ = ["AnalysisAgent"]