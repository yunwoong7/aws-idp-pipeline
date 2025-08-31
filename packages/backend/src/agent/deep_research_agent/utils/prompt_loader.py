"""
Utility for loading YAML prompts with variable substitution
"""
import yaml
import os
from typing import Dict, Any
from pathlib import Path


class PromptLoader:
    """Load and format YAML prompt templates"""
    
    def __init__(self, prompts_dir: str = None):
        """
        Initialize prompt loader
        
        Args:
            prompts_dir: Directory containing YAML prompt files
        """
        if prompts_dir is None:
            # Default to prompts directory relative to this file
            current_dir = Path(__file__).parent.parent
            self.prompts_dir = current_dir / "prompts"
        else:
            self.prompts_dir = Path(prompts_dir)
        
        self._prompt_cache = {}
    
    def load_prompts(self, filename: str) -> Dict[str, str]:
        """
        Load prompts from YAML file
        
        Args:
            filename: YAML filename (without extension)
        
        Returns:
            Dictionary of prompt templates
        """
        if filename in self._prompt_cache:
            return self._prompt_cache[filename]
        
        yaml_path = self.prompts_dir / f"{filename}.yaml"
        
        if not yaml_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {yaml_path}")
        
        with open(yaml_path, 'r', encoding='utf-8') as f:
            prompts = yaml.safe_load(f)
        
        self._prompt_cache[filename] = prompts
        return prompts
    
    def format_prompt(self, filename: str, prompt_key: str, **variables) -> str:
        """
        Load and format a specific prompt with variables
        
        Args:
            filename: YAML filename (without extension)
            prompt_key: Key of the prompt in the YAML file
            **variables: Variables for template substitution
        
        Returns:
            Formatted prompt string
        """
        prompts = self.load_prompts(filename)
        
        if prompt_key not in prompts:
            raise KeyError(f"Prompt key '{prompt_key}' not found in {filename}.yaml")
        
        template = prompts[prompt_key]
        
        # Replace {{variable}} patterns
        formatted = template
        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"
            formatted = formatted.replace(placeholder, str(value))
        
        return formatted
    
    def get_system_prompt(self, filename: str) -> str:
        """
        Get system prompt from YAML file
        
        Args:
            filename: YAML filename (without extension)
        
        Returns:
            System prompt string
        """
        return self.format_prompt(filename, "system_prompt")


# Global instance for convenience
prompt_loader = PromptLoader()