"""
PDF Processing Utility
Provides functions to download PDF files from S3 and extract text
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
    """PDF File Processing Class"""
    
    def __init__(self, bucket_name: Optional[str] = None):
        """
        Initialize PDF processor
        
        Args:
            bucket_name: S3 bucket name (optional, can be extracted from file_uri)
        """
        self.bucket_name = bucket_name
        self.s3_client = boto3.client('s3')
        
        if not fitz:
            raise ImportError("PyMuPDF (fitz) is not installed.")
    
    def _extract_bucket_and_key_from_uri(self, file_uri: str) -> tuple[str, str]:
        """
        Extract S3 bucket name and key from file_uri
        
        Args:
            file_uri: S3 file URI (e.g., s3://bucket-name/path/to/file.pdf)
        
        Returns:
            (bucket_name, s3_key) tuple
        """
        if file_uri.startswith('s3://'):
            # s3://bucket-name/path/to/file.pdf 형식
            uri_parts = file_uri[5:].split('/', 1)  # s3:// 제거 후 분할
            bucket_name = uri_parts[0]
            s3_key = uri_parts[1] if len(uri_parts) > 1 else ''
        else:
            # 버킷명이 없는 경우 기본 버킷 사용
            if not self.bucket_name:
                raise ValueError("file_uri에 버킷명이 없고 기본 버킷도 설정되지 않았습니다.")
            bucket_name = self.bucket_name
            s3_key = file_uri.lstrip('/')
        
        return bucket_name, s3_key

    def _download_pdf_from_s3(self, bucket_name: str, s3_key: str) -> str:
        """
        Download PDF file from S3 and save as a temporary file
        
        Args:
            bucket_name: S3 bucket name
            s3_key: S3 object key
        
        Returns:
            Temporary file path
        """
        try:
            # 임시 파일 생성
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            temp_file_path = temp_file.name
            temp_file.close()
            
            # S3에서 파일 다운로드
            self.s3_client.download_file(bucket_name, s3_key, temp_file_path)
            logger.info(f"PDF file download complete: s3://{bucket_name}/{s3_key} -> {temp_file_path}")
            
            return temp_file_path
            
        except ClientError as e:
            logger.error(f"Failed to download PDF from S3: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error during PDF download: {str(e)}")
            raise

    def extract_text_from_pdf(self, file_uri: str) -> List[str]:
        """
        Extract text from all pages of a PDF file and return a list of text per page
        
        Args:
            file_uri: PDF file URI (S3 path)
        
        Returns:
            List of text per page (index = page number)
        """
        temp_file_path = None
        
        try:
            # 버킷명과 S3 키 추출
            bucket_name, s3_key = self._extract_bucket_and_key_from_uri(file_uri)
            
            logger.info(f"Starting PDF text extraction: s3://{bucket_name}/{s3_key}")
            
            # S3에서 PDF 다운로드
            temp_file_path = self._download_pdf_from_s3(bucket_name, s3_key)
            
            # PDF 문서 열기
            pdf_document = fitz.open(temp_file_path)
            page_count = len(pdf_document)
            
            logger.info(f"PDF page count: {page_count}")
            
            # 모든 페이지에서 텍스트 추출
            page_texts = []
            
            for page_number in range(page_count):
                # 텍스트 추출
                extracted_text = self._extract_text_from_page(pdf_document, page_number)
                page_texts.append(extracted_text)
                
                logger.debug(f"Page {page_number + 1} processed - text length: {len(extracted_text) if extracted_text else 0}")
            
            pdf_document.close()
            
            logger.info(f"PDF text extraction complete - total pages: {page_count}")
            
            return page_texts
            
        except Exception as e:
            logger.error(f"PDF text extraction failed: {str(e)}")
            raise
        finally:
            # 임시 파일 정리
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    logger.info(f"Temporary file deleted: {temp_file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file: {str(e)}")
    
    def _extract_text_from_page(self, pdf_document: fitz.Document, page_number: int) -> str:
        """
        Extract text from a specific page of a PDF document
        
        Args:
            pdf_document: PyMuPDF document object
            page_number: Page number (starts from 0)
        
        Returns:
            Extracted text
        """
        try:
            page = pdf_document[page_number]
            text = page.get_text()
            return text.strip() if text else ""
        except Exception as e:
            logger.error(f"Failed to extract text from page {page_number + 1}: {str(e)}")
            return ""
    
    def extract_text_from_all_pages(self, file_uri: str, document_id: str) -> List[Dict[str, Any]]:
        """
        Extract text from all pages of a PDF file
        
        Args:
            file_uri: PDF file URI (S3 path)
            document_id: Document ID
        
        Returns:
            List of text extraction results per page
        """
        temp_file_path = None
        
        try:
            # 버킷명과 S3 키 추출
            bucket_name, s3_key = self._extract_bucket_and_key_from_uri(file_uri)
            
            logger.info(f"Starting PDF text extraction: s3://{bucket_name}/{s3_key}")
            
            # S3에서 PDF 다운로드
            temp_file_path = self._download_pdf_from_s3(bucket_name, s3_key)
            
            # PDF 문서 열기
            pdf_document = fitz.open(temp_file_path)
            page_count = len(pdf_document)
            
            logger.info(f"PDF page count: {page_count}")
            
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
                
                logger.info(f"Page {page_number + 1} processed - text length: {len(extracted_text) if extracted_text else 0}")
            
            pdf_document.close()
            
            # 텍스트가 있는 페이지만 반환
            valid_results = [result for result in extraction_results if result['has_text']]
            
            logger.info(f"Text extraction complete - total pages: {page_count}, pages with text: {len(valid_results)}")
            
            return valid_results
            
        except Exception as e:
            logger.error(f"PDF text extraction failed: {str(e)}")
            raise
        finally:
            # 임시 파일 정리
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    logger.info(f"Temporary file deleted: {temp_file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file: {str(e)}")
    
    def extract_text_from_single_page(self, file_uri: str, page_number: int) -> Optional[str]:
        """
        Extract text from a specific page of a PDF file
        
        Args:
            file_uri: PDF file URI (S3 path)
            page_number: Page number (starts from 1)
        
        Returns:
            Extracted text or None
        """
        temp_file_path = None
        
        try:
            # 버킷명과 S3 키 추출
            bucket_name, s3_key = self._extract_bucket_and_key_from_uri(file_uri)
            
            logger.info(f"Starting single page text extraction: s3://{bucket_name}/{s3_key}, page: {page_number}")
            
            # S3에서 PDF 다운로드
            temp_file_path = self._download_pdf_from_s3(bucket_name, s3_key)
            
            # PDF 문서 열기
            pdf_document = fitz.open(temp_file_path)
            page_count = len(pdf_document)
            
            # 페이지 번호 검증
            if page_number > page_count:
                logger.warning(f"Requested page {page_number} exceeds total page count {page_count}.")
                page_number = page_count
            elif page_number < 1:
                logger.warning(f"Requested page {page_number} is invalid. Adjusting to first page.")
                page_number = 1
            
            # 텍스트 추출 (페이지 번호는 0부터 시작)
            extracted_text = self._extract_text_from_page(pdf_document, page_number - 1)
            
            pdf_document.close()
            
            logger.info(f"Page {page_number} text extraction complete - length: {len(extracted_text) if extracted_text else 0}")
            
            return extracted_text if extracted_text else None
            
        except Exception as e:
            logger.error(f"Failed to extract text from single page: {str(e)}")
            raise
        finally:
            # 임시 파일 정리
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    logger.info(f"Temporary file deleted: {temp_file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file: {str(e)}") 