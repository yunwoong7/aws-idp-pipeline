import logging
import json
from typing import Any, Dict, List, Optional
from colorama import Fore, Back, Style, init
from datetime import datetime

# colorama 초기화
init(autoreset=True)

class ColoredLogger:
    """컬러 로그 포맷터"""
    
    def __init__(self, logger_name: str = __name__):
        self.logger = logging.getLogger(logger_name)
    
    def _get_timestamp(self) -> str:
        """현재 시간 스탬프 반환"""
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]
    
    def _create_box(self, title: str, content: str, color: str = Fore.WHITE, width: int = 80) -> str:
        """박스 형태의 로그 메시지 생성"""
        # 상단 테두리
        top_border = "┌" + "─" * (width - 2) + "┐"
        # 하단 테두리
        bottom_border = "└" + "─" * (width - 2) + "┘"
        # 제목 라인
        title_line = f"│ {color}{Style.BRIGHT}{title}{Style.RESET_ALL}" + " " * (width - len(title) - 3) + "│"
        
        # 내용을 라인별로 분할
        content_lines = []
        for line in content.split('\n'):
            while len(line) > width - 4:
                content_lines.append(f"│ {line[:width-4]} │")
                line = line[width-4:]
            if line:
                content_lines.append(f"│ {line}" + " " * (width - len(line) - 3) + "│")
        
        # 빈 라인이 없으면 추가
        if not content_lines:
            content_lines.append(f"│" + " " * (width - 2) + "│")
        
        # 모든 라인 조합
        box_lines = [top_border, title_line] + content_lines + [bottom_border]
        return color + "\n".join(box_lines) + Style.RESET_ALL
    
    def _create_section(self, title: str, content: str, color: str = Fore.WHITE) -> str:
        """섹션 형태의 로그 메시지 생성"""
        timestamp = self._get_timestamp()
        separator = "━" * 60
        header = f"{color}{Style.BRIGHT}[{timestamp}] {title}{Style.RESET_ALL}"
        return f"\n{color}{separator}{Style.RESET_ALL}\n{header}\n{content}\n{color}{separator}{Style.RESET_ALL}"
    
    def log_response(self, response: str, references: Optional[List[Dict]] = None):
        """AI 응답 로그"""
        content = f"응답 내용:\n{response}"
        
        if references:
            content += f"\n\n참조 정보:\n"
            for i, ref in enumerate(references, 1):
                ref_type = ref.get('type', 'unknown')
                title = ref.get('title', 'No title')
                content += f"  [{i}] {ref_type}: {title}\n"
        
        formatted_log = self._create_section("🤖 AI 응답", content, Fore.GREEN)
        print(formatted_log)
        self.logger.info(f"AI Response: {response[:100]}..." if len(response) > 100 else response)
    
    def log_tool_call(self, tool_name: str, tool_args: Dict[str, Any]):
        """도구 호출 로그"""
        args_str = json.dumps(tool_args, ensure_ascii=False, indent=2)
        content = f"도구명: {tool_name}\n매개변수:\n{args_str}"
        
        formatted_log = self._create_section("🔧 도구 호출", content, Fore.BLUE)
        print(formatted_log)
        self.logger.info(f"Tool Call: {tool_name} with args: {tool_args}")
    
    def log_tool_result(self, tool_name: str, result: Any, execution_time: Optional[float] = None):
        """도구 실행 결과 로그"""
        # 결과를 문자열로 변환
        if isinstance(result, dict):
            result_str = json.dumps(result, ensure_ascii=False, indent=2)
        elif isinstance(result, (list, tuple)):
            result_str = json.dumps(list(result), ensure_ascii=False, indent=2)
        else:
            result_str = str(result)
        
        # 결과가 너무 길면 자르기
        if len(result_str) > 1000:
            result_str = result_str[:1000] + "\n... (결과가 잘렸습니다)"
        
        content = f"도구명: {tool_name}\n실행 결과:\n{result_str}"
        
        if execution_time is not None:
            content += f"\n실행 시간: {execution_time:.3f}초"
        
        formatted_log = self._create_section("✅ 도구 결과", content, Fore.CYAN)
        print(formatted_log)
        self.logger.info(f"Tool Result: {tool_name} completed")
    
    def log_tool_error(self, tool_name: str, error: Exception):
        """도구 실행 에러 로그"""
        content = f"도구명: {tool_name}\n에러 유형: {type(error).__name__}\n에러 메시지: {str(error)}"
        
        formatted_log = self._create_section("❌ 도구 에러", content, Fore.RED)
        print(formatted_log)
        self.logger.error(f"Tool Error: {tool_name} failed with {type(error).__name__}: {error}")
    
    def log_conversation_start(self, user_message: str, project_id: Optional[str] = None):
        """대화 시작 로그"""
        content = f"사용자 메시지: {user_message}"
        if project_id:
            content += f"\n프로젝트 ID: {project_id}"
        
        formatted_log = self._create_section("💬 대화 시작", content, Fore.YELLOW)
        print(formatted_log)
        self.logger.info(f"Conversation started with message: {user_message[:50]}...")
    
    def log_mcp_status(self, status: str, tool_count: Optional[int] = None, details: str = ""):
        """MCP 서비스 상태 로그"""
        content = f"상태: {status}"
        if tool_count is not None:
            content += f"\n로드된 도구 수: {tool_count}개"
        if details:
            content += f"\n세부사항: {details}"
        
        color = Fore.GREEN if "시작" in status or "완료" in status else Fore.YELLOW
        formatted_log = self._create_section("🚀 MCP 서비스", content, color)
        print(formatted_log)
        self.logger.info(f"MCP Status: {status}")
    
    def log_debug_info(self, title: str, data: Any):
        """디버그 정보 로그"""
        if isinstance(data, (dict, list)):
            data_str = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            data_str = str(data)
        
        content = f"디버그 데이터:\n{data_str}"
        formatted_log = self._create_section(f"🐛 {title}", content, Fore.MAGENTA)
        print(formatted_log)
        self.logger.debug(f"Debug Info: {title}")
    
    def log_state_info(self, state_info: Dict[str, Any]):
        """상태 정보 로그"""
        content = "현재 상태:\n"
        for key, value in state_info.items():
            content += f"  {key}: {value}\n"
        
        formatted_log = self._create_section("📊 상태 정보", content, Fore.WHITE)
        print(formatted_log)
        self.logger.info("State information logged")

# 전역 로거 인스턴스
colored_logger = ColoredLogger("ReactAgent")

# 편의 함수들
def log_response(response: str, references: Optional[List[Dict]] = None):
    """AI 응답 로그 (편의 함수)"""
    colored_logger.log_response(response, references)

def log_tool_call(tool_name: str, tool_args: Dict[str, Any]):
    """도구 호출 로그 (편의 함수)"""
    colored_logger.log_tool_call(tool_name, tool_args)

def log_tool_result(tool_name: str, result: Any, execution_time: Optional[float] = None):
    """도구 실행 결과 로그 (편의 함수)"""
    colored_logger.log_tool_result(tool_name, result, execution_time)

def log_tool_error(tool_name: str, error: Exception):
    """도구 실행 에러 로그 (편의 함수)"""
    colored_logger.log_tool_error(tool_name, error)

def log_conversation_start(user_message: str, project_id: Optional[str] = None):
    """대화 시작 로그 (편의 함수)"""
    colored_logger.log_conversation_start(user_message, project_id)

def log_mcp_status(status: str, tool_count: Optional[int] = None, details: str = ""):
    """MCP 서비스 상태 로그 (편의 함수)"""
    colored_logger.log_mcp_status(status, tool_count, details)

def log_debug_info(title: str, data: Any):
    """디버그 정보 로그 (편의 함수)"""
    colored_logger.log_debug_info(title, data)

def log_state_info(state_info: Dict[str, Any]):
    """상태 정보 로그 (편의 함수)"""
    colored_logger.log_state_info(state_info) 