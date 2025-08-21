"""
PDF 처리 유틸리티
S3에서 PDF 파일을 다운로드하고 텍스트를 추출하는 기능 제공
"""

import os
import tempfile
import logging
from typing import List, Dict, Any, Optional

import boto3
from botocore.exceptions import ClientError

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

logger = logging.getLogger(__name__)

class PDFProcessor:
    """PDF 파일 처리 클래스"""
    
    def __init__(self, bucket_name: str):
        """
        PDF 프로세서 초기화
        
        Args:
            bucket_name: S3 버킷 이름
        """
        self.bucket_name = bucket_name
        self.s3_client = boto3.client('s3')
        
        if not fitz:
            raise ImportError("PyMuPDF (fitz)가 설치되지 않았습니다.")
    
    def _download_pdf_from_s3(self, s3_key: str) -> str:
        """
        S3에서 PDF 파일을 다운로드하여 임시 파일로 저장
        
        Args:
            s3_key: S3 객체 키
            
        Returns:
            임시 파일 경로
        """
        try:
            # 임시 파일 생성
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            temp_file_path = temp_file.name
            temp_file.close()
            
            # S3에서 파일 다운로드
            self.s3_client.download_file(self.bucket_name, s3_key, temp_file_path)
            logger.info(f"PDF 파일 다운로드 완료: {s3_key} -> {temp_file_path}")
            
            return temp_file_path
            
        except ClientError as e:
            logger.error(f"S3에서 PDF 다운로드 실패: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"PDF 다운로드 중 오류: {str(e)}")
            raise
    
    def _extract_text_from_page(self, pdf_document: fitz.Document, page_number: int) -> str:
        """
        PDF 문서의 특정 페이지에서 텍스트 추출
        
        Args:
            pdf_document: PyMuPDF 문서 객체
            page_number: 페이지 번호 (0부터 시작)
            
        Returns:
            추출된 텍스트
        """
        try:
            page = pdf_document[page_number]
            text = page.get_text()
            return text.strip() if text else ""
        except Exception as e:
            logger.error(f"페이지 {page_number + 1} 텍스트 추출 실패: {str(e)}")
            return ""
    
    def extract_text_from_all_pages(self, file_uri: str, document_id: str) -> List[Dict[str, Any]]:
        """
        PDF 파일의 모든 페이지에서 텍스트 추출
        
        Args:
            file_uri: PDF 파일 URI (S3 경로)
            document_id: 문서 ID
            
        Returns:
            페이지별 텍스트 추출 결과 리스트
        """
        temp_file_path = None
        
        try:
            # S3 키 추출
            if file_uri.startswith('s3://'):
                s3_key = file_uri.replace(f's3://{self.bucket_name}/', '')
            else:
                s3_key = file_uri
            
            if s3_key.startswith('/'):
                s3_key = s3_key[1:]
            
            logger.info(f"PDF 텍스트 추출 시작: {s3_key}")
            
            # S3에서 PDF 다운로드
            temp_file_path = self._download_pdf_from_s3(s3_key)
            
            # PDF 문서 열기
            pdf_document = fitz.open(temp_file_path)
            page_count = len(pdf_document)
            
            logger.info(f"PDF 페이지 수: {page_count}")
            
            # 모든 페이지에서 텍스트 추출
            extraction_results = []
            
            for page_number in range(page_count):
                # 페이지 ID 생성 (document_id + page_number)
                page_id = f"{document_id}#{page_number}"
                
                # 텍스트 추출
                extracted_text = self._extract_text_from_page(pdf_document, page_number)
                
                extraction_results.append({
                    'page_id': page_id,
                    'page_number': page_number + 1,  # 1부터 시작
                    'extracted_text': extracted_text,
                    'text_length': len(extracted_text) if extracted_text else 0,
                    'has_text': bool(extracted_text)
                })
                
                logger.info(f"페이지 {page_number + 1} 처리 완료 - 텍스트 길이: {len(extracted_text) if extracted_text else 0}")
            
            pdf_document.close()
            
            # 텍스트가 있는 페이지만 반환
            valid_results = [result for result in extraction_results if result['has_text']]
            
            logger.info(f"텍스트 추출 완료 - 총 페이지: {page_count}, 텍스트 있는 페이지: {len(valid_results)}")
            
            return valid_results
            
        except Exception as e:
            logger.error(f"PDF 텍스트 추출 실패: {str(e)}")
            raise
        finally:
            # 임시 파일 정리
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    logger.info(f"임시 파일 삭제: {temp_file_path}")
                except Exception as e:
                    logger.warning(f"임시 파일 삭제 실패: {str(e)}")
    
    def extract_text_from_single_page(self, file_uri: str, page_number: int) -> Optional[str]:
        """
        PDF 파일의 특정 페이지에서 텍스트 추출
        
        Args:
            file_uri: PDF 파일 URI (S3 경로)
            page_number: 페이지 번호 (1부터 시작)
            
        Returns:
            추출된 텍스트 또는 None
        """
        temp_file_path = None
        
        try:
            # S3 키 추출
            if file_uri.startswith('s3://'):
                s3_key = file_uri.replace(f's3://{self.bucket_name}/', '')
            else:
                s3_key = file_uri
            
            if s3_key.startswith('/'):
                s3_key = s3_key[1:]
            
            logger.info(f"단일 페이지 텍스트 추출 시작: {s3_key}, 페이지: {page_number}")
            
            # S3에서 PDF 다운로드
            temp_file_path = self._download_pdf_from_s3(s3_key)
            
            # PDF 문서 열기
            pdf_document = fitz.open(temp_file_path)
            page_count = len(pdf_document)
            
            # 페이지 번호 검증
            if page_number > page_count:
                logger.warning(f"요청된 페이지 {page_number}이 총 페이지 수 {page_count}를 초과합니다.")
                page_number = page_count
            elif page_number < 1:
                logger.warning(f"요청된 페이지 {page_number}이 유효하지 않습니다. 첫 번째 페이지로 조정합니다.")
                page_number = 1
            
            # 텍스트 추출 (페이지 번호는 0부터 시작)
            extracted_text = self._extract_text_from_page(pdf_document, page_number - 1)
            
            pdf_document.close()
            
            logger.info(f"페이지 {page_number} 텍스트 추출 완료 - 길이: {len(extracted_text) if extracted_text else 0}")
            
            return extracted_text if extracted_text else None
            
        except Exception as e:
            logger.error(f"단일 페이지 텍스트 추출 실패: {str(e)}")
            raise
        finally:
            # 임시 파일 정리
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    logger.info(f"임시 파일 삭제: {temp_file_path}")
                except Exception as e:
                    logger.warning(f"임시 파일 삭제 실패: {str(e)}") 