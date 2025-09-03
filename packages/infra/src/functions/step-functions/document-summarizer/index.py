"""
Document Summarizer Lambda
Combines all segment content_combined to generate document-level summary using LLM
"""

import json
import logging
import os
from typing import Dict, Any, List
from datetime import datetime, timezone
from botocore.exceptions import ClientError

# Common module imports
from common import (
    DynamoDBService,
    handle_lambda_error,
    get_current_timestamp
)

# Logging setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize common services
db_service = DynamoDBService()


class SkipSummaryError(Exception):
    """Raised when summary generation should be skipped (e.g., context limit)."""
    pass

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Document Summarizer Lambda handler
    Generate document-level summary from all segment content_combined using LLM
    
    Args:
        event: Event received from Step Function (includes document_id and index_id)
        context: Lambda context
        
    Returns:
        Processing result
    """
    try:
        logger.info(f"Document Summarizer started - Event: {json.dumps(event, ensure_ascii=False, indent=2)}")
        
        # Extract input data
        index_id = event.get('index_id')
        document_id = event.get('document_id')
        
        if not document_id or not index_id:
            raise ValueError("Both document_id and index_id are required.")
        
        logger.info(f"📋 Target: index_id={index_id}, document_id={document_id}")
        
        # Mark document as summarizing in-progress (status only)
        try:
            current_time = get_current_timestamp()
            db_service.update_item(
                table_name='documents',
                key={'document_id': document_id},
                update_expression='SET #status = :status, updated_at = :updated_at',
                expression_attribute_names={'#status': 'status'},
                expression_attribute_values={
                    ':status': 'summarizing',
                    ':updated_at': current_time
                }
            )
            logger.info(f"📌 Document status set to summarizing: {document_id}")
        except Exception as se:
            logger.warning(f"⚠️ Failed to set summarizing status: {str(se)}")

        # Generate document summary
        summary_result = generate_document_summary(document_id, index_id)
        
        if summary_result:
            if summary_result.get('skipped'):
                logger.warning(f"⚠️ Document summary skipped due to context limit: {document_id}")
            else:
                logger.info(f"✅ Document summary generation complete: {document_id}")
            
            # Update document status to final completion
            update_document_final_status(document_id, True)
            
            return {
                'success': True,
                'message': 'Document summary skipped due to context limit' if summary_result.get('skipped') else 'Document summary generation complete',
                'document_id': document_id,
                'index_id': index_id,
                'summary_length': len(summary_result.get('summary', '')),
                'skipped': summary_result.get('skipped', False)
            }
        else:
            logger.error(f"❌ Document summary generation failed: {document_id}")
            
            # Update document status to indicate failure
            update_document_final_status(document_id, False)
            
            return {
                'success': False,
                'message': 'Document summary generation failed',
                'document_id': document_id,
                'index_id': index_id
            }
        
    except Exception as e:
        logger.error(f"Document Summarizer error: {str(e)}", exc_info=True)
        return handle_lambda_error(e)

def generate_document_summary(document_id: str, index_id: str) -> Dict[str, Any]:
    """Generate document-level summary from all segments"""
    try:
        logger.info(f"📄 Document summary generation started: {document_id}")
        
        # Get document information
        document = db_service.get_item('documents', {'document_id': document_id})
        if not document:
            logger.error(f"❌ Document not found: {document_id}")
            return None
        
        media_type = document.get('media_type', 'DOCUMENT')
        file_name = document.get('file_name', 'Unknown')
        
        logger.info(f"📄 Document info: {file_name} ({media_type})")
        
        # Retrieve all segments for the document
        from boto3.dynamodb.conditions import Key
        segments_response = db_service.query_items(
            table_name='segments',
            key_condition_expression=Key('document_id').eq(document_id),
            index_name='DocumentIdIndex'
        )
        
        segments = segments_response.get('Items', [])
        logger.info(f"📋 Total segments found: {len(segments)}")
        
        if not segments:
            logger.warning(f"⚠️ No segments found for document: {document_id}")
            return None
        
        # Collect per-segment short summaries (3~4 lines) using Haiku, then combine
        segment_contents = []
        
        for segment in segments:
            segment_id = segment.get('segment_id')
            segment_index = segment.get('segment_index', 0)
            segment_type = segment.get('segment_type', 'PAGE')
            
            if not segment_id:
                continue

            # Prefer existing content fields as source; we'll re-summarize to 3~4 lines using Haiku
            source_text = (
                segment.get('content_combined')
                or segment.get('summary')
                or segment.get('content')
                or ''
            )

            short_summary = ''
            if isinstance(source_text, str) and source_text.strip():
                try:
                    short_summary = generate_page_summary_with_llm(
                        source_text.strip(),
                        media_type,
                        file_name,
                        segment_index,
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Haiku page summary failed for segment {segment_index}: {str(e)}")

            # Fallback if summarization failed
            if not short_summary:
                fallback_text = (segment.get('summary') or segment.get('content_combined') or '')
                short_summary = (fallback_text[:800] + '...') if isinstance(fallback_text, str) else ''

            if short_summary:
                segment_contents.append({
                    'segment_index': segment_index,
                    'segment_type': segment_type,
                    'content': short_summary.strip()
                })
                logger.debug(f"📄 Segment {segment_index} short summary collected: {len(short_summary)} chars")
        
        if not segment_contents:
            logger.warning(f"⚠️ No segment summaries found for document: {document_id}")
            return None
        
        # Sort by segment_index
        segment_contents.sort(key=lambda x: x['segment_index'])
        
        logger.info(f"📊 Total segments with summaries: {len(segment_contents)}")
        
        # Generate combined content from short summaries
        combined_content = create_combined_content_for_llm(segment_contents, media_type, file_name)
        
        # Generate summary using LLM
        summary_skipped = False
        try:
            summary = generate_summary_with_llm(combined_content, media_type, file_name)
        except SkipSummaryError as se:
            # Context limit exceeded (input length + max_tokens)
            logger.warning(f"⚠️ Skipping summary generation due to context limit: {str(se)}")
            summary = ""
            summary_skipped = True
        
        if summary_skipped:
            # Treat as success without updating summary
            return {
                'summary': summary,
                'segment_count': len(segment_contents),
                'total_content_length': sum(len(s['content']) for s in segment_contents),
                'skipped': True
            }

        if summary:
            # Update Documents table with summary
            success = update_document_summary(document_id, summary)
            
            if success:
                return {
                    'summary': summary,
                    'segment_count': len(segment_contents),
                    'total_content_length': sum(len(s['content']) for s in segment_contents),
                    'skipped': False
                }
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Document summary generation error: {str(e)}")
        raise

def create_combined_content_for_llm(segment_contents: List[Dict[str, Any]], media_type: str, file_name: str) -> str:
    """Create combined content for LLM input"""
    try:
        content_parts = []
        
        # Add header based on media type
        if media_type == 'VIDEO':
            content_parts.append(f"# 동영상 '{file_name}' 전체 분석 내용\n")
            content_parts.append(f"다음은 {len(segment_contents)}개 챕터별 분석 결과입니다:\n\n")
        else:
            content_parts.append(f"# 문서 '{file_name}' 전체 분석 내용\n")
            content_parts.append(f"다음은 {len(segment_contents)}개 페이지별 분석 결과입니다:\n\n")
        
        # Add each segment's content (prefer summary-based 'content')
        for segment in segment_contents:
            segment_index = segment['segment_index']
            segment_type = segment['segment_type']
            # Prefer 'content' (segment summary). Fallback to 'content_combined' for backward compatibility.
            content_text = segment.get('content') or segment.get('content_combined') or ""
            
            if media_type == 'VIDEO':
                content_parts.append(f"## 챕터 {segment_index + 1}\n")
            else:
                content_parts.append(f"## 페이지 {segment_index + 1}\n")
            
            content_parts.append(f"{content_text}\n\n")
        
        combined_content = "\n".join(content_parts)
        
        logger.info(f"📝 Combined content for LLM: {len(combined_content)} chars")
        return combined_content
        
    except Exception as e:
        logger.error(f"❌ Error creating combined content: {str(e)}")
        return ""

def generate_summary_with_llm(content: str, media_type: str, file_name: str) -> str:
    """Generate summary using LLM (Bedrock)"""
    try:
        import boto3
        
        # Get Bedrock configuration
        model_id = os.environ.get('BEDROCK_SUMMARY_MODEL_ID', 'us.anthropic.claude-3-7-sonnet-20250219-v1:0')
        max_tokens = int(os.environ.get('BEDROCK_SUMMARY_MAX_TOKENS', '64000'))
        
        bedrock_runtime = boto3.client('bedrock-runtime')
        
        # Create prompt based on media type
        if media_type == 'VIDEO':
            system_prompt = f"""당신은 동영상 분석 전문가입니다. 제공된 동영상 '{file_name}'의 챕터별 분석 결과를 바탕으로 전체 동영상의 종합적인 요약을 생성해주세요.

요약은 다음과 같은 구조로 작성해주세요:
1. 동영상 전체 개요 (주제, 목적, 대상 등)
2. 주요 내용 및 핵심 메시지
3. 챕터별 요점 정리
4. 결론 및 시청자에게 전달하고자 하는 메시지

전문적이고 체계적으로 작성하되, 이해하기 쉽게 작성해주세요."""

            user_prompt = f"다음은 동영상 '{file_name}'의 챕터별 분석 결과입니다. 이를 바탕으로 전체 동영상의 종합 요약을 생성해주세요:\n\n{content}"
        else:
            system_prompt = f"""당신은 문서 분석 전문가입니다. 제공된 문서 '{file_name}'의 페이지별 분석 결과를 바탕으로 전체 문서의 종합적인 요약을 생성해주세요.

요약은 다음과 같은 구조로 작성해주세요:
1. 문서 전체 개요 (주제, 목적, 대상 등)
2. 주요 내용 및 핵심 포인트
3. 페이지별 중요 사항 정리
4. 결론 및 문서의 핵심 메시지

전문적이고 체계적으로 작성하되, 이해하기 쉽게 작성해주세요."""

            user_prompt = f"다음은 문서 '{file_name}'의 페이지별 분석 결과입니다. 이를 바탕으로 전체 문서의 종합 요약을 생성해주세요:\n\n{content}"
        
        # Prepare request body
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
        }
        
        # Call Bedrock
        logger.info(f"🤖 Calling Bedrock model: {model_id}")
        try:
            response = bedrock_runtime.invoke_model(
                modelId=model_id,
                body=json.dumps(request_body)
            )
        except ClientError as ce:
            code = (ce.response.get('Error') or {}).get('Code')
            message = (ce.response.get('Error') or {}).get('Message', '')
            # Detect context limit overflow and signal skip
            if code == 'ValidationException' and 'context limit' in message:
                raise SkipSummaryError(message)
            raise

        # Parse response
        response_body = json.loads(response['body'].read())
        summary = response_body['content'][0]['text']
        
        logger.info(f"✅ LLM summary generated: {len(summary)} chars")
        return summary
        
    except SkipSummaryError:
        # Bubble up to caller to handle as "skipped"
        raise
    except Exception as e:
        logger.error(f"❌ LLM summary generation error: {str(e)}")
        return ""

def generate_page_summary_with_llm(content: str, media_type: str, file_name: str, segment_index: int) -> str:
    """Generate 3~4 line page/chapter summary using Haiku"""
    try:
        import boto3

        model_id = os.environ.get('BEDROCK_PAGE_SUMMARY_MODEL_ID', 'us.anthropic.claude-3-5-haiku-20241022-v1:0')
        max_tokens_env = int(os.environ.get('BEDROCK_PAGE_SUMMARY_MAX_TOKENS', '8192'))
        # Cap to a reasonable output length for 3~4 lines
        max_tokens = min(max_tokens_env, 512)

        bedrock_runtime = boto3.client('bedrock-runtime')

        if media_type == 'VIDEO':
            system_prompt = (
                "당신은 동영상 챕터 요약 전문가입니다. 입력된 챕터 내용을 3~4줄의 한국어 요약으로 간결하게 정리하세요. "
                "불필요한 서론/결론 없이 핵심만 담고, 문장은 짧고 명확하게 작성하세요."
            )
            user_prompt = f"동영상 '{file_name}'의 챕터 {segment_index + 1} 내용입니다. 3~4줄 요약:\n\n{content}"
        else:
            system_prompt = (
                "당신은 문서 페이지 요약 전문가입니다. 입력된 페이지 내용을 3~4줄의 한국어 요약으로 간결하게 정리하세요. "
                "불필요한 서론/결론 없이 핵심만 담고, 문장은 짧고 명확하게 작성하세요."
            )
            user_prompt = f"문서 '{file_name}'의 페이지 {segment_index + 1} 내용입니다. 3~4줄 요약:\n\n{content}"

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": user_prompt,
                }
            ]
        }

        logger.debug(f"🤖 Calling Haiku for page {segment_index + 1}: {model_id}")
        response = bedrock_runtime.invoke_model(
            modelId=model_id,
            body=json.dumps(request_body)
        )

        response_body = json.loads(response['body'].read())
        page_summary = response_body['content'][0]['text']
        return page_summary

    except Exception as e:
        logger.error(f"❌ Page-level LLM summary error: {str(e)}")
        return ""

def update_document_summary(document_id: str, summary: str) -> bool:
    """Update Documents table with generated summary"""
    try:
        current_time = get_current_timestamp()
        
        update_response = db_service.update_item(
            table_name='documents',
            key={'document_id': document_id},
            update_expression='SET summary = :summary, updated_at = :updated_at',
            expression_attribute_values={
                ':summary': summary,
                ':updated_at': current_time
            }
        )
        
        logger.info(f"📄 Document summary updated: {document_id} ({len(summary)} chars)")
        return True
        
    except Exception as e:
        logger.error(f"❌ Document summary update failed: {str(e)}")
        return False

def update_document_final_status(document_id: str, success: bool) -> None:
    """Update document status to final completion"""
    try:
        current_time = get_current_timestamp()
        final_status = 'completed' if success else 'summary_failed'
        
        update_response = db_service.update_item(
            table_name='documents',
            key={'document_id': document_id},
            update_expression='SET #status = :status, updated_at = :updated_at',
            expression_attribute_names={'#status': 'status'},
            expression_attribute_values={
                ':status': final_status,
                ':updated_at': current_time
            }
        )
        
        logger.info(f"📄 Document final status update: {document_id} -> {final_status}")
        
    except Exception as e:
        logger.error(f"❌ Document status update failed: {str(e)}")

# 테스트용 메인 함수
if __name__ == "__main__":
    # 로컬 테스트용
    test_event = {
        "index_id": "test_index_123",
        "document_id": "test_document_456"
    }
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, ensure_ascii=False, indent=2))