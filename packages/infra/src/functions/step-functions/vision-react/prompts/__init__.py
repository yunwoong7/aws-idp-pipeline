"""
Prompt management system for Vision Plan Execute agent
"""

import os
import yaml
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class PromptManager:
    """
    YAML-based prompt management system
    """
    
    def __init__(self):
        """Initialize prompt manager"""
        self.prompts_dir = os.path.dirname(os.path.abspath(__file__))
        self._prompt_cache = {}
        logger.info(f"PromptManager initialized with directory: {self.prompts_dir}")
    
    def get_prompt(self, prompt_file: str, prompt_key: str, **kwargs) -> Dict[str, str]:
        """
        Get prompt from YAML file and format with variables
        
        Args:
            prompt_file: YAML filename (without .yaml extension)
            prompt_key: Key within the YAML file
            **kwargs: Variables to format into the prompt template
            
        Returns:
            Dict containing system_prompt and user_prompt
        """
        try:
            # Load prompt from cache or file
            if prompt_file not in self._prompt_cache:
                self._load_prompt_file(prompt_file)
            
            # Get specific prompt
            prompt_data = self._prompt_cache[prompt_file].get(prompt_key)
            if not prompt_data:
                raise KeyError(f"Prompt key '{prompt_key}' not found in {prompt_file}.yaml")
            
            # Format templates
            system_template = prompt_data.get('system_prompt', '')
            user_template = prompt_data.get('user_prompt_template', '')
            
            # Format both system and user prompts with variables using {{}} format
            system_prompt = self._format_template(system_template, **kwargs) if system_template else ''
            user_prompt = self._format_template(user_template, **kwargs) if user_template else ''
            
            # Log prompt usage
            logger.info(f"📝 Loaded prompt: {prompt_file}.{prompt_key}")
            logger.info(f"   System prompt: {len(system_prompt)} chars")
            logger.info(f"   User prompt: {len(user_prompt)} chars")
            
            # Log full prompts for debugging
            logger.info("=" * 80)
            logger.info(f"SYSTEM PROMPT ({prompt_file}.{prompt_key}):")
            logger.info(system_prompt)
            logger.info("-" * 80)
            logger.info(f"USER PROMPT ({prompt_file}.{prompt_key}):")
            logger.info(user_prompt)
            logger.info("=" * 80)
            
            return {
                'system_prompt': system_prompt,
                'user_prompt': user_prompt
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get prompt {prompt_file}.{prompt_key}: {e}")
            raise
    
    def _load_prompt_file(self, prompt_file: str):
        """Load prompts from YAML file"""
        file_path = os.path.join(self.prompts_dir, f"{prompt_file}.yaml")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self._prompt_cache[prompt_file] = yaml.safe_load(f)
            
            logger.info(f"✅ Loaded prompt file: {prompt_file}.yaml")
            
        except FileNotFoundError:
            logger.error(f"❌ Prompt file not found: {file_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"❌ YAML parsing error in {file_path}: {e}")
            raise
    
    def get_text(self, prompt_file: str, template_key: str, field: str = 'template', **kwargs) -> str:
        """Get a single text field from YAML and format it with variables.
        
        Args:
            prompt_file: YAML filename without extension
            template_key: The top-level key under which the text template resides
            field: The field name containing the template string (default: 'template')
            **kwargs: Variables to interpolate into the template
        
        Returns:
            Formatted text string
        """
        try:
            if prompt_file not in self._prompt_cache:
                self._load_prompt_file(prompt_file)
            prompt_data = self._prompt_cache[prompt_file].get(template_key)
            if not prompt_data:
                raise KeyError(f"Template key '{template_key}' not found in {prompt_file}.yaml")
            raw_template = prompt_data.get(field, '')
            if not isinstance(raw_template, str) or not raw_template:
                raise KeyError(f"Field '{field}' not found or empty in {prompt_file}.{template_key}")
            formatted = self._format_template(raw_template, **kwargs)
            logger.info(f"📝 Loaded text: {prompt_file}.{template_key}.{field} ({len(formatted)} chars)")
            return formatted
        except Exception as e:
            logger.error(f"❌ Failed to get text {prompt_file}.{template_key}.{field}: {e}")
            raise
    
    def list_available_prompts(self) -> Dict[str, list]:
        """List all available prompts"""
        available = {}
        
        for file in os.listdir(self.prompts_dir):
            if file.endswith('.yaml') and not file.startswith('_'):
                file_key = file[:-5]  # Remove .yaml extension
                try:
                    if file_key not in self._prompt_cache:
                        self._load_prompt_file(file_key)
                    available[file_key] = list(self._prompt_cache[file_key].keys())
                except Exception as e:
                    logger.error(f"Error loading {file}: {e}")
        
        return available
    
    def _format_template(self, template: str, **kwargs) -> str:
        """Format template using {{variable}} syntax"""
        import re
        
        def replace_var(match):
            var_name = match.group(1)
            return str(kwargs.get(var_name, f"{{{{{var_name}}}}}"))
        
        # Replace {{variable}} with values
        return re.sub(r'\{\{([^}]+)\}\}', replace_var, template)
    
    def reload_prompts(self):
        """Clear cache and reload all prompts"""
        self._prompt_cache.clear()
        logger.info("🔄 Prompt cache cleared")

# Global prompt manager instance
prompt_manager = PromptManager()