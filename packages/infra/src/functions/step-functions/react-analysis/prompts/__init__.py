# src/agent/prompts/__init__.py

import os
import yaml
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from langchain_core.messages import SystemMessage, HumanMessage

class PromptLoader:
    """YAML 파일에서 프롬프트를 로드하는 클래스"""
    
    def __init__(self, prompts_dir: Union[str, Path]):
        self.prompts_dir = Path(prompts_dir)
        self.prompts_cache = {}
    
    def load_prompt(self, name: str, variant: Optional[str] = None) -> Dict[str, Any]:
        """
        프롬프트 YAML 파일 로드
        
        Args:
            name: 프롬프트 이름 (파일명)
            variant: 프롬프트 변형 이름 (없으면 기본 사용)
            
        Returns:
            Dict: 로드된 프롬프트 데이터
        """
        # 캐시 키 생성
        cache_key = f"{name}_{variant or 'default'}"
        
        # 이미 캐시된 프롬프트가 있으면 반환
        if cache_key in self.prompts_cache:
            return self.prompts_cache[cache_key]
        
        # 기본 프롬프트 파일 경로
        file_path = self.prompts_dir / f"{name}.yaml"
        
        # 변형 프롬프트 파일 경로
        if variant and not file_path.exists():
            variant_path = self.prompts_dir / "variants" / f"{name}_{variant}.yaml"
            if variant_path.exists():
                file_path = variant_path
        
        # 파일이 존재하는지 확인
        if not file_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {file_path}")
        
        # YAML 파일 로드
        with open(file_path, 'r', encoding='utf-8') as file:
            prompt_data = yaml.safe_load(file)
        
        # 변형 적용
        if variant and "variants" in prompt_data and variant in prompt_data["variants"]:
            variant_data = prompt_data["variants"][variant]
            
            # 변형 데이터 병합
            for key, value in variant_data.items():
                if key.endswith('_append') and key[:-7] in prompt_data:
                    # _append 접미사가 있는 필드는 기존 내용에 추가
                    base_key = key[:-7]
                    prompt_data[base_key] = prompt_data[base_key] + "\n" + value
                else:
                    # 일반 필드는 덮어쓰기
                    prompt_data[key] = value
        
        # variants 필드 제거 (사용할 필요 없음)
        if "variants" in prompt_data:
            del prompt_data["variants"]
        
        # 캐시에 저장
        self.prompts_cache[cache_key] = prompt_data
        return prompt_data
    
    def format_prompt(self, prompt_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        프롬프트 데이터의 템플릿 필드를 포맷팅
        
        Args:
            prompt_data: 로드된 프롬프트 데이터
            **kwargs: 템플릿 변수
            
        Returns:
            Dict: 포맷팅된 프롬프트
        """
        result = {}
        
        # 필수 변수 확인
        if "variables" in prompt_data:
            for var in prompt_data["variables"]:
                if var.get("required", False) and var["name"] not in kwargs:
                    raise ValueError(f"Missing required variable: {var['name']}")
        
        # 조건부 블록 및 변수 포맷팅 처리
        for key, value in prompt_data.items():
            if isinstance(value, str):
                # 조건부 블록 처리
                processed_value = self._process_conditional_blocks(value, kwargs)
                
                # 이중 중괄호 변수 처리 ({{VARIABLE}} 형식)
                for var_name, var_value in kwargs.items():
                    processed_value = processed_value.replace(f"{{{{{var_name}}}}}", str(var_value))
                
                try:
                    # 일반 변수 대체 ({VARIABLE} 형식) - 템플릿에 실제 단일 중괄호 플레이스홀더가 있을 때만 수행
                    # 원본 값 기준으로 단일 중괄호 패턴 존재 여부 확인 (이중 중괄호는 제외)
                    if re.search(r'{(?!{)[^{}]+}', value):
                        result[key] = processed_value.format(**kwargs)
                    else:
                        # 단일 중괄호 플레이스홀더가 없다면, 이미 {{VAR}} 치환만으로 충분하므로 그대로 사용
                        result[key] = processed_value
                except (KeyError, ValueError):
                    # 치환 중 오류가 발생하면 포맷을 적용하지 않고 원문을 사용 (분석 텍스트 내 중괄호 안전성 보장)
                    result[key] = processed_value
            else:
                result[key] = value
        
        return result
    
    def _process_conditional_blocks(self, text: str, context: Dict[str, Any]) -> str:
        """
        조건부 블록 {{#if condition}}...{{else}}...{{/if}} 처리
        
        Args:
            text: 처리할 텍스트
            context: 조건 변수를 포함한 컨텍스트
            
        Returns:
            str: 조건부 블록이 처리된 텍스트
        """
        # if 블록 찾기
        pattern = r'{{#if (\w+)}}(.*?)(?:{{else}}(.*?))?{{/if}}'
        
        def replace_conditional(match):
            condition_var = match.group(1)
            if_content = match.group(2)
            else_content = match.group(3) or ''
            
            # 조건 평가
            if context.get(condition_var):
                return if_content
            else:
                return else_content
        
        # 모든 조건부 블록 처리
        return re.sub(pattern, replace_conditional, text, flags=re.DOTALL)


class PromptManager:
    """프롬프트 관리 클래스"""
    
    def __init__(self, prompts_dir: Union[str, Path]):
        self.loader = PromptLoader(prompts_dir)
        self.current_variants = {}  
    
    def get_prompt(self, name: str, variant: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        포맷팅된 프롬프트 가져오기
        
        Args:
            name: 프롬프트 이름
            variant: 프롬프트 변형 (없으면 현재 설정된 변형 또는 기본값 사용)
            **kwargs: 템플릿 변수
            
        Returns:
            Dict: 포맷팅된 프롬프트
        """
        # 변형이 지정되지 않았으면 현재 설정된 변형 사용
        if variant is None:
            variant = self.current_variants.get(name)
        
        # 프롬프트 로드
        prompt_data = self.loader.load_prompt(name, variant)
        
        # 현재 변형 업데이트
        if variant:
            self.current_variants[name] = variant
        
        # 프롬프트 포맷팅
        return self.loader.format_prompt(prompt_data, **kwargs)
    
    def set_variant(self, name: str, variant: Optional[str] = None):
        """
        프롬프트 변형 설정
        
        Args:
            name: 프롬프트 이름
            variant: 프롬프트 변형 (None이면 기본 변형으로 재설정)
        """
        if variant is None:
            # 변형 설정 제거
            if name in self.current_variants:
                del self.current_variants[name]
        else:
            # 변형 설정
            self.current_variants[name] = variant
        
        return self
    
    def get_messages(self, name: str, variant: Optional[str] = None, **kwargs) -> List:
        """
        LangChain 호환 메시지 리스트 생성
        
        Args:
            name: 프롬프트 이름
            variant: 프롬프트 변형
            **kwargs: 템플릿 변수
            
        Returns:
            List: LangChain 메시지 객체 리스트
        """
        prompt_data = self.get_prompt(name, variant, **kwargs)
        
        messages = []
        
        # 시스템 프롬프트 추가
        if "system_prompt" in prompt_data:
            messages.append(SystemMessage(content=prompt_data["system_prompt"]))
        
        # 인스트럭션 추가
        if "instruction" in prompt_data:
            messages.append(HumanMessage(content=prompt_data["instruction"]))
        
        return messages

    def clear_cache(self):
        """프롬프트 캐시 초기화"""
        self.loader.prompts_cache.clear()
        
    def toggle_variant(self, name: str, variant: str, condition: bool):
        """
        조건에 따라 프롬프트 변형을 설정하거나 해제
        
        Args:
            name: 프롬프트 이름
            variant: 프롬프트 변형
            condition: 조건 (True면 변형 설정, False면 기본으로 되돌림)
        """
        if condition:
            self.set_variant(name, variant)
        else:
            self.set_variant(name, None)
        
        return self


# Lambda 환경에서 사용할 prompt_manager 인스턴스 생성
current_dir = Path(__file__).parent
prompt_manager = PromptManager(current_dir)

# manager를 바로 사용할 수 있도록 export
__all__ = ['PromptLoader', 'PromptManager', 'prompt_manager'] 