import os
from typing import List, Dict, AsyncGenerator, Optional, Any
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_aws.chat_models import ChatBedrockConverse
from openinference.instrumentation.langchain import LangChainInstrumentor

class BedrockLLMService:
    """
    Chat Interface for Bedrock
    """
    def __init__(
        self, 
        model_id: str,
        region: Optional[str] = None, 
        temperature: Optional[float] = None, 
        max_tokens: Optional[int] = None,
        streaming: bool = True,
        profile_name: Optional[str] = None,
        tracer_provider = None, 
        callbacks = None,
        model_kwargs: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the BedrockChat class

        Args:
            model_id: Bedrock model ID (e.g., 'anthropic.claude-3-sonnet-20240229-v1:0')
            region: AWS region (default: environment variable or 'us-west-2')
            temperature: generation temperature (default: environment variable or 0.3)
            max_tokens: maximum number of tokens (default: environment variable or 4096)
            streaming: streaming support (default: True)
            profile_name: AWS profile name (default: environment variable or 'default')
            tracer_provider: OpenTelemetry tracer provider
            callbacks: list of LangChain callback handlers
            model_kwargs: additional arguments to pass to the model
        """
        # tracing setup
        if tracer_provider:
            LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
        
        # default parameter settings
        temp = temperature or float(os.environ.get("TEMPERATURE", 0.3))
        tokens = max_tokens or int(os.environ.get("MAX_TOKENS", 4096))
        region_name = region or os.environ.get("AWS_REGION", "us-west-2")
        profile_name = profile_name or os.environ.get("AWS_PROFILE", "default")
        
        # model parameter configuration
        model_params = {
            "credentials_profile_name": profile_name,
            "model": model_id,
            "region_name": region_name,
            "temperature": temp,
            "max_tokens": tokens,
        }
        
        # add callbacks
        if callbacks:
            model_params["callbacks"] = callbacks
            
        # merge additional model parameters
        if model_kwargs:
            model_params.update(model_kwargs)
        
        # initialize Bedrock model
        self.model = ChatBedrockConverse(**model_params)
        self.streaming = streaming

    def _format_messages(self, prompt: str, message_history: List[Dict] = None) -> List[BaseMessage]:
        """
        Convert message history and current prompt to LangChain format

        Args:
            prompt: current user prompt
            message_history: previous message history (optional)

        Returns:
            list of LangChain messages
        """
        messages = []
        
        # convert message history
        if message_history:
            for msg in message_history:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))
        
        # add current prompt
        cached_prompt = "You are a helpful assistant. You are given a question and you need to answer it. You are also given a cache of previous messages. You need to use the cache to answer the question."
        messages.append(SystemMessage(content=cached_prompt, additional_kwargs={"cache-control": {"type": "ephemeral"}}))
        messages.append(HumanMessage(content=prompt))
        
        
        return messages

    def _update_history(self, prompt: str, response: str, message_history: List[Dict] = None) -> List[Dict]:
        """
        Update message history

        Args:
            prompt: user prompt
            response: assistant response
            message_history: previous message history (optional)

        Returns:
            updated message history
        """
        history = message_history or []
        return history + [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": response}
        ]

    def chat(self, prompt: str, message_history: List[Dict] = None) -> Dict:
        """
        General chat method (non-streaming)

        Args:
            prompt: user prompt
            message_history: previous message history (optional)

        Returns:
            dictionary containing the response and updated message history
        """
        try:
            # convert message format
            messages = self._format_messages(prompt, message_history)
            
            # call model
            response = self.model.invoke(messages)
            print(response)
            assistant_message = response.content
            usage_metadata = response.usage_metadata
            input_tokens = usage_metadata.get("input_tokens", 'N/A')
            output_tokens = usage_metadata.get("output_tokens", 'N/A')
            total_tokens = usage_metadata.get("total_tokens", 'N/A')
            print(f"Input Tokens: {input_tokens}, Output Tokens: {output_tokens}, Total Tokens: {total_tokens}")
            
            # update message history
            updated_history = self._update_history(prompt, assistant_message, message_history)
            
            return {
                'response': assistant_message,
                'message_history': updated_history
            }
        except Exception as e:
            print(f"Error in chat: {str(e)}")
            raise e

    async def stream_chat(self, prompt: str, message_history: List[Dict] = None) -> AsyncGenerator:
        """
        Streams the chat response token by token using the model's native streaming capability
        """
        if message_history is None:
            message_history = []

        # Convert message history to LangChain format
        messages = []
        for msg in message_history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

        # Add current prompt
        messages.append(HumanMessage(content=prompt))

        try:
            complete_response = ""
            
            # Use the model's native streaming capability
            async for chunk in self.model.astream(messages):
                # Extract token from the chunk based on the response format
                if isinstance(chunk.content, list):
                    # Claude 3 format
                    for content_item in chunk.content:
                        if content_item.get('type') == 'text':
                            token = content_item.get('text', '')
                            if token:
                                complete_response += token
                                yield token
                else:
                    # Standard format
                    token = chunk.content
                    if token:
                        complete_response += token
                        yield token
            
            # Return final message with history
            updated_history = message_history + [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": complete_response}
            ]
            
            yield {
                'response': complete_response,
                'message_history': updated_history
            }

        except Exception as e:
            print(f"Error in stream_chat: {str(e)}")
            raise e
        
    async def stream_plan(self, prompt: str, message_history=None):
        async for token in self.stream_chat(prompt, message_history):
            yield token

    async def stream_response(self, prompt: str, message_history: List[Dict] = None):
        async for token in self.stream_chat(prompt, message_history):
            yield token
        

# Test the LLMChat class
if __name__ == "__main__":
    import asyncio
    from pathlib import Path
    from dotenv import load_dotenv

    root_dir = Path(__file__).resolve().parents[3]
    env_path = root_dir / '.env'
    print(env_path)

    # load environment variables
    load_dotenv(env_path)
    print(os.environ.get("AWS_REGION"))

    # Regular chat tests
    try:
        print("Start LLM Chat Test")
        
        # Create chat instance
        chat = BedrockLLMService(model_id="anthropic.claude-3-sonnet-20240229-v1:0")
        
        # Test prompt
        test_prompt = "Hello, this is a test message. My name is yunwoong."
        print(f"\nFirst Prompt: {test_prompt}")
        
        # Response test
        response = chat.chat(test_prompt)
        print(f"First Response: {response['response']}")
        
        # Second prompt test (remembering the previous message)
        second_prompt = "What did I say my name was?"
        print(f"\nSecond Prompt: {second_prompt}")

        response2 = chat.chat(second_prompt, response['message_history'])
        print(f"Second Response: {response2['response']}")
        print(f"\nBasic Chat Test Passed ✅")
        
        # Streaming test
        async def test_streaming():
            print("\nStart Streaming Test")
            
            stream_prompt = "Tell me a short story about a robot"
            print(f"\nStreaming Prompt: {stream_prompt}")
            
            print("\nStreaming response:")
            async for token in chat.stream_chat(stream_prompt):
                if isinstance(token, str):
                    print(token, end='', flush=True)
                else:
                    print(token)
                    print("\n\nFinal message history received ✅")
            
            print(f"\nStreaming Test Passed ✅")
        
        # Run streaming test
        asyncio.run(test_streaming())
        
        print("\nAll Tests Passed Successfully! ✅")
        
    except Exception as e:
        print(f"\nTest Failed ❌: {str(e)}")