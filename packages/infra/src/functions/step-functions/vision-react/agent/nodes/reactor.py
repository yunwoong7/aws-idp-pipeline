"""
Vision Reactor Node - Thinks and decides next action based on image and observations
"""

import os
import sys
import json
import logging
import base64
from typing import Dict, Any, Optional
from datetime import datetime

sys.path.append('/opt/python')
from common import S3Service, AWSClientFactory

from agent.state.agent_state import AgentState
from agent.tools import get_all_tools
from prompts import prompt_manager

logger = logging.getLogger(__name__)

class ReactorNode:
    """
    Reactor that can see images and decide next actions
    """
    
    def __init__(self):
        """Initialize Vision Reactor"""
        # Bedrock runtime for vision analysis
        self.bedrock_client = AWSClientFactory.get_bedrock_runtime_client()
        self.vision_model_id = os.environ.get('BEDROCK_AGENT_MODEL_ID', 'us.anthropic.claude-3-5-sonnet-20241022-v2:0')
        self.max_tokens = int(os.environ.get('BEDROCK_AGENT_MAX_TOKENS', 64000))

        # S3 for image download - S3Service will handle bucket discovery
        self.s3_service = S3Service()
        
        # Load available tools
        self.tools = get_all_tools()
        
        logger.info(f"✅ VisionReactorNode initialized with {len(self.tools)} tools")
    
    def _get_tool_descriptions(self) -> str:
        """Generate dynamic tool descriptions"""
        tool_descriptions = []
        for tool in self.tools:
            # Get tool name from class name
            tool_name = tool.__class__.__name__.replace('Tool', '')
            
            # Get description from tool's schema or docstring
            description = None
            
            # Try to get description from schema
            if hasattr(tool, 'get_schema'):
                try:
                    schema = tool.get_schema()
                    if hasattr(schema, '__doc__') and schema.__doc__:
                        description = schema.__doc__.strip()
                except:
                    pass
            
            # Fallback to tool docstring
            if not description and tool.__doc__:
                lines = tool.__doc__.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('"""') and not line.startswith('Args:') and not line.startswith('Returns:'):
                        description = line
                        break
            
            # Default description if nothing found
            if not description:
                if tool_name == 'ImageAnalyzer':
                    description = "Deep image analysis with specific queries"
                elif tool_name == 'VideoAnalyzer':
                    description = "Analyze video chapters"
                else:
                    description = f"Analysis tool for {tool_name.lower()}"
            
            tool_descriptions.append(f"{tool_name}: {description}")
        
        return "\n".join(tool_descriptions)
    
    def __call__(self, state: AgentState) -> AgentState:
        """Process current state and decide next action"""
        
        # If this is not the first iteration, check if we should continue
        if state.get('iteration_count', 0) > 0:
            # Check if we have observations to process
            observations = state.get('observations', [])
            if not observations or observations[-1].get('success') == False:
                logger.info("🛑 Last action failed or no observations, stopping")
                state['should_continue'] = False
                state['next_action'] = None
                return state
        
        logger.info("=" * 60)
        logger.info(f"🧠 VISION REACTOR - Iteration {state.get('iteration_count', 0) + 1}/{state.get('max_iterations', 5)}")
        logger.info("=" * 60)
        
        try:
            # Generate tool descriptions
            tool_descriptions = self._get_tool_descriptions()
            
            # Build context from previous iterations
            context = self._build_context(state)
            
            # Get current date
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            # Get prompts from YAML
            prompts = prompt_manager.get_prompt(
                'reactor',
                'think_and_act',
                user_query=state.get('user_query'),
                media_type=state.get('media_type'),
                tool_descriptions=tool_descriptions,
                previous_context=context,
                current_date=current_date,
                iteration=state.get('iteration_count', 0) + 1,
                max_iterations=state.get('max_iterations', 5)
            )
            
            # Prepare message content based on media type
            message_content = [{"type": "text", "text": prompts['user_prompt']}]
            
            # For IMAGE and DOCUMENT, include the actual image
            if state.get('media_type') in ['IMAGE', 'DOCUMENT'] and state.get('image_uri'):
                try:
                    image_base64 = self._download_and_encode_image(state.get('image_uri'))
                    message_content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_base64
                        }
                    })
                    logger.info(f"✅ {state.get('media_type')} image added to message content")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load image, proceeding with text-only: {e}")
            else:
                logger.info(f"📺 {state.get('media_type')} mode - proceeding with text-only analysis based on previous context")
            
            # Call model to think and decide
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": self.max_tokens,
                "temperature": 0.1,
                "system": prompts['system_prompt'],
                "messages": [{
                    "role": "user",
                    "content": message_content
                }]
            }
            
            response = self.bedrock_client.invoke_model(
                modelId=self.vision_model_id,
                body=json.dumps(request_body),
                contentType='application/json'
            )
            
            response_body = json.loads(response['body'].read())
            reactor_response = response_body['content'][0]['text']
            
            # Parse the response to extract thought and action
            thought, action = self._parse_reactor_response(reactor_response, state.get('iteration_count', 0))
            
            # Add thought to state
            if thought:
                thoughts = state.get('thoughts', [])
                thoughts.append(thought)
                state['thoughts'] = thoughts
                logger.info(f"💭 Thought: {thought['content']}")
            
            # Set next action
            if action:
                state['next_action'] = action
                logger.info(f"🎯 Next Action: {action['tool_name']}")
                logger.info(f"📝 Rationale: {action['rationale']}")
            else:
                # No more actions needed
                state['should_continue'] = False
                state['next_action'] = None
                logger.info("✅ No more actions needed, ready to respond")
            
            # Increment iteration count
            state['iteration_count'] = state.get('iteration_count', 0) + 1
            
            return state
            
        except Exception as e:
            logger.error(f"❌ Reactor failed: {str(e)}")
            state['should_continue'] = False
            state['next_action'] = None
            return state
    
    def _build_context(self, state: AgentState) -> str:
        """Build context from previous iterations"""
        context_parts = []
        
        # Add previous analysis context if this is the first iteration
        iteration_count = state.get('iteration_count', 0)
        previous_context = state.get('previous_analysis_context', '')
        if iteration_count == 0 and previous_context:
            context_parts.append("=== Previous Analysis Context ===")
            context_parts.append(previous_context)
            context_parts.append("")
        
        # Add previous thoughts and observations
        thoughts = state.get('thoughts', [])
        actions = state.get('actions', [])
        observations = state.get('observations', [])
        
        for i in range(len(thoughts)):
            context_parts.append(f"=== Iteration {i + 1} ===")
            
            if i < len(thoughts):
                thought = thoughts[i]
                context_parts.append(f"Thought: {thought.get('content', '')}")
            
            if i < len(actions):
                action = actions[i]
                context_parts.append(f"Action: {action.get('tool_name', '')} - {action.get('rationale', '')}")
            
            if i < len(observations):
                obs = observations[i]
                result = obs.get('result', '')
                # Show full observation result for ReAct to make proper decisions
                context_parts.append(f"Observation: {result}")
            
            context_parts.append("")
        
        return "\n".join(context_parts)
    
    def _parse_reactor_response(self, response: str, iteration: int) -> tuple:
        """Parse reactor response to extract thought and action"""
        thought = None
        action = None
        
        try:
            # Look for thought pattern
            if "<thought>" in response and "</thought>" in response:
                thought_start = response.index("<thought>") + len("<thought>")
                thought_end = response.index("</thought>")
                thought_content = response[thought_start:thought_end].strip()
                
                thought = {
                    "iteration": iteration,
                    "content": thought_content,
                    "timestamp": datetime.now().isoformat()
                }
            
            # Look for action pattern
            if "<action>" in response and "</action>" in response:
                action_start = response.index("<action>") + len("<action>")
                action_end = response.index("</action>")
                action_content = response[action_start:action_end].strip()
                
                # Parse action JSON
                try:
                    action_data = json.loads(action_content)
                    action = {
                        "iteration": iteration,
                        "tool_name": action_data.get("tool_name"),
                        "tool_args": action_data.get("tool_args", {}),
                        "rationale": action_data.get("rationale", "")
                    }
                except json.JSONDecodeError:
                    logger.warning("Failed to parse action JSON, trying alternative format")
                    # Try to extract tool name and rationale manually
                    lines = action_content.split('\n')
                    for line in lines:
                        if 'tool_name' in line:
                            tool_name = line.split(':')[1].strip().strip('"').strip("'")
                            action = {
                                "iteration": iteration,
                                "tool_name": tool_name,
                                "tool_args": {},
                                "rationale": "Extracted from response"
                            }
                            break
            
            # Check for STOP signal
            if "<stop>" in response.lower() or "no more actions" in response.lower():
                action = None  # Signal to stop
            
        except Exception as e:
            logger.error(f"Failed to parse reactor response: {e}")
            logger.debug(f"Response was: {response}")
        
        return thought, action
    
    def _download_and_encode_image(self, image_uri: str) -> str:
        """Download image from S3 and encode to base64"""
        try:
            # Use S3Service to download and encode image
            # The S3Service will handle bucket resolution and resizing
            base64_image = self.s3_service.download_image_as_base64(
                s3_uri_or_key=image_uri,
                max_size=(2048, 2048)  # Reasonable max size for vision models
            )
            
            logger.info(f"Successfully downloaded and encoded image: {image_uri}")
            return base64_image
            
        except Exception as e:
            logger.error(f"Failed to download image: {str(e)}")
            raise
    
    def _resize_if_needed(self, image_bytes: bytes, max_mb: float = 3.5) -> bytes:
        """Resize image if too large"""
        size_mb = len(image_bytes) / (1024 * 1024)
        
        if size_mb <= max_mb:
            return image_bytes
            
        try:
            from PIL import Image
            import io
            
            # Load and resize
            img = Image.open(io.BytesIO(image_bytes))
            ratio = (max_mb / size_mb) ** 0.5
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            
            # Save to bytes
            output = io.BytesIO()
            img.save(output, format='PNG' if img.mode == 'RGBA' else 'JPEG', 
                    quality=85, optimize=True)
            
            return output.getvalue()
            
        except Exception as e:
            logger.warning(f"Resize failed, using original: {e}")
            return image_bytes