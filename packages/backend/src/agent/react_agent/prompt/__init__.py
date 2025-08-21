# src/common/prompt_utils.py

import os
import yaml
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from langchain_core.messages import SystemMessage, HumanMessage
from datetime import datetime

class PromptLoader:
    """
    Class for loading prompts from YAML files.
    """
    
    def __init__(self, prompts_dir: Union[str, Path]):
        self.prompts_dir = Path(prompts_dir)
        self.prompts_cache = {}
    
    def load_prompt(self, name: str, variant: Optional[str] = None) -> Dict[str, Any]:
        """
        Load a prompt from a YAML file.
        
        Args:
            name: Prompt name (file name)
            variant: Prompt variant name (default if not provided)
            
        Returns:
            Dict: Loaded prompt data
        """
        # Create cache key
        cache_key = f"{name}_{variant or 'default'}"
        
        # If cached prompt exists, return it
        if cache_key in self.prompts_cache:
            return self.prompts_cache[cache_key]
        
        # Default prompt file path
        file_path = self.prompts_dir / f"{name}.yaml"
        
        # Variant prompt file path
        if variant and not file_path.exists():
            variant_path = self.prompts_dir / "variants" / f"{name}_{variant}.yaml"
            if variant_path.exists():
                file_path = variant_path
        
        # Check if file exists
        if not file_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {file_path}")
        
        # Load YAML file
        with open(file_path, 'r', encoding='utf-8') as file:
            prompt_data = yaml.safe_load(file)
        
        # Apply variant
        if variant and "variants" in prompt_data and variant in prompt_data["variants"]:
            variant_data = prompt_data["variants"][variant]
            
            # Merge variant data
            for key, value in variant_data.items():
                if key.endswith('_append') and key[:-7] in prompt_data:
                    # _append suffix fields are added to the existing content
                    base_key = key[:-7]
                    prompt_data[base_key] = prompt_data[base_key] + "\n" + value
                else:
                    # General fields are overwritten
                    prompt_data[key] = value
        
        # Remove variants field (not needed)
        if "variants" in prompt_data:
            del prompt_data["variants"]
        
        # Save to cache
        self.prompts_cache[cache_key] = prompt_data
        return prompt_data
    
    def format_prompt(self, prompt_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Format template fields in prompt data
        
        Args:
            prompt_data: Loaded prompt data
            **kwargs: Template variables
            
        Returns:
            Dict: Formatted prompt
        """
        result = {}
        
        # Check required variables
        if "variables" in prompt_data:
            for var in prompt_data["variables"]:
                if var.get("required", False) and var["name"] not in kwargs:
                    raise ValueError(f"Missing required variable: {var['name']}")
        
        # Format conditional blocks and variables
        for key, value in prompt_data.items():
            if isinstance(value, str):
                # Process conditional blocks
                processed_value = self._process_conditional_blocks(value, kwargs)
                
                try:
                    # Convert {{variable}} to {variable} and replace variables
                    converted_value = self._convert_double_braces(processed_value)
                    result[key] = converted_value.format(**kwargs)
                except KeyError as e:
                    raise ValueError(f"Missing format variable {e} in {key}")
            else:
                result[key] = value
        
        return result
    
    def _process_conditional_blocks(self, text: str, context: Dict[str, Any]) -> str:
        """
        Process conditional blocks {{#if condition}}...{{else}}...{{/if}}
        
        Args:
            text: Text to process
            context: Context containing condition variables
            
        Returns:
            str: Text with conditional blocks processed
        """
        # Find if blocks
        pattern = r'{{#if (\w+)}}(.*?)(?:{{else}}(.*?))?{{/if}}'
        
        def replace_conditional(match):
            condition_var = match.group(1)
            if_content = match.group(2)
            else_content = match.group(3) or ''
            
            # Evaluate condition
            if context.get(condition_var):
                return if_content
            else:
                return else_content
        
        # Process all conditional blocks
        return re.sub(pattern, replace_conditional, text, flags=re.DOTALL)
    
    def _convert_double_braces(self, text: str) -> str:
        """
        Convert {{variable}} to {variable} format
        
        Args:
            text: Text to convert
            
        Returns:
            str: Converted text
        """
        # Find {{variable}} pattern and convert to {variable}
        # Except for conditional blocks like {{#if, {{else}}, {{/if}}
        pattern = r'\{\{(?!#if|else|/if)([^}]+)\}\}'
        return re.sub(pattern, r'{\1}', text)


class PromptManager:
    """Prompt management class"""
    
    def __init__(self, prompts_dir: Union[str, Path]):
        self.loader = PromptLoader(prompts_dir)
        self.current_variants = {}  
    
    def get_prompt(self, name: str, variant: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Get formatted prompt
        
        Args:
            name: Prompt name
            variant: Prompt variant (default if not provided)
            **kwargs: Template variables
            
        Returns:
            Dict: 포맷팅된 프롬프트
        """
        # If variant is not provided, use the current variant
        if variant is None:
            variant = self.current_variants.get(name)
        
        # Load prompt
        prompt_data = self.loader.load_prompt(name, variant)
        
        # Update current variant
        if variant:
            self.current_variants[name] = variant
        
        # Format prompt
        return self.loader.format_prompt(prompt_data, **kwargs)
    
    def set_variant(self, name: str, variant: Optional[str] = None):
        """
        Set prompt variant
        
        Args:
            name: Prompt name
            variant: Prompt variant (None resets to default variant)
        """
        if variant is None:
            # Remove variant setting
            if name in self.current_variants:
                del self.current_variants[name]
        else:
            # Set variant
            self.current_variants[name] = variant
        
        return self
    
    def get_messages(self, name: str, variant: Optional[str] = None, **kwargs) -> List:
        """
        Create LangChain compatible message list
        
        Args:
            name: Prompt name
            variant: Prompt variant
            **kwargs: Template variables
            
        Returns:
            List: List of SystemMessage and HumanMessage objects
        """
        prompt = self.get_prompt(name, variant, **kwargs)
        
        return [
            SystemMessage(content=prompt["system_prompt"]),
            HumanMessage(content=prompt["instruction"])
        ]
    
    def toggle_variant(self, name: str, variant: str, condition: bool):
        """
        Toggle variant based on condition
        
        Args:
            name: Prompt name
            variant: Variant name to apply
            condition: True applies variant, False uses default prompt
            
        Returns:
            PromptManager: self for method chaining
        """
        return self.set_variant(name, variant if condition else None)
    
    def clear_cache(self):
        """
        Clear prompt cache
        """
        self.loader.prompts_cache = {}


# Create singleton instance
# Use prompts directory as default path
_module_path = Path(__file__).resolve()
_default_prompts_dir = _module_path.parent

# Create singleton instance
prompt_manager = PromptManager(_default_prompts_dir)

# Export manager for direct use
__all__ = [
    'PromptLoader', 
    'PromptManager', 
    'prompt_manager',
]