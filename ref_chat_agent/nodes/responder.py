# src/agent/nodes/responder.py
import time
import re
from colorama import Fore, Style
from typing import cast, List, Dict, Any, Optional, Tuple
from langchain_core.messages import HumanMessage, AIMessage
from src.chat_agent.states.schemas import AgentState
from src.chat_agent.prompts import prompt_manager
from src.chat_agent.tools.base import Reference

class ResponderNode:
    """
    ResponderNode generates comprehensive responses based on executed tasks 
    and direct responses, handling thought process display as needed.
    """
    
    def __init__(self, llm, show_thought_process: bool = False):
        """
        Initialize the ResponderNode
        
        Args:
            llm: LLM service to use for response generation
            show_thought_process: Whether to show the thought process in the output
        """
        self.model = llm.model
        self.show_thought_process = show_thought_process
        
        # Set the variant based on the show_thought_process parameter
        prompt_manager.toggle_variant("responder", "with_thought_process", show_thought_process)
    
    def toggle_thought_process(self, show: bool):
        """
        Toggle whether to show the thought process in the output
        
        Args:
            show: Whether to show the thought process
        """
        self.show_thought_process = show
        prompt_manager.toggle_variant("responder", "with_thought_process", show)
        return self
    
    def _build_context(self, state: AgentState) -> Tuple[str, List[str], List[Any]]:
        """
        Build context and references from state
        
        Args:
            state: The current agent state
            
        Returns:
            Tuple containing:
              - context text (str)
              - list of reference strings (List[str])
              - list of original references (List[Any])
        """
        if state.plan.direct_response:
            return f"Direct response: {state.plan.direct_response}", [], []
        
        # Initialize references and context parts
        references = []
        context_parts = [f"Plan overview: {state.plan.overview}\n\nExecuted tasks and their results:\n"]
        ref_index = 1
        
        # Store original references
        original_references = []
        
        for task_info in state.executed_tasks:
            task = task_info['task']
            result = task_info.get('result', '')
            success = task_info.get('success', False)

            if not success:
                context_parts.append(f"Status: Failed")
                context_parts.append(f"Error: {result}")
                continue

            # Process the result
            if isinstance(result, dict):
                # Add LLM text if available
                if 'llm_text' in result:
                    context_parts.append(result['llm_text'])
                
                # Process references
                if 'references' in result and isinstance(result['references'], list):
                    # Store original references
                    original_references.extend(result['references'])
                    
                    for ref in result['references']:
                        # Format reference for display
                        ref_text = f"[{ref_index}] {ref.get('type', 'link')}: {ref.get('value', '')}"
                        if ref.get('title'):
                            ref_text += f" - {ref.get('title')}"
                        references.append(ref_text)
                        ref_index += 1
                # Fallback if no LLM text or specific processing
                if 'llm_text' not in result and 'results' not in result:
                    context_parts.append(str(result))
            else:
                context_parts.append(str(result))

        return "\n".join(context_parts), references, original_references
    
    def _filter_references_from_response(self, response: str, original_references: List[Any]) -> List[Any]:
        """
        Filter references that appear in the final response
        
        Args:
            response: The final response text
            original_references: List of all original references
            
        Returns:
            List of references that are referenced in the response
        """
        if not original_references:
            print(Fore.CYAN + "\n📋 참조 데이터가 없습니다." + Style.RESET_ALL)
            return []
        
        # 응답 로깅 (디버깅용)
        print(Fore.GREEN + "\n📝 필터링 대상 응답 내용:" + Style.RESET_ALL)
        print("=" * 80)
        # 응답이 너무 길면 처음 500자와 마지막 500자만 출력
        if len(response) > 1000:
            print(response[:500] + "\n...\n" + response[-500:])
        else:
            print(response)
        print("=" * 80 + "\n")
        
        print(Fore.CYAN + f"\n📋 원본 참조 데이터 {len(original_references)}개 발견됨:" + Style.RESET_ALL)
        for i, ref in enumerate(original_references):
            ref_type = ref.get('type', '알 수 없음')
            ref_title = ref.get('title', '제목 없음')
            ref_value = ref.get('value', '')
            value_preview = ref_value[:30] + '...' if ref_value and len(ref_value) > 30 else ref_value
            print(f"  {i+1}. [{ref_type}] {ref_title} - {value_preview}")
        
        # 이미지 참조 파악 (이제 자동 포함하지 않음)
        image_references = [ref for ref in original_references if ref.get('type') == 'image']
        if image_references:
            print(Fore.CYAN + f"\n🖼️ 이미지 참조 {len(image_references)}개 감지됨 (필터링 대상)" + Style.RESET_ALL)
        
        # 참조 객체 ID 또는 제목에서 고유 식별자 추출 패턴
        # [1], [2] 같은 참조 표시나 "출처: XXX"와 같은 패턴 찾기
        ref_patterns = [
            r'\[(\d+)\]',  # [1], [2] 등의 패턴
            r'출처[:\s]+([^.\n]+)',  # "출처: XXX" 패턴
            r'참고[:\s]+([^.\n]+)',  # "참고: XXX" 패턴
            r'참조[:\s]+([^.\n]+)',  # "참조: XXX" 패턴
        ]
        
        # 텍스트에서 실제 사용된 참조 식별
        used_refs = set()
        pattern_matches = []
        
        # 참조 번호 패턴 ([1], [2] 등) 찾기
        print(Fore.CYAN + "\n🔎 참조 패턴 검색 결과:" + Style.RESET_ALL)
        for pattern in ref_patterns:
            matches = re.findall(pattern, response)
            if matches:
                pattern_matches.append((pattern, matches))
                print(f"  패턴 '{pattern}': {matches} 발견")
                for match in matches:
                    try:
                        # 숫자 패턴이면 인덱스로 처리
                        if match.isdigit():
                            ref_idx = int(match) - 1  # [1]은 인덱스 0
                            if 0 <= ref_idx < len(original_references):
                                used_refs.add(ref_idx)
                                # print(f"    인덱스 {ref_idx} ({ref_idx+1}번 참조) 추가됨")
                    except Exception as e:
                        print(f"    처리 오류: {e}")
        
        if not pattern_matches:
            print("  감지된 참조 패턴 없음")
        
        # 제목이나 URL 기반으로 직접 참조된 것 찾기
        print(Fore.CYAN + "\n🔍 내용 기반 참조 검색:" + Style.RESET_ALL)
        content_matched = False
        
        for i, ref in enumerate(original_references):
            ref_value = ref.get('value', '').lower()
            ref_title = ref.get('title', '').lower()
            
            # 참조 URL이나 제목이 응답에 포함되어 있는지 확인
            value_match = ref_value and ref_value in response.lower()
            title_match = ref_title and ref_title in response.lower()
            
            if value_match or title_match:
                used_refs.add(i)
                content_matched = True
                match_type = []
                if value_match: match_type.append("URL/값")
                if title_match: match_type.append("제목")
                
                print(f"  {i+1}번 참조: {', '.join(match_type)} 일치 (추가됨)")
        
        if not content_matched:
            print("  내용 기반으로 일치하는 참조 없음")
        
        # 사용된 참조 목록 생성
        filtered_references = []
        
        # 텍스트에 실제 언급된 참조만 추가 (이미지 자동 포함 X)
        for i in used_refs:
            if i < len(original_references):
                ref = original_references[i]
                if ref not in filtered_references:  # 중복 방지
                    filtered_references.append(ref)
        
        print(Fore.CYAN + f"\n🔍 최종 결과: 원본 참조 {len(original_references)}개 중 {len(filtered_references)}개 필터링됨" + Style.RESET_ALL)
        if filtered_references:
            print("📌 최종 선택된 참조:")
            for i, ref in enumerate(filtered_references):
                ref_type = ref.get('type', '알 수 없음')
                ref_title = ref.get('title', '제목 없음')
                print(f"  {i+1}. [{ref_type}] {ref_title}")
        
        return filtered_references
    
    def _build_messages(self, state: AgentState):
        """
        Build messages for the LLM
        
        Args:
            state: The current agent state
            
        Returns:
            List of message objects for the LLM
        """
        context, references, original_references = self._build_context(state)
        
        # Format references as a newline-separated string
        references_text = "\n".join(references) if references else ""

        # 메시지 히스토리 처리
        conversation = []
        for msg in state.message_history:
            if msg["role"] == "user":
                conversation.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                conversation.append(AIMessage(content=msg["content"]))
        
        # 현재 입력 메시지 추가
        conversation.append(HumanMessage(content=state.input))
        
        # Get messages from the prompt manager
        return prompt_manager.get_messages("responder",
            context=context,
            user_query=state.input,
            references=references_text,
            show_thought_process=self.show_thought_process,
            conversation=conversation
        )
    
    def _process_response(self, response: str) -> str:
        """
        Process the LLM response based on settings
        
        Args:
            response: Raw response from the LLM
            
        Returns:
            Processed response with thought process removed if needed
        """
        if not self.show_thought_process:
            # Remove thought process tags and content
            response = re.sub(r'<thought_process>.*?</thought_process>', '', response, flags=re.DOTALL)
            # Clean up excessive newlines
            response = re.sub(r'\n{3,}', '\n\n', response)
        
        return response.strip()
    
    async def __call__(self, state: AgentState):
        """
        Async generator for responding to queries
        
        Args:
            state: The current agent state
            
        Yields:
            Token chunks or final message with updated history
        """
        print(Fore.GREEN + "\n✨ Generating final response" + Style.RESET_ALL)
        start_time = time.time()
        response = ""
        raw_response = ""

        # Get context and references before streaming
        context, references, original_references = self._build_context(state)
        
        if state.plan.direct_response:
            # Split the direct response into chunks and yield each chunk
            response = state.plan.direct_response
            raw_response = response
            chunk_size = 100  # Define the chunk size
            for i in range(0, len(response), chunk_size):
                chunk = response[i:i + chunk_size]
                yield chunk
        else:
            messages = self._build_messages(state)
            
            # Stream the response
            async for chunk in self.model.astream(messages):
                if hasattr(chunk, 'content'):
                    if isinstance(chunk.content, list):
                        # Claude 3 format
                        for content_item in chunk.content:
                            if content_item.get('type') == 'text':
                                token = content_item.get('text', '')
                                if token:
                                    raw_response += token
                                    yield token
                    else:
                        token = chunk.content
                        if token:
                            raw_response += token
                            yield token
            
            # Process the final response to remove thought process if needed
            response = self._process_response(raw_response)
        
        # 최종 응답에서 실제 사용된 참조만 필터링
        filtered_references = self._filter_references_from_response(response, original_references)
        
        # Yield final message with history
        yield {
            'response': response,
            'raw_response': raw_response,
            'message_history': [*state.message_history, {
                "role": "assistant",
                "content": response
            }],
            'references': filtered_references  # 필터링된 참조 사용
        }
        
        elapsed_time = time.time() - start_time
        print(Fore.YELLOW + f"\n⏱️ Response generation took: {elapsed_time:.2f} seconds" + Style.RESET_ALL)

    async def acall(self, state: AgentState) -> Dict[str, Any]:
        """
        Non-streaming execution with complete response
        
        Args:
            state: The current agent state
            
        Returns:
            Dict containing updated state with response
        """
        # Build context and get references
        context, references, original_references = self._build_context(state)
        
        # Generate response
        response = await self.model.ainvoke(self._build_messages(state))
        raw_result = cast(str, response.content)
        result = self._process_response(raw_result)
        
        # 최종 응답에서 실제 사용된 참조만 필터링
        filtered_references = self._filter_references_from_response(result, original_references)
        
        # Update message history
        updated_message_history = [*state.message_history, {
            "role": "assistant",
            "content": result
        }]
        
        # Return state with response and references
        return {
            **state.model_dump(),
            "response": result,
            "raw_response": raw_result,
            "references": filtered_references,  # 필터링된 참조 사용
            "message_history": updated_message_history
        }