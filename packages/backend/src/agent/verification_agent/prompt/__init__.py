"""
VerificationAgent Prompt package
"""

import yaml
import os
from pathlib import Path
from typing import Dict, Any

class PromptManager:
    """Manages verification prompts"""
    
    def __init__(self):
        self.prompts: Dict[str, Any] = {}
        self._load_prompts()
    
    def _load_prompts(self):
        """Load prompts from YAML file"""
        try:
            prompt_file = Path(__file__).parent / "verification_prompts.yaml"
            with open(prompt_file, 'r', encoding='utf-8') as f:
                self.prompts = yaml.safe_load(f)
        except Exception as e:
            print(f"Warning: Failed to load verification prompts: {e}")
            self.prompts = {}
    
    def get_prompt(self, prompt_name: str) -> Dict[str, Any]:
        """Get prompt by name"""
        return self.prompts.get(prompt_name, {})
    
    def get_system_prompt(self, prompt_name: str) -> str:
        """Get system prompt text"""
        prompt = self.get_prompt(prompt_name)
        return prompt.get("system_prompt", "")
    
    def format_prompt(self, prompt_name: str, **kwargs) -> str:
        """Format prompt with variables"""
        system_prompt = self.get_system_prompt(prompt_name)
        try:
            return system_prompt.format(**kwargs)
        except KeyError as e:
            print(f"Warning: Missing prompt variable {e} for prompt {prompt_name}")
            return system_prompt

# Global prompt manager instance
prompt_manager = PromptManager()

__all__ = ["prompt_manager", "PromptManager"]