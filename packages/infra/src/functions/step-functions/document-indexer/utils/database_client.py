"""
DynamoDB 클라이언트 유틸리티
Documents 및 Pages 테이블과 상호작용하는 기능 제공
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class DatabaseClient:
    """DynamoDB 클라이언트 클래스"""
    
    def __init__(self, documents_table_name: str, pages_table_name: str, elements_table_name: str = None):
        """
        데이터베이스 클라이언트 초기화
        
        Args:
            documents_table_name: Documents 테이블 이름
            pages_table_name: Pages 테이블 이름
            elements_table_name: Elements 테이블 이름 (선택적)
        """
        self.documents_table_name = documents_table_name
        self.pages_table_name = pages_table_name
        self.elements_table_name = elements_table_name
        
        # DynamoDB 클라이언트 초기화
        self.dynamodb = boto3.resource('dynamodb')
        self.documents_table = self.dynamodb.Table(documents_table_name)
        self.pages_table = self.dynamodb.Table(pages_table_name)
        
        if elements_table_name:
            self.elements_table = self.dynamodb.Table(elements_table_name)
    
    def get_current_timestamp(self) -> str:
        """현재 UTC 타임스탬프 반환"""
        return datetime.now(timezone.utc).isoformat()
    
    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        문서 정보 조회
        
        Args:
            document_id: 문서 ID
            
        Returns:
            문서 정보 또는 None
        """
        try:
            response = self.documents_table.get_item(
                Key={'document_id': document_id}
            )
            
            if 'Item' in response:
                logger.info(f"문서 조회 성공: {document_id}")
                return response['Item']
            else:
                logger.warning(f"문서를 찾을 수 없음: {document_id}")
                return None
                
        except ClientError as e:
            logger.error(f"문서 조회 실패: {document_id}, 오류: {str(e)}")
            return None
    
    def get_pages_by_document(self, document_id: str) -> List[Dict[str, Any]]:
        """
        문서의 모든 페이지 조회
        
        Args:
            document_id: 문서 ID
            
        Returns:
            페이지 리스트
        """
        try:
            response = self.pages_table.query(
                IndexName='DocumentIdIndex',
                KeyConditionExpression=boto3.dynamodb.conditions.Key('document_id').eq(document_id)
            )
            
            pages = response.get('Items', [])
            logger.info(f"문서 페이지 조회 완료: {document_id}, 페이지 수: {len(pages)}")
            
            return pages
            
        except ClientError as e:
            logger.error(f"문서 페이지 조회 실패: {document_id}, 오류: {str(e)}")
            return []
    
    def update_page_text(self, page_id: str, extracted_text: str) -> bool:
        """
        페이지 텍스트 정보 업데이트
        
        Args:
            page_id: 페이지 ID
            extracted_text: 추출된 텍스트
            
        Returns:
            업데이트 성공 여부
        """
        try:
            current_time = self.get_current_timestamp()
            
            # 업데이트 표현식 구성
            update_expression = "SET extracted_text = :text, text_extraction_completed_at = :completed_at"
            expression_values = {
                ':text': extracted_text,
                ':completed_at': current_time
            }
            
            # 텍스트 길이 추가
            if extracted_text:
                update_expression += ", text_length = :length"
                expression_values[':length'] = len(extracted_text)
            
            # 페이지 업데이트
            response = self.pages_table.update_item(
                Key={'page_id': page_id},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values,
                ReturnValues='UPDATED_NEW'
            )
            
            logger.info(f"페이지 텍스트 업데이트 성공: {page_id}")
            return True
            
        except ClientError as e:
            logger.error(f"페이지 텍스트 업데이트 실패: {page_id}, 오류: {str(e)}")
            return False
    
    def update_document_processing_status(
        self,
        document_id: str,
        status: str,
        processing_metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        문서 처리 상태 업데이트
        
        Args:
            document_id: 문서 ID
            status: 처리 상태
            processing_metadata: 처리 메타데이터
            
        Returns:
            업데이트 성공 여부
        """
        try:
            current_time = self.get_current_timestamp()
            
            # 기본 업데이트 표현식
            update_expression = "SET processing_status = :status, updated_at = :updated_at"
            expression_values = {
                ':status': status,
                ':updated_at': current_time
            }
            
            # 처리 메타데이터 추가
            if processing_metadata:
                for key, value in processing_metadata.items():
                    attr_name = f"#{key}"
                    attr_value = f":{key}"
                    
                    update_expression += f", {attr_name} = {attr_value}"
                    expression_values[attr_value] = value
                    
                    # ExpressionAttributeNames 설정 (예약어 처리)
                    if 'ExpressionAttributeNames' not in locals():
                        expression_attribute_names = {}
                    expression_attribute_names[attr_name] = key
            
            # 문서 업데이트
            update_params = {
                'Key': {'document_id': document_id},
                'UpdateExpression': update_expression,
                'ExpressionAttributeValues': expression_values,
                'ReturnValues': 'UPDATED_NEW'
            }
            
            if 'expression_attribute_names' in locals():
                update_params['ExpressionAttributeNames'] = expression_attribute_names
            
            response = self.documents_table.update_item(**update_params)
            
            logger.info(f"문서 처리 상태 업데이트 성공: {document_id}, 상태: {status}")
            return True
            
        except ClientError as e:
            logger.error(f"문서 처리 상태 업데이트 실패: {document_id}, 오류: {str(e)}")
            return False
    
    def get_page(self, page_id: str) -> Optional[Dict[str, Any]]:
        """
        페이지 정보 조회
        
        Args:
            page_id: 페이지 ID
            
        Returns:
            페이지 정보 또는 None
        """
        try:
            response = self.pages_table.get_item(
                Key={'page_id': page_id}
            )
            
            if 'Item' in response:
                logger.info(f"페이지 조회 성공: {page_id}")
                return response['Item']
            else:
                logger.warning(f"페이지를 찾을 수 없음: {page_id}")
                return None
                
        except ClientError as e:
            logger.error(f"페이지 조회 실패: {page_id}, 오류: {str(e)}")
            return None
    
    def batch_update_pages(self, page_updates: List[Dict[str, Any]]) -> int:
        """
        여러 페이지 일괄 업데이트
        
        Args:
            page_updates: 페이지 업데이트 정보 리스트
                         [{'page_id': str, 'extracted_text': str}, ...]
            
        Returns:
            성공적으로 업데이트된 페이지 수
        """
        success_count = 0
        
        for update_info in page_updates:
            page_id = update_info.get('page_id')
            extracted_text = update_info.get('extracted_text', '')
            
            if page_id and self.update_page_text(page_id, extracted_text):
                success_count += 1
        
        logger.info(f"일괄 페이지 업데이트 완료: {success_count}/{len(page_updates)}")
        return success_count
    
    def get_documents_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        특정 상태의 문서들 조회
        
        Args:
            status: 처리 상태
            
        Returns:
            문서 리스트
        """
        try:
            response = self.documents_table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr('processing_status').eq(status)
            )
            
            documents = response.get('Items', [])
            logger.info(f"상태별 문서 조회 완료: {status}, 문서 수: {len(documents)}")
            
            return documents
            
        except ClientError as e:
            logger.error(f"상태별 문서 조회 실패: {status}, 오류: {str(e)}")
            return []
    
    def check_table_health(self) -> Dict[str, bool]:
        """
        테이블 상태 확인
        
        Returns:
            테이블 상태 정보
        """
        health_status = {
            'documents_table': False,
            'pages_table': False
        }
        
        try:
            # Documents 테이블 상태 확인
            response = self.documents_table.describe_table()
            if response['Table']['TableStatus'] == 'ACTIVE':
                health_status['documents_table'] = True
                
        except Exception as e:
            logger.error(f"Documents 테이블 상태 확인 실패: {str(e)}")
        
        try:
            # Pages 테이블 상태 확인
            response = self.pages_table.describe_table()
            if response['Table']['TableStatus'] == 'ACTIVE':
                health_status['pages_table'] = True
                
        except Exception as e:
            logger.error(f"Pages 테이블 상태 확인 실패: {str(e)}")
        
        logger.info(f"테이블 상태 확인 완료: {health_status}")
        return health_status
    
    def get_elements_by_document(self, document_id: str) -> List[Dict[str, Any]]:
        """
        문서의 모든 Elements 조회
        
        Args:
            document_id: 문서 ID
            
        Returns:
            Elements 리스트
        """
        if not hasattr(self, 'elements_table'):
            logger.warning("Elements 테이블이 설정되지 않았습니다.")
            return []
        
        try:
            response = self.elements_table.query(
                IndexName='ProjectIndex',
                KeyConditionExpression=boto3.dynamodb.conditions.Key('document_id').eq(document_id)
            )
            
            elements = response.get('Items', [])
            logger.info(f"문서 Elements 조회 완료: {document_id}, Elements 수: {len(elements)}")
            
            return elements
            
        except ClientError as e:
            logger.error(f"문서 Elements 조회 실패: {document_id}, 오류: {str(e)}")
            return []
    
    def update_document(self, document_id: str, update_data: Dict[str, Any]) -> bool:
        """
        Documents 테이블 업데이트
        
        Args:
            document_id: 문서 ID
            update_data: 업데이트할 데이터
            
        Returns:
            성공 여부
        """
        try:
            # UpdateExpression과 ExpressionAttributeValues 구성
            update_expression_parts = []
            expression_attribute_values = {}
            
            for key, value in update_data.items():
                update_expression_parts.append(f"{key} = :{key}")
                expression_attribute_values[f":{key}"] = value
            
            update_expression = "SET " + ", ".join(update_expression_parts)
            
            response = self.documents_table.update_item(
                Key={'document_id': document_id},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_attribute_values,
                ReturnValues='UPDATED_NEW'
            )
            
            logger.info(f"Documents 테이블 업데이트 성공: {document_id}")
            return True
            
        except ClientError as e:
            logger.error(f"Documents 테이블 업데이트 실패: {document_id} - {str(e)}")
            return False
    
    def update_page(self, page_id: str, update_data: Dict[str, Any]) -> bool:
        """
        Pages 테이블 업데이트
        
        Args:
            page_id: 페이지 ID
            update_data: 업데이트할 데이터
            
        Returns:
            성공 여부
        """
        try:
            # UpdateExpression과 ExpressionAttributeValues 구성
            update_expression_parts = []
            expression_attribute_values = {}
            
            for key, value in update_data.items():
                update_expression_parts.append(f"{key} = :{key}")
                expression_attribute_values[f":{key}"] = value
            
            update_expression = "SET " + ", ".join(update_expression_parts)
            
            response = self.pages_table.update_item(
                Key={'page_id': page_id},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_attribute_values,
                ReturnValues='UPDATED_NEW'
            )
            
            logger.info(f"Pages 테이블 업데이트 성공: {page_id}")
            return True
            
        except ClientError as e:
            logger.error(f"Pages 테이블 업데이트 실패: {page_id} - {str(e)}")
            return False
    
    def create_element(self, element_data: Dict[str, Any]) -> bool:
        """
        Elements 테이블에 새 엘리먼트 생성
        
        Args:
            element_data: 엘리먼트 데이터
            
        Returns:
            성공 여부
        """
        try:
            response = self.elements_table.put_item(Item=element_data)
            logger.debug(f"Element 생성 성공: {element_data.get('elements_id')}")
            return True
            
        except ClientError as e:
            logger.error(f"Element 생성 실패: {element_data.get('elements_id')} - {str(e)}")
            return False
    
    def get_elements_by_page(self, page_id: str) -> List[Dict[str, Any]]:
        """
        페이지의 모든 엘리먼트 조회
        
        Args:
            page_id: 페이지 ID
            
        Returns:
            엘리먼트 목록
        """
        try:
            response = self.elements_table.query(
                IndexName='PageIndex',
                KeyConditionExpression=boto3.dynamodb.conditions.Key('page_id').eq(page_id)
            )
            return response.get('Items', [])
            
        except ClientError as e:
            logger.error(f"페이지 Elements 조회 실패: {page_id} - {str(e)}")
            return []