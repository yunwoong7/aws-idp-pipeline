#!/usr/bin/env python3
"""
로그 시스템 테스트 스크립트
새로운 colorama 로그 시스템의 기능을 테스트합니다.
"""

import sys
import time
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.agent.react_agent.utils.logging_utils import (
    log_response, log_tool_call, log_tool_result, log_tool_error,
    log_conversation_start, log_mcp_status, log_debug_info, log_state_info
)

def test_all_logs():
    """모든 로그 타입을 테스트합니다."""
    print("🧪 로그 시스템 테스트 시작\n")
    
    # 1. 대화 시작 로그
    log_conversation_start(
        "안녕하세요! 프로젝트의 문서들을 분석해주세요.",
        "test-project-123"
    )
    time.sleep(1)
    
    # 2. MCP 서비스 상태 로그
    log_mcp_status(
        "시작 완료", 
        tool_count=15,
        details="모든 MCP 도구가 성공적으로 로드되었습니다"
    )
    time.sleep(1)
    
    # 3. 도구 호출 로그
    log_tool_call("hybrid_search", {
        "query": "구조 안전성 분석",
        "project_id": "test-project-123",
        "limit": 10
    })
    time.sleep(1)
    
    # 4. 도구 실행 결과 로그
    tool_result = {
        "status": "success",
        "data": {
            "results": [
                {
                    "title": "구조 안전성 보고서",
                    "content": "건물의 구조적 안전성을 평가한 결과...",
                    "score": 0.95,
                    "file_uri": "https://example.com/report.pdf"
                }
            ]
        },
        "message": "검색이 성공적으로 완료되었습니다"
    }
    log_tool_result("hybrid_search", tool_result, execution_time=1.234)
    time.sleep(1)
    
    # 5. 도구 에러 로그
    try:
        raise ValueError("프로젝트 ID가 유효하지 않습니다")
    except Exception as e:
        log_tool_error("get_project_info", e)
    time.sleep(1)
    
    # 6. 디버그 정보 로그
    log_debug_info("StateManager 상태", {
        "project_id": "test-project-123",
        "context": {
            "user_id": "user-456",
            "session_id": "session-789"
        },
        "tool_count": 15,
        "active_conversations": 3
    })
    time.sleep(1)
    
    # 7. 상태 정보 로그
    log_state_info({
        "current_step": 5,
        "total_steps": 10,
        "project_id": "test-project-123",
        "message_count": 12,
        "tool_calls_made": 3
    })
    time.sleep(1)
    
    # 8. AI 응답 로그 (참조 포함)
    references = [
        {
            "type": "document",
            "title": "구조 안전성 보고서",
            "value": "https://example.com/safety-report.pdf"
        },
        {
            "type": "image",
            "title": "구조 도면 분석 결과",
            "value": "https://example.com/analysis-image.png"
        }
    ]
    
    response_text = """프로젝트의 구조 안전성을 분석한 결과, 전반적으로 양호한 상태입니다[1]. 

주요 발견사항:
- 구조적 강도: 기준치의 120% 수준으로 안전함
- 내진 설계: 규모 7.0 지진까지 견딜 수 있는 구조
- 재료 품질: 모든 재료가 KS 규격을 만족함

자세한 분석 결과는 첨부된 이미지를 참조하세요[2]."""

    log_response(response_text, references)
    
    print("\n🎉 로그 시스템 테스트 완료!")
    print("📝 위의 로그들이 색깔별로 구분되어 보기 좋게 출력되었는지 확인하세요.")

if __name__ == "__main__":
    test_all_logs() 