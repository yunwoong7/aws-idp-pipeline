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

from .base import BaseTool, ToolResult
from .state_aware_base import StateAwareBaseTool

logger = logging.getLogger(__name__)


class AnalyzeVideoInput(BaseModel):
    """Analyze video using an AI model."""
    query: str = Field(
        title="Analysis Query", 
        description="Question about the information to extract from the video chapter (AI model will analyze this question)"
    )


class VideoAnalyzerTool(StateAwareBaseTool):
    """Video analysis tool with Agent context integration
    Analyze video chapters using TwelveLabs Pegasus model with conversation history context.
    
    Args:
        query: Question about the information to extract from the video chapter
        
    Returns:
        ToolResult: Result of the video chapter analysis
    """
    
    supports_agent_context: ClassVar[bool] = True
    
    def __init__(self):
        super().__init__()
        
        # Use object.__setattr__ to bypass Pydantic field validation for instance attributes
        object.__setattr__(self, 'model_id', os.environ.get('BEDROCK_VIDEO_MODEL_ID', 'us.twelvelabs.pegasus-1-2-v1:0'))
        object.__setattr__(self, 'bucket_owner_id', os.environ.get('BUCKET_OWNER_ACCOUNT_ID', ''))
        
        # Initialize AWS client
        try:
            object.__setattr__(self, 'bedrock_client', AWSClientFactory.get_bedrock_runtime_client())
            logger.info("Bedrock client initialization completed")
        except Exception as e:
            logger.error(f"Failed to initialize Bedrock client: {str(e)}")
            raise
            
        if not self.bucket_owner_id:
            logger.warning("⚠️ BUCKET_OWNER_ACCOUNT_ID 환경변수가 설정되지 않음")
    
    def get_schema(self) -> type:
        return AnalyzeVideoInput

    def _get_agent_context_info(self) -> Dict[str, Any]:
        """Get agent context information (LangGraph State based)"""
        try:
            # Use StateAwareBaseTool's get_agent_context
            agent_context = self.get_agent_context()
            
            # Check if necessary fields exist and set default values
            # Extract conversation_history from State's messages
            conversation_history = []
            if hasattr(self, '_state') and self._state and 'messages' in self._state:
                for msg in self._state['messages']:
                    if hasattr(msg, 'content') and hasattr(msg, '__class__'):
                        msg_type = msg.__class__.__name__
                        if msg_type == 'HumanMessage':
                            conversation_history.append({
                                "role": "user", 
                                "content": str(msg.content)
                            })
                        elif msg_type == 'AIMessage':
                            conversation_history.append({
                                "role": "assistant", 
                                "content": str(msg.content)
                            })
            
            return {
                "index_id": agent_context.get("index_id", "unknown"),
                "document_id": agent_context.get("document_id", "unknown"),
                "segment_id": agent_context.get("segment_id", "unknown"),
                "file_uri": agent_context.get("file_uri") or agent_context.get("file_path"),
                "start_timecode_smpte": agent_context.get("start_timecode_smpte"),
                "end_timecode_smpte": agent_context.get("end_timecode_smpte"),
                "segment_type": agent_context.get("segment_type"),
                "segment_index": agent_context.get("segment_index"),
                "thread_id": agent_context.get("thread_id", "unknown"),
                "user_query": agent_context.get("user_query", ""),
                "session_id": agent_context.get("session_id", ""),
                "conversation_history": conversation_history,
                "previous_analysis_context": agent_context.get("previous_analysis_context", ""),
                "combined_analysis_context": agent_context.get("combined_analysis_context", ""),
                "analysis_history": agent_context.get("analysis_history", []),
                "skip_opensearch_query": agent_context.get("skip_opensearch_query", False)
            }
            
        except Exception as e:
            logger.warning(f"Failed to get agent context: {str(e)}")
            return {
                "index_id": "unknown",
                "document_id": "unknown",
                "segment_id": "unknown",
                "file_uri": None,
                "start_timecode_smpte": None,
                "end_timecode_smpte": None,
                "segment_type": None,
                "segment_index": None,
                "thread_id": "unknown",
                "user_query": "",
                "session_id": "",
                "conversation_history": [],
                "previous_analysis_context": "",
                "combined_analysis_context": "",
                "analysis_history": [],
                "skip_opensearch_query": False,
                "error": f"Failed to get agent context: {str(e)}"
            }

    def execute(self, query: str = None, **kwargs) -> ToolResult:
        """Execute video chapter analysis"""
        try:
            # Get information from Agent context
            agent_context = self._get_agent_context_info()
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
            
            if not query:
                query = f"동영상의 {start_timecode}부터 {end_timecode}까지의 구간을 상세히 분석해주세요."
            
            # Log query content
            logger.info(f"Video analysis query: {query}")
            
            # Get analysis context (LangGraph State based)
            combined_analysis_context = agent_context.get('combined_analysis_context', '')
            analysis_history = agent_context.get('analysis_history', [])
            
            if combined_analysis_context:
                previous_analysis_context = combined_analysis_context
                logger.info(f"🔍 Using combined analysis context: {len(previous_analysis_context)} characters (history {len(analysis_history)} items)")
            else:
                previous_analysis_context = "**Previous analysis context**: No previous analysis results"
                logger.info("🔍 No combined analysis context - using default")
            
            # Generate analysis prompt
            analysis_prompt = self._generate_analysis_prompt(
                start_timecode, end_timecode, query, previous_analysis_context
            )
            
            # Analyze video with Bedrock
            analysis_result = self._analyze_video_with_bedrock(file_uri, analysis_prompt)
            
            if not analysis_result:
                return self._create_error_result("Bedrock 동영상 분석 실패")
            
            # Return success result
            result_data = {
                "analysis_type": "video_analyzer",
                "segment_id": segment_id,
                "document_id": document_id,
                "file_uri": file_uri,
                "start_timecode_smpte": start_timecode,
                "end_timecode_smpte": end_timecode,
                "query": query,
                "analysis_query": query,  # tool_node에서 추출할 수 있도록 analysis_query로도 추가
                "ai_response": analysis_result,
                "model_version": self.model_id,
                "token_usage": getattr(self, '_last_token_usage', None)
            }
            
            message = f"동영상 챕터 분석 완료 (시간: {start_timecode} ~ {end_timecode})\n\n{analysis_result}"
            
            logger.info(f"✅ Video chapter analysis successful: {segment_id}")
            logger.info(f"Analysis result: {analysis_result}")
            
            return self._create_success_result(message, result_data)
            
        except Exception as e:
            error_msg = f"Video analysis failed: {str(e)}"
            logger.error(error_msg)
            return self._create_error_result(error_msg)

    def _generate_analysis_prompt(
        self, 
        start_timecode: str, 
        end_timecode: str,
        query: str,
        previous_analysis_context: str
    ) -> str:
        """
        시간 기반 동적 프롬프트 생성 (하드코딩된 프롬프트 사용)
        """
        # ImageAnalyzer와 유사한 구조로 프롬프트 생성
        user_prompt = f"""
        You are an AI Video Analysis Expert. Analyze the provided video segment and deliver professional insights.

        <analysis_target_segment>{start_timecode} ~ {end_timecode}</analysis_target_segment>
        <previous_analysis_context>{previous_analysis_context}</previous_analysis_context>
        <user_query>{query}</user_query>

        ## Analysis Guidelines:

        **Progressive Strategy**: Build upon previous findings, focus on NEW information not yet covered in the video analysis.

        **Key Priorities**:
        1. Identify visual content and scene composition
        2. Extract audio content (dialogue, narration, sound)
        3. Analyze temporal progression and key moments
        4. Highlight thematic elements and messages

        ## Output Structure:

        1. **Previous Findings Summary** (brief if available)
        2. **New Video Analysis Results**:
        - Visual elements and scene descriptions
        - Audio content and key dialogue
        - Temporal flow and transitions
        - Key insights and themes
        3. **Comprehensive Summary & Recommendations**

        **Focus**: Provide actionable professional insights for the video segment from {start_timecode} to {end_timecode}, avoid redundancy with previous analysis, use appropriate technical terminology for video content analysis.
        """
        
        logger.info(f"📝 Video analysis prompt generated: {start_timecode} ~ {end_timecode}")
        return user_prompt.strip()

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
    
    def _create_success_result(self, message: str, data: Dict[str, Any], execution_time: float = 0) -> ToolResult:
        """Create success result"""
        return ToolResult(
            success=True,
            message=message,
            data=data,
            execution_time=execution_time
        )
    
    def _create_error_result(self, message: str, execution_time: float = 0) -> ToolResult:
        """Create error result"""
        return ToolResult(
            success=False,
            message=message,
            data=None,
            execution_time=execution_time
        )
