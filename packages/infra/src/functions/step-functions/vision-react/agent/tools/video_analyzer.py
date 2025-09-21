"""
VideoAnalyzerTool - 동영상 챕터별 Bedrock AI 분석 도구
TwelveLabs Pegasus 모델을 사용하여 특정 시간 구간의 동영상 내용을 상세 분석
"""

import json
import logging
import os
import sys
from typing import Dict, Any, Optional, ClassVar
from pydantic import BaseModel, Field

# Common module imports
sys.path.append('/opt/python')
from common import AWSClientFactory

from .base import BaseTool
from prompts import prompt_manager

logger = logging.getLogger(__name__)


class AnalyzeVideoInput(BaseModel):
    """Analyze video using an AI model."""
    query: str = Field(
        title="Analysis Query", 
        description="Question about the information to extract from the video chapter (AI model will analyze this question)"
    )


class VideoAnalyzerTool(BaseTool):
    """Video analysis tool with Agent context integration
    Analyze video chapters using TwelveLabs Pegasus model with conversation history context.
    
    Args:
        query: Question about the information to extract from the video chapter
        
    Returns:
        ToolResult: Result of the video chapter analysis
    """
    
    def __init__(self):
        super().__init__()
        
        self.model_id = os.environ.get('BEDROCK_VIDEO_MODEL_ID', 'us.twelvelabs.pegasus-1-2-v1:0')
        self.bucket_owner_id = os.environ.get('BUCKET_OWNER_ACCOUNT_ID', '')
        
        # Initialize AWS client
        try:
            self.bedrock_client = AWSClientFactory.get_bedrock_runtime_client()
            logger.info("Bedrock client initialization completed")
        except Exception as e:
            logger.error(f"Failed to initialize Bedrock client: {str(e)}")
            raise
            
        if not self.bucket_owner_id:
            logger.warning("⚠️ BUCKET_OWNER_ACCOUNT_ID 환경변수가 설정되지 않음")
    
    def get_schema(self) -> type:
        return AnalyzeVideoInput

    def _get_agent_context_info(self, **kwargs) -> Dict[str, Any]:
        """Get agent context information from kwargs"""
        return {
            "index_id": kwargs.get("index_id", "unknown"),
            "document_id": kwargs.get("document_id", "unknown"),
            "segment_id": kwargs.get("segment_id", "unknown"),
            "file_uri": kwargs.get("file_path") or kwargs.get("file_uri"),
            "start_timecode_smpte": kwargs.get("start_timecode_smpte"),
            "end_timecode_smpte": kwargs.get("end_timecode_smpte"),
            "segment_type": kwargs.get("segment_type"),
            "segment_index": kwargs.get("segment_index"),
            "thread_id": kwargs.get("thread_id", "unknown"),
            "user_query": kwargs.get("user_query", ""),
            "previous_analysis_context": kwargs.get("previous_analysis_context", ""),
            "image_understanding": kwargs.get("image_understanding", ""),
        }

    def execute(self, query: str = None, **kwargs) -> dict:
        """Execute video chapter analysis"""
        try:
            # Get information from Agent context
            agent_context = self._get_agent_context_info(**kwargs)
            document_id = agent_context.get('document_id', 'unknown')
            segment_id = agent_context.get('segment_id', 'unknown')
            file_uri = agent_context.get('file_uri')
            start_timecode = agent_context.get('start_timecode_smpte')
            end_timecode = agent_context.get('end_timecode_smpte')
            segment_type = agent_context.get('segment_type')
            
            logger.info(f"🎬 Video analysis started")
            logger.info(f"Document ID: {document_id}")
            logger.info(f"Segment ID: {segment_id}")
            logger.info(f"File URI: {file_uri}")
            logger.info(f"Segment Type: {segment_type}")
            logger.info(f"Start Timecode: {start_timecode}")
            logger.info(f"End Timecode: {end_timecode}")
            
            # Debug: Log entire Agent context
            logger.info(f"🔍 Agent context contents:")
            for key, value in agent_context.items():
                if key != "tool_registry_instance":
                    logger.info(f"  - {key}: {value}")
            
            # Check if this is a video chapter
            if segment_type != 'CHAPTER':
                logger.info(f"⏭️ Skipping non-video segment (type: {segment_type})")
                return self._create_success_result(
                    "세그먼트가 동영상 챕터가 아니므로 건너뜁니다.",
                    {
                        "analysis_type": "skip",
                        "segment_type": segment_type,
                        "segment_id": segment_id,
                        "reason": "Not a video chapter"
                    }
                )
            
            # Validate required information (check for both None and empty string)
            if not all([file_uri and file_uri.strip(), start_timecode and start_timecode.strip(), end_timecode and end_timecode.strip()]):
                missing = []
                if not file_uri or not file_uri.strip(): missing.append('file_uri')
                if not start_timecode or not start_timecode.strip(): missing.append('start_timecode_smpte')
                if not end_timecode or not end_timecode.strip(): missing.append('end_timecode_smpte')
                
                error_msg = f"동영상 분석에 필요한 정보가 누락됨: {missing}"
                logger.error(f"❌ {error_msg}")
                return self._create_error_result(error_msg)
            
            # Use planned query if available, otherwise use default
            planned_query = kwargs.get('planned_query', '')
            if not query:
                if planned_query:
                    query = planned_query
                else:
                    query = f"동영상의 {start_timecode}부터 {end_timecode}까지의 구간을 상세히 분석해주세요."
            
            # Log query content
            logger.info(f"Video analysis query: {query}")
            
            # Skip previous analysis context for video to avoid token limit (max 2000 tokens)
            # Video analysis should be self-contained per chapter
            logger.info("🔍 Skipping previous analysis context for video (token limit: 2000)")

            # Remove previous_analysis_context from kwargs to avoid duplicate argument error
            kwargs_clean = {k: v for k, v in kwargs.items() if k != 'previous_analysis_context'}

            # Generate analysis prompt without previous context
            analysis_prompt = self._generate_analysis_prompt(
                start_timecode, end_timecode, query, None, **kwargs_clean
            )
            
            # Analyze video with Bedrock
            analysis_result = self._analyze_video_with_bedrock(file_uri, analysis_prompt)
            
            if not analysis_result:
                return self._create_error_result("Bedrock video analysis failed")
            
            # Create references for video chapter
            references = []
            references.append(self.create_reference(
                ref_type="video",
                value=file_uri,
                title=f"Video Chapter {start_timecode}-{end_timecode}",
                description=f"Video chapter from {start_timecode} to {end_timecode}"
            ))
            
            # Create result data
            results = [{
                "analysis_type": "video_analyzer",
                "segment_id": segment_id,
                "document_id": document_id,
                "file_uri": file_uri,
                "start_timecode_smpte": start_timecode,
                "end_timecode_smpte": end_timecode,
                "query": query,
                "ai_response": analysis_result,
                "model_version": self.model_id,
                "token_usage": getattr(self, '_last_token_usage', None)
            }]
            
            logger.info(f"✅ Video chapter analysis successful: {segment_id}")
            logger.info(f"Analysis result: {analysis_result}")
            
            # Return in new ToolResult format
            return {
                "success": True,
                "count": len(results),
                "results": results,
                "references": references,
                "llm_text": analysis_result,
                "error": None
            }
            
        except Exception as e:
            error_msg = f"Video analysis failed: {str(e)}"
            logger.error(error_msg)
            return self._create_error_result(error_msg)

    def _generate_analysis_prompt(
        self,
        start_timecode: str,
        end_timecode: str,
        query: str,
        previous_analysis_context: str,
        **kwargs
    ) -> str:
        """
        YAML 기반 동적 프롬프트 생성
        """
        # Get context from kwargs
        segment_type = kwargs.get('segment_type', 'CHAPTER')
        file_uri = kwargs.get('file_path') or kwargs.get('file_uri', 'Unknown')

        # Get current date for context
        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d")

        # For video analysis, always set empty previous context to avoid token limit
        if previous_analysis_context is None:
            previous_analysis_context = ""

        # Get prompts from YAML
        prompts = prompt_manager.get_prompt(
            'video_analyzer',
            'video_chapter_analysis',
            segment_type=segment_type,
            start_timecode_smpte=start_timecode,
            end_timecode_smpte=end_timecode,
            file_uri=file_uri,
            previous_analysis_context=previous_analysis_context,
            query=query,
            current_date=current_date
        )

        logger.info(f"📝 Video analysis prompt generated: {start_timecode} ~ {end_timecode}")
        return prompts['user_prompt']

    def _analyze_video_with_bedrock(self, file_uri: str, prompt: str) -> Optional[str]:
        """
        Bedrock을 사용한 동영상 분석
        """
        try:
            logger.info(f"🤖 Bedrock 동영상 분석 시작: {self.model_id}")
            
            # S3 URI에서 bucket과 key 추출
            if not file_uri.startswith('s3://'):
                raise ValueError(f"잘못된 S3 URI 형식: {file_uri}")
            
            # Bedrock 요청 본문 구성
            request_body = {
                "inputPrompt": prompt,
                "mediaSource": {
                    "s3Location": {
                        "uri": file_uri,
                        "bucketOwner": self.bucket_owner_id
                    }
                },
                "temperature": 0
            }
            
            # Bedrock 동영상 분석 API 호출
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json"
            )
            
            # 응답 처리
            response_body = json.loads(response['body'].read())
            
            # 응답에서 분석 결과 추출 (TwelveLabs 모델은 'message' 필드 사용)
            analysis_result = response_body.get('message', response_body.get('outputText', ''))
            
            # 토큰 사용량 로깅 (헤더 또는 body.usage)
            try:
                headers = response.get('ResponseMetadata', {}).get('HTTPHeaders', {}) or {}
                input_tokens = headers.get('x-amzn-bedrock-input-token-count')
                output_tokens = headers.get('x-amzn-bedrock-output-token-count')
                total_tokens = headers.get('x-amzn-bedrock-total-token-count')
                if (input_tokens is None or output_tokens is None) and isinstance(response_body, dict) and response_body.get('usage'):
                    usage = response_body['usage']
                    input_tokens = input_tokens or usage.get('input_tokens')
                    output_tokens = output_tokens or usage.get('output_tokens')
                    total_tokens = total_tokens or usage.get('total_tokens')
                logger.info(f"🔢 Bedrock Token Usage (video): input={input_tokens}, output={output_tokens}, total={total_tokens}")
                self._last_token_usage = {
                    'input_tokens': int(input_tokens) if input_tokens is not None and str(input_tokens).isdigit() else None,
                    'output_tokens': int(output_tokens) if output_tokens is not None and str(output_tokens).isdigit() else None,
                    'total_tokens': int(total_tokens) if total_tokens is not None and str(total_tokens).isdigit() else None,
                }
            except Exception as token_log_err:
                logger.debug(f"Token usage logging skipped (video): {str(token_log_err)}")
            
            if not analysis_result:
                logger.error("❌ Bedrock 응답에서 분석 결과를 찾을 수 없음")
                logger.error(f"❌ 전체 응답: {response_body}")
                return None
            
            logger.info(f"✅ Bedrock 동영상 분석 완료: {len(analysis_result)} 문자")
            return analysis_result
            
        except Exception as e:
            logger.error(f"❌ Bedrock 동영상 분석 실패: {str(e)}")
            return None
    
    def _create_success_result(self, message: str, data: Dict[str, Any]) -> dict:
        """Create success result"""
        return {
            "success": True,
            "count": 1,
            "results": [data],
            "references": [],
            "llm_text": message,
            "error": None
        }
    
    def _create_error_result(self, message: str) -> dict:
        """Create error result"""
        return {
            "success": False,
            "count": 0,
            "results": [],
            "references": [],
            "llm_text": "",
            "error": message
        }
