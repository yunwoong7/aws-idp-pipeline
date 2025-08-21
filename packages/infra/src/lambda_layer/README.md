# AWS IDP AI Analysis - Lambda Layer

통합 Lambda Layer for AWS 서비스 접근을 위한 공통 라이브러리입니다.

## 구조

```
lambda_layer/
└── python/
    ├── common/
    │   ├── __init__.py              # 패키지 초기화 및 exports
    │   ├── aws_clients.py           # AWS 클라이언트 팩토리 (싱글톤)
    │   ├── dynamodb_service.py      # DynamoDB 통합 서비스  
    │   ├── opensearch_service.py    # OpenSearch 통합 서비스
    │   ├── s3_service.py           # S3 통합 서비스
    │   ├── activity_recorder.py     # 활동 기록 통합 서비스
    │   └── utils.py                # 공통 유틸리티 함수
    ├── requirements.txt             # 의존성 패키지
    └── README.md                   # 문서
```

## 주요 기능

### 1. AWS 클라이언트 팩토리 (`aws_clients.py`)
- 싱글톤 패턴으로 AWS 클라이언트 관리
- DynamoDB, S3, OpenSearch, Bedrock 클라이언트 제공
- 환경 변수 기반 설정 자동화

### 2. DynamoDB 서비스 (`dynamodb_service.py`)
- 5개 테이블 통합 관리 (activities, documents, elements, pages, projects)
- CRUD 작업 표준화
- GSI 쿼리 패턴 통일
- 자동 타임스탬프 관리

### 3. OpenSearch 서비스 (`opensearch_service.py`)
- 통합 검색 및 인덱싱
- Bedrock Titan 임베딩 자동 생성
- 하이브리드 검색 (텍스트 + 벡터)
- 인덱스 관리 자동화

### 4. S3 서비스 (`s3_service.py`)
- 파일 업로드/다운로드 통합
- Pre-signed URL 생성
- 이미지 처리 (리사이징, Base64 변환)
- 배치 작업 지원

### 5. 활동 기록 서비스 (`activity_recorder.py`)
- 통합 활동 로깅
- 프로젝트/문서/페이지 활동 추적
- 표준화된 활동 타입 및 상태

## 사용법

### 기본 사용

```python
from common import DynamoDBService, OpenSearchService, S3Service, ActivityRecorder

# 서비스 초기화
db = DynamoDBService()
search = OpenSearchService()
s3 = S3Service()
activity = ActivityRecorder()

# DynamoDB 사용
project = db.create_item('projects', {
    'id': 'project-123',
    'name': 'My Project',
    'status': 'active'
})

# OpenSearch 사용
search.index_document({
    'content': 'Document content...',
    'project_id': 'project-123'
})

# S3 사용
s3.upload_file(file_content, 'path/to/file.pdf')

# 활동 기록
activity.record_project_created('project-123', 'My Project')
```

### 환경 변수

```bash
# 필수 환경 변수
AWS_REGION=us-west-2
AWS_ACCOUNT_ID=057336397075
ENVIRONMENT=dev

# OpenSearch
OPENSEARCH_ENDPOINT=https://your-opensearch-domain.us-west-2.es.amazonaws.com
OPENSEARCH_INDEX_NAME=aws-idp-ai-analysis

# S3
DOCUMENTS_BUCKET_NAME=your-documents-bucket
```

## 배포

Lambda Layer를 배포하려면:

```bash
# 의존성 설치
cd lambda_layer/python
pip install -r requirements.txt -t .

# ZIP 파일 생성
cd ..
zip -r lambda-layer.zip python/

# AWS CLI로 배포
aws lambda publish-layer-version \
  --layer-name aws-idp-ai-common \
  --zip-file fileb://lambda-layer.zip \
  --compatible-runtimes python3.9 python3.10 python3.11
```

## Lambda 함수에서 사용

```python
# Lambda 함수 핸들러 예시
import json
from common import DynamoDBService, handle_lambda_error, create_success_response

def lambda_handler(event, context):
    try:
        db = DynamoDBService()
        
        # 비즈니스 로직
        result = db.get_item('projects', {'id': 'project-123'})
        
        return create_success_response(result)
        
    except Exception as e:
        return handle_lambda_error(e)
```

## 이점

1. **코드 중복 제거**: ~70% 코드 중복 감소
2. **유지보수성 향상**: 중앙 집중식 관리
3. **일관성**: 표준화된 에러 처리 및 로깅
4. **성능**: 클라이언트 재사용 및 최적화
5. **확장성**: 새로운 서비스 추가 용이