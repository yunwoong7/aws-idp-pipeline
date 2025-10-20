"""
Prompt management for Search Agent
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

class PromptManager:
    """Manager for loading and processing YAML prompts"""

    def __init__(self, reload: bool = False):
        self.prompt_dir = Path(__file__).parent
        self.prompt_cache = {} if reload else {}
        self._load_prompts()

    def _load_prompts(self):
        """Load all YAML prompts from the prompt directory"""
        for yaml_file in self.prompt_dir.glob("*.yaml"):
            if yaml_file.is_file():
                prompt_name = yaml_file.stem
                if prompt_name not in self.prompt_cache:
                    with open(yaml_file, 'r', encoding='utf-8') as f:
                        self.prompt_cache[prompt_name] = yaml.safe_load(f)

    def get_prompt(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a specific prompt by name"""
        return self.prompt_cache.get(name)

    def format_system_prompt(
        self,
        name: str,
        variables: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format system prompt with variables"""
        prompt_data = self.get_prompt(name)
        if not prompt_data:
            raise ValueError(f"Prompt '{name}' not found")

        system_prompt = prompt_data.get('system_prompt', '')

        # Default variables
        default_vars = {
            'DATETIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        # Merge with provided variables
        if variables:
            default_vars.update(variables)

        # Replace variables in prompt
        for key, value in default_vars.items():
            system_prompt = system_prompt.replace(f'{{{{{key}}}}}', str(value))

        return system_prompt

    def format_instruction(
        self,
        name: str,
        variables: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format instruction prompt with variables"""
        prompt_data = self.get_prompt(name)
        if not prompt_data:
            raise ValueError(f"Prompt '{name}' not found")

        instruction = prompt_data.get('instruction', '')

        # Default variables
        default_vars = {
            'DATETIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'INDEX_ID': '',
            'DOCUMENT_ID': '',
            'SEGMENT_ID': '',
            'QUERY': '',
            'CONVERSATION_HISTORY': '',
            'CONTENT': '',
            'REFERENCES': ''
        }

        # Merge with provided variables
        if variables:
            default_vars.update(variables)

        # Replace variables in instruction
        for key, value in default_vars.items():
            instruction = instruction.replace(f'{{{{{key}}}}}', str(value))

        return instruction

# Global prompt manager instance
prompt_manager = PromptManager()
