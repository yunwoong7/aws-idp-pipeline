"""
AWS IDP AI Analysis - ReAct Analysis Lambda Function
"""

import json
import os
import sys
import logging
import time
import asyncio
import boto3
from datetime import datetime, timezone
from typing import Dict, Any
from agent.analysis_agent import AnalysisAgent

# Add Local Module Path for Lambda Environment
sys.path.append('/opt/python')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Common module imports
from common import (
    DynamoDBService,
    S3Service,
    AWSClientFactory,
    setup_logging,
    get_current_timestamp,
)

# Logging Setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize common services
db_service = DynamoDBService()
s3_service = S3Service()
aws_clients = AWSClientFactory()

# Environment Variables
STAGE = os.environ.get('STAGE', 'prod')
S3_BUCKET_NAME = os.environ.get('DOCUMENTS_TABLE_NAME')
SEGMENTS_TABLE_NAME = os.environ.get('SEGMENTS_TABLE_NAME')
MODEL_REGION = os.environ.get('AWS_REGION', 'us-west-2')  # Lambda에서 자동 제공
BEDROCK_AGENT_MODEL_ID = os.environ.get('BEDROCK_AGENT_MODEL_ID', 'us.anthropic.claude-3-7-sonnet-20250219-v1:0')
BEDROCK_AGENT_MAX_TOKENS = int(os.environ.get('BEDROCK_AGENT_MAX_TOKENS', 8192))
OPENSEARCH_ENDPOINT = os.environ.get('OPENSEARCH_ENDPOINT', '')
DOCUMENTS_TABLE_NAME = os.environ.get('DOCUMENTS_TABLE_NAME')

class LambdaReActAnalysisHandler:
    """Handler for LangGraph-based ReAct analysis"""
    
    def __init__(self):
        """Initialize the handler"""
        self.model_id = BEDROCK_AGENT_MODEL_ID
        self.max_tokens = BEDROCK_AGENT_MAX_TOKENS
        
        logger.info(f"✅ ReAct analysis handler initialized")
        logger.info("-" * 50)
        logger.info(f"Agent Model: {self.model_id}")
        logger.info(f"Agent Max Tokens: {self.max_tokens}")
        logger.info(f"OpenSearch: {'Enabled' if OPENSEARCH_ENDPOINT else 'Disabled'}")
        logger.info("-" * 50)
    

    async def _analyze_single_segment(self, segment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph-based single segment analysis
        """
        try:
            index_id = segment_data['index_id']
            document_id = segment_data['document_id']
            segment_index = segment_data['segment_index']
            segment_id = segment_data['segment_id']
            image_uri = segment_data['image_uri']
            file_path = segment_data['file_path']
            thread_id = segment_data.get('thread_id')  # 추가: thread_id 추출
            
            # 동영상 챕터 정보 추출
            segment_type = segment_data.get('segment_type')
            start_timecode_smpte = segment_data.get('start_timecode_smpte')
            end_timecode_smpte = segment_data.get('end_timecode_smpte')
            
            # Step Function에서 전달받은 media_type 추출
            media_type = segment_data.get('media_type', 'DOCUMENT')
            
            # Start logging
            logger.info(f"🎯 Segment analysis started:")
            logger.info("-" * 50)
            logger.info(f"Index ID: {index_id}")
            logger.info(f"Document ID: {document_id}")
            logger.info(f"Media Type: {media_type}")
            logger.info(f"Segment Index: {segment_index}")
            logger.info(f"Segment ID: {segment_id}")
            logger.info(f"Segment Type: {segment_type}")
            logger.info(f"Image URI: {image_uri}")
            logger.info(f"File Path: {file_path}")
            logger.info(f"Start Timecode: {start_timecode_smpte}")
            logger.info(f"End Timecode: {end_timecode_smpte}")
            logger.info(f"Thread ID: {thread_id}")  # 추가: thread_id 로깅
            logger.info("-" * 50)

            # Update segment analysis status
            self._update_segment_analysis_status(
                document_id=document_id, 
                segment_id=segment_id,
                segment_index=segment_index,
                steps_count=0,
                status='react_analyzing',
                analysis_summary='LangGraph analysis started'
            )
            
            # ReAct Analysis Start Logging
            start_time = time.time()
            
            # User Query
            user_query = f"'{document_id}' 세그먼트 {segment_index + 1}를 다양한 각도와 시각에서 도구를 최대한 활용하여 분석해주고, 추출한 텍스트 정보와 이미지 분석 결과를 종합하여 세그먼트에 있는 내용을 자세히 설명해주세요."
            
            logger.info("-" * 50)
            logger.info(f"💬 User Query: {user_query}")
            logger.info("-" * 50)

            agent = AnalysisAgent(
                index_id=index_id,
                document_id=document_id,
                segment_id=segment_id,
                segment_index=segment_index,
                image_uri=image_uri, 
                file_path=file_path,
                model_id=self.model_id,
                max_tokens=self.max_tokens,
                thread_id=thread_id,  # 추가: thread_id 전달
                segment_type=segment_type,  # 동영상 챕터 타입
                start_timecode_smpte=start_timecode_smpte,  # 동영상 챕터 시작 시간
                end_timecode_smpte=end_timecode_smpte,  # 동영상 챕터 종료 시간
                media_type=media_type  # Documents 테이블의 media_type
            )

            logger.info("⚡ ReAct Analysis Running...")
            analysis_result = agent.analyze_document(
                user_query=user_query,
                analysis_type="comprehensive"
            )
            
            analysis_time = time.time() - start_time
            logger.info("-" * 50)
            logger.info(f"⏱️ Total Analysis Time: {analysis_time:.2f} seconds")
            logger.info("-" * 50)

            print(f"analysis_result: {analysis_result}")
            
            # Analysis Result Processing
            if analysis_result.get('success'):
                logger.info("🎉" + "=" * 100)
                logger.info("🎉 ReAct Analysis Success!")
                logger.info("🎉" + "=" * 100)
                logger.info(f"🔢 Steps Executed: {analysis_result.get('steps_count', 0)}")
                logger.info(f"🛠️ Tools Used: {analysis_result.get('tools_used', [])}")
                logger.info(f"⏱️ Total Analysis Time: {analysis_time:.2f} seconds")
                
                # Analysis Summary
                analysis_content = analysis_result.get('analysis_content', '')
                analysis_summary = analysis_result.get('analysis_summary', '')
                
                logger.info(f"📝 Analysis Summary Character Count: {len(analysis_summary):,}")
                logger.info(f"📄 Total Analysis Content Character Count: {len(analysis_content):,}")
                
                # Tool Result Details
                tool_results = analysis_result.get('tool_results', [])
                if tool_results:
                    logger.info(f"🔧 Tool Result Details:")
                    for i, tool_result in enumerate(tool_results[:3]):
                        tool_name = tool_result.get('tool_name', 'Unknown')
                        success = tool_result.get('success', False)
                        message = tool_result.get('message', '')
                        status = "✅" if success else "❌"
                        logger.info(f"  {i+1}. {status} {tool_name}: {message[:100]}...")
                
                if not analysis_summary and analysis_content:
                    # Only use content if summary is not available for error handling
                    analysis_summary = analysis_content[:1000] + "..." if len(analysis_content) > 1000 else analysis_content
                
                # Update DynamoDB segment ReAct analysis status
                try:
                    self._update_segment_analysis_status(
                        document_id=document_id,
                        segment_id=segment_id,
                        segment_index=segment_index,
                        steps_count=analysis_result.get('steps_count', 0),
                        status='completed',
                        analysis_summary=analysis_summary
                    )
                except Exception as e:
                    logger.error(f"❌ DynamoDB ReAct analysis status update failed: {str(e)}")

                # Note: The new LangGraph-based agent automatically saves tool results and final responses to OpenSearch
                
                # OpenSearch 저장 상태 확인 및 로깅
                opensearch_saved = analysis_result.get('opensearch_saved', False)
                logger.info(f"💾 OpenSearch 최종 응답 저장 상태: {opensearch_saved}")
                
                if not opensearch_saved:
                    logger.warning("⚠️ 최종 AI 응답이 OpenSearch에 저장되지 않았습니다!")
                    logger.warning("⚠️ 로그를 확인하여 저장 실패 원인을 파악하세요.")
                else:
                    logger.info("✅ 최종 AI 응답이 OpenSearch에 성공적으로 저장되었습니다.")
                
                logger.info("🎉" + "=" * 80)
                logger.info(f"🎉 Segment {segment_index} ReAct analysis completed!")
                logger.info("🎉" + "=" * 80)
                
                # References 정보 추출 및 스트리밍 준비
                references = analysis_result.get('references', [])
                logger.info(f"📋 추출된 참조 개수: {len(references)}")
                
                # References가 있는 경우 로깅
                if references:
                    for i, ref in enumerate(references, 1):
                        title = ref.get('title', f'참조 {i}')
                        logger.info(f"📋 참조 {i}: {title}")
                
                return {
                    'success': True,
                    'document_id': document_id,
                    'segment_id': segment_id,
                    'segment_index': segment_index,
                    'analysis_summary': analysis_summary,
                    'analysis_content': analysis_content,
                    'analysis_time': analysis_time,
                    'steps_count': analysis_result.get('steps_count', 0),
                    'tools_used': analysis_result.get('tools_used', []),
                    'tool_results': analysis_result.get('tool_results', []),
                    'analysis_history': analysis_result.get('analysis_history', []),
                    'references': references,  # 참조 정보 추가
                    'opensearch_saved': opensearch_saved,  # 실제 저장 상태 포함
                    'timestamp': get_current_timestamp()
                }
            else:
                error_msg = analysis_result.get('error', 'Unknown analysis error')
                logger.error(f"❌ ReAct analysis failed: {error_msg}")
                raise Exception(f"Analysis failed: {error_msg}")
                
        except Exception as e:
            error_msg = f"Segment analysis processing failed: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Exception details: {str(e)}")
            
            # Stack trace logging
            import traceback
            logger.error("💥 Stack trace:")
            logger.error(traceback.format_exc())
            
            # Update segment ReAct analysis status to 'react_failed' when an error occurs
            try:
                self._update_segment_analysis_status(
                    document_id=segment_data['document_id'],
                    segment_id=segment_data['segment_id'],
                    segment_index=segment_data['segment_index'],
                    steps_count=0,
                    status='react_failed',
                    analysis_summary=f'ReAct analysis failed: {str(e)[:200]}'
                )
            except Exception as update_error:
                logger.error(f"[DynamoDB] ReAct analysis status update failed: {str(update_error)}")
            
            raise Exception(error_msg)
    
    def _update_segment_analysis_status(self, document_id: str, segment_id: str, segment_index: int, 
                                   steps_count: int, status: str, analysis_summary: str):
        """Update DynamoDB Segments table status"""
        try:
            if not (SEGMENTS_TABLE_NAME):
                logger.warning("SEGMENTS_TABLE_NAME environment variable is not set")
                return
            
            # Construct update expression based on status
            if status == 'react_analyzing':
                # ReAct analysis started
                update_expr = """
                    SET #status = :status,
                        updated_at = :updated_at
                """
                attr_values = {
                    ':status': status,
                    ':updated_at': get_current_timestamp()
                }
                attr_names = { '#status': 'status' }
            elif status == 'react_completed':
                # ReAct analysis completed
                update_expr = """
                    SET #status = :status,
                        analysis_completed_at = :analysis_completed_at,
                        analysis_error = :analysis_error,
                        analysis_failed_at = :analysis_failed_at,
                        steps_count = :steps_count,
                        updated_at = :updated_at
                """
                attr_values = {
                    ':status': status,
                    ':analysis_completed_at': get_current_timestamp(),
                    ':analysis_error': '', 
                    ':analysis_failed_at': '',
                    ':steps_count': steps_count,
                    ':updated_at': get_current_timestamp()
                }
                attr_names = { '#status': 'status' }
            elif status == 'react_failed':
                # ReAct analysis failed
                update_expr = """
                    SET #status = :status,
                        analysis_completed_at = :analysis_completed_at,
                        analysis_error = :analysis_error,
                        analysis_failed_at = :analysis_failed_at,
                        updated_at = :updated_at
                """
                attr_values = {
                    ':status': status,
                    ':analysis_completed_at': '',
                    ':analysis_error': analysis_summary[:500] if analysis_summary else '',  # 오류 메시지
                    ':analysis_failed_at': get_current_timestamp(),
                    ':updated_at': get_current_timestamp()
                }
                attr_names = { '#status': 'status' }
            else:
                # Default update
                update_expr = """
                    SET #status = :status,
                        updated_at = :updated_at
                """
                attr_values = {
                    ':status': status,
                    ':updated_at': get_current_timestamp()
                }
                attr_names = { '#status': 'status' }
            
            # DynamoDB update using common service
            db_service.update_item(
                'segments',
                {'segment_id': segment_id},
                update_expression=update_expr,
                expression_attribute_values=attr_values,
                expression_attribute_names=attr_names
            )
            
            logger.info(f"[DynamoDB] Segment ReAct analysis status updated - segment_id: {segment_id}, status: {status}")
            
        except Exception as e:
            logger.error(f"[DynamoDB] Segment ReAct analysis status update failed - segment_id: {segment_id}, error: {str(e)}")
            raise

# Global handler instance
handler_instance = None

def lambda_handler(event, context):
    """
    Lambda handler (AWS Lambda entry point)
    
    Args:
        event: Step Function event
        context: Lambda context
        
    Returns:
        Analysis result
    """
    global handler_instance
    handler_start_time = datetime.now(timezone.utc)
    
    try:
        # 🔍 Lambda handler start logging
        logger.info("🚀" + "=" * 100)
        logger.info("🚀 Start ReAct Analysis Handler")
        logger.info("🚀" + "=" * 100)

        # 🔍 Environment variables logging
        logger.info("🌍 Environment variables:")
        logger.info("-" * 50)
        important_env_vars = [
            'STAGE', 'BEDROCK_AGENT_MODEL_ID', 'BEDROCK_AGENT_MAX_TOKENS', 
            'BEDROCK_IMAGE_MODEL_ID', 'BEDROCK_IMAGE_MAX_TOKENS',
            'AWS_REGION', 
            'OPENSEARCH_ENDPOINT'
        ]
        for var in important_env_vars:
            value = os.environ.get(var, 'NOT_SET')
            if len(str(value)) > 50:
                value = str(value)[:50] + "..."
            logger.info(f"   {var}: {value}")
        logger.info("-" * 50)
        
        # 🔍 Input event logging
        logger.info("📋 Input event:")
        logger.info("-" * 50)
        logger.info(json.dumps(event, ensure_ascii=False, indent=2, default=str))
        logger.info("-" * 50)
        
        # Initialize handler instance
        if handler_instance is None:
            handler_instance = LambdaReActAnalysisHandler()
        
        # Run asynchronous analysis
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Convert event from Step Function Map to _analyze_single_segment format
            segment_data = {
                'index_id': event['index_id'],
                'document_id': event['document_id'],
                'segment_index': event['segment_index'],
                'segment_id': event['segment_id'],
                'image_uri': event['image_uri'],
                'file_path': event.get('file_uri', ''),
                'thread_id': event.get('thread_id'),  # 추가: thread_id 전달
                # 동영상 챕터 정보 추가
                'segment_type': event.get('segment_type'),
                'start_timecode_smpte': event.get('start_timecode_smpte'),
                'end_timecode_smpte': event.get('end_timecode_smpte'),
            }
            
            logger.info(f"🔄 Extracted thread_id from event: {segment_data.get('thread_id')}")
            
            result = loop.run_until_complete(handler_instance._analyze_single_segment(segment_data))
        finally:
            loop.close()
        
        # 🔍 Lambda handler completion logging
        handler_end_time = datetime.now(timezone.utc)
        handler_duration = (handler_end_time - handler_start_time).total_seconds()
        
        logger.info("🚀" + "=" * 100)
        logger.info(f"🎯 ReAct Lambda handler completed - Segment {result.get('segment_index', 'unknown')}")
        logger.info("🚀" + "=" * 100)
        logger.info(f"⏰ Lambda end time: {handler_end_time.isoformat()}")
        logger.info(f"⌛ Total processing time: {handler_duration:.2f} seconds")
        logger.info(f"✅ Segment processing success: {result.get('success', False)}")
        logger.info(f"📃 Processed segment: {result.get('segment_index', 'unknown')}")
        logger.info(f"📁 Index ID: {result.get('index_id', 'unknown')}")
        logger.info(f"📄 Document ID: {result.get('document_id', 'unknown')}")
        logger.info(f"🔢 ReAct steps: {result.get('steps_count', 0)}")
        logger.info(f"🛠️ Used tools: {result.get('tools_used', [])}")
        logger.info(f"📄 Analysis time: {result.get('analysis_time', 0):.2f} seconds")
        logger.info(f"🔍 OpenSearch saved: {result.get('opensearch_saved', False)}")
        
        if result.get('success'):
            summary_length = len(result.get('analysis_summary', ''))
            logger.info(f"📝 Analysis summary character count: {summary_length}")
            logger.info("🎉 ReAct analysis completed successfully!")
        else:
            logger.error(f"❌ Segment {result.get('segment_index', 'unknown')} analysis failed")
        
        logger.info("🚀" + "=" * 100)
        return result
        
    except Exception as e:
        # 🔍 Overall error handling logging
        handler_end_time = datetime.now(timezone.utc)
        handler_duration = (handler_end_time - handler_start_time).total_seconds()
        
        logger.error("🚀" + "=" * 100)
        logger.error("💥 ReAct analysis Lambda handler error")
        logger.error("🚀" + "=" * 100)
        logger.error(f"⏰ Error occurred time: {handler_end_time.isoformat()}")
        logger.error(f"⌛ Processing time before error: {handler_duration:.2f} seconds")
        logger.error(f"💥 Error message: {str(e)}")
        logger.error(f"💥 Error type: {type(e).__name__}")
        logger.error(f"📨 Request ID: {context.aws_request_id}")
        
        # Stack trace logging
        import traceback
        logger.error("💥 Stack trace:")
        logger.error(traceback.format_exc())
        
        # Create failure response
        error_response = {
            'success': False,
            'error': str(e),
            'error_details': {
                'error_type': type(e).__name__,
                'processing_time': handler_duration,
                'timestamp': get_current_timestamp(),
                'function_name': context.function_name,
                'request_id': context.aws_request_id
            },
            'index_id': event.get('index_id', 'unknown'),
            'document_id': event.get('document_id', 'unknown'),
            'segment_id': event.get('segment_id', 'unknown'),
            'segment_index': event.get('segment_index', 0),
            'timestamp': get_current_timestamp()
        }
        
        logger.error(f"💥 Error response: {json.dumps(error_response, indent=2, ensure_ascii=False, default=str)}")
        logger.error("🚀" + "=" * 100)
        
        # Raise exception to handle failure in Step Function
        raise Exception(f"Lambda execution failed: {str(e)}")