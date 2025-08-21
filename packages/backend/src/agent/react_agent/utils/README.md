# React Agent Utils - 로그 시스템

이 디렉토리는 React Agent의 로그 시스템과 유틸리티 함수들을 포함합니다.

## 📝 Colorama 로그 시스템

### 개요

새로운 로그 시스템은 `colorama`를 이용하여 색깔별로 구분된 보기 좋은 로그를 제공합니다:

- 🤖 **AI 응답** (초록색) - Agent의 최종 응답과 참조 정보
- 🔧 **도구 호출** (파란색) - 도구 호출 시 매개변수 정보  
- ✅ **도구 결과** (시안색) - 도구 실행 결과와 실행 시간
- ❌ **도구 에러** (빨간색) - 도구 실행 실패 시 에러 정보
- 💬 **대화 시작** (노란색) - 새로운 대화 세션 시작
- 🚀 **MCP 서비스** (초록/노란색) - MCP 서비스 상태 변경
- 🐛 **디버그 정보** (자홍색) - 개발용 디버그 데이터
- 📊 **상태 정보** (흰색) - 시스템 상태 정보

### 사용법

#### 1. 기본 사용

```python
from src.agent.react_agent.utils.logging_utils import (
    log_response, log_tool_call, log_tool_result, log_tool_error,
    log_conversation_start, log_mcp_status, log_debug_info, log_state_info
)

# AI 응답 로그
log_response("분석이 완료되었습니다.", references=[...])

# 도구 호출 로그
log_tool_call("hybrid_search", {"query": "안전성 분석", "limit": 10})

# 도구 결과 로그
log_tool_result("hybrid_search", result_data, execution_time=1.234)

# 에러 로그
log_tool_error("get_project_info", exception)
```

#### 2. 클래스 기반 사용

```python
from src.agent.react_agent.utils.logging_utils import ColoredLogger

# 커스텀 로거 생성
logger = ColoredLogger("MyAgent")

# 직접 메소드 호출
logger.log_response("응답 내용", references)
logger.log_tool_call("도구명", {"매개변수": "값"})
```

### 로그 타입별 상세 설명

#### 🤖 AI 응답 (`log_response`)
- **용도**: Agent의 최종 응답 출력
- **포함 정보**: 응답 텍스트, 참조 정보 목록
- **색상**: 초록색

#### 🔧 도구 호출 (`log_tool_call`) 
- **용도**: 도구 실행 전 호출 정보
- **포함 정보**: 도구명, 매개변수 JSON
- **색상**: 파란색

#### ✅ 도구 결과 (`log_tool_result`)
- **용도**: 도구 실행 완료 후 결과
- **포함 정보**: 도구명, 결과 데이터, 실행 시간
- **색상**: 시안색
- **특징**: 큰 결과는 자동으로 1000자로 제한

#### ❌ 도구 에러 (`log_tool_error`)
- **용도**: 도구 실행 실패 시 에러 정보
- **포함 정보**: 도구명, 에러 타입, 에러 메시지
- **색상**: 빨간색

#### 💬 대화 시작 (`log_conversation_start`)
- **용도**: 새로운 대화 세션 시작
- **포함 정보**: 사용자 메시지, 프로젝트 ID
- **색상**: 노란색

#### 🚀 MCP 서비스 (`log_mcp_status`)
- **용도**: MCP 서비스 상태 변경
- **포함 정보**: 상태, 도구 수, 세부사항
- **색상**: 시작/완료=초록색, 기타=노란색

#### 🐛 디버그 정보 (`log_debug_info`)
- **용도**: 개발/디버깅용 정보
- **포함 정보**: 제목, 데이터 객체
- **색상**: 자홍색
- **특징**: 딕셔너리/리스트는 JSON 형태로 출력

#### 📊 상태 정보 (`log_state_info`)
- **용도**: 시스템 현재 상태
- **포함 정보**: 상태 딕셔너리
- **색상**: 흰색

### React Agent 통합

React Agent에서는 다음과 같이 자동으로 로그가 생성됩니다:

1. **대화 시작**: `astream`/`ainvoke` 호출 시
2. **MCP 상태**: `startup`/`shutdown` 호출 시  
3. **도구 실행**: `_execute_tool` 호출 시
4. **AI 응답**: 최종 응답 생성 시
5. **디버그 정보**: `debug_mode=True`일 때

### 테스트

로그 시스템을 테스트하려면:

```bash
cd packages/backend
python src/agent/react_agent/utils/test_logging.py
```

### 로그 포맷

각 로그는 다음과 같은 형태로 출력됩니다:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[14:25:33.123] 🤖 AI 응답
응답 내용:
분석이 완료되었습니다.

참조 정보:
  [1] document: 안전성 보고서
  [2] image: 분석 결과 이미지
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 환경 설정

`colorama`가 설치되어 있어야 합니다:

```bash
pip install colorama
```

Windows에서는 자동으로 ANSI 색상 코드가 활성화됩니다.

### 커스터마이징

로그 색상이나 포맷을 변경하려면 `logging_utils.py`의 `ColoredLogger` 클래스를 수정하세요.

- `Fore.COLOR`: 텍스트 색상
- `Back.COLOR`: 배경 색상  
- `Style.BRIGHT`: 굵게 표시
- `Style.RESET_ALL`: 스타일 초기화

### 성능 고려사항

- 큰 데이터는 자동으로 잘려서 출력됩니다 (1000자 제한)
- JSON 직렬화는 한국어를 지원합니다 (`ensure_ascii=False`)
- 프로덕션 환경에서는 로그 레벨을 조정하여 성능을 최적화하세요 