#!/usr/bin/env python3
"""
Simple Deep Research Agent - 핵심 기능만 포함한 단순 버전
"""
import asyncio
import requests
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
API_BASE_URL = "https://k19cn9zp70.execute-api.us-west-2.amazonaws.com"


class SimpleDocumentAnalyzer:
    """간단한 문서 분석기"""
    
    def __init__(self, index_id: str):
        self.index_id = index_id
        self.rate_limit_delay = 2.0  # 2초마다 한 번씩 처리
    
    def get_segment_content(self, document_id: str, segment_id: str) -> Dict[str, Any]:
        """세그먼트 내용을 가져와서 파싱"""
        url = f"{API_BASE_URL}/api/documents/{document_id}/segments/{segment_id}"
        params = {"index_id": self.index_id}
        
        try:
            response = requests.get(url, params=params, timeout=30)
            if response.status_code != 200:
                return {"success": False, "error": f"API error: {response.status_code}"}
            
            data = response.json()
            analysis_results = data.get("analysis_results", [])
            
            # 모든 분석 결과를 텍스트로 결합
            combined_text = []
            for result in analysis_results:
                tool_name = result.get("tool_name", "unknown")
                content = result.get("content", "")
                if content:
                    combined_text.append(f"[{tool_name}]\n{content}")
            
            full_content = "\n\n".join(combined_text)
            
            return {
                "success": True,
                "content": full_content,
                "segment_id": segment_id,
                "analysis_count": len(analysis_results)
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def analyze_document(self, document_id: str, query: str) -> Dict[str, Any]:
        """문서 전체 분석"""
        logger.info(f"Starting analysis of document {document_id}")
        
        # 1. 문서 정보 가져오기
        status_url = f"{API_BASE_URL}/api/documents/{document_id}/status"
        try:
            response = requests.get(status_url)
            if response.status_code != 200:
                return {"success": False, "error": "Document not found"}
            
            doc_info = response.json()
            segment_ids = doc_info.get("segment_ids", [])
            total_segments = len(segment_ids)
            
            logger.info(f"Found {total_segments} segments to analyze")
            
        except Exception as e:
            return {"success": False, "error": f"Failed to get document info: {e}"}
        
        # 2. 각 세그먼트 분석
        results = []
        successful = 0
        failed = 0
        
        for i, segment_id in enumerate(segment_ids):
            logger.info(f"Processing segment {i+1}/{total_segments}: {segment_id}")
            
            # Rate limiting
            time.sleep(self.rate_limit_delay)
            
            result = self.get_segment_content(document_id, segment_id)
            if result["success"]:
                results.append(result)
                successful += 1
                logger.info(f"✅ Success - {result['analysis_count']} analyses, {len(result['content'])} chars")
            else:
                failed += 1
                logger.error(f"❌ Failed: {result['error']}")
        
        # 3. 결과 요약 생성
        total_content_length = sum(len(r.get("content", "")) for r in results)
        total_analyses = sum(r.get("analysis_count", 0) for r in results)
        
        summary = f"""
문서 분석 완료

📊 통계:
- 총 세그먼트: {total_segments}
- 성공: {successful}
- 실패: {failed}
- 총 분석 결과: {total_analyses}개
- 총 콘텐츠 길이: {total_content_length:,} 문자

🔍 질의: {query}

📄 분석된 내용의 일부:
{results[0]['content'][:500] if results else 'No content'}...
        """
        
        # 4. 결과 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("./analysis_results")
        output_dir.mkdir(exist_ok=True)
        
        output_file = output_dir / f"analysis_{document_id}_{timestamp}.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(summary)
            f.write("\n\n" + "="*80 + "\n")
            f.write("상세 분석 결과\n")
            f.write("="*80 + "\n\n")
            
            for i, result in enumerate(results):
                f.write(f"세그먼트 {i+1}: {result['segment_id']}\n")
                f.write("-" * 40 + "\n")
                f.write(result.get("content", "No content") + "\n\n")
        
        logger.info(f"Results saved to: {output_file}")
        
        return {
            "success": True,
            "summary": summary,
            "total_segments": total_segments,
            "successful": successful,
            "failed": failed,
            "output_file": str(output_file),
            "results": results
        }


def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Simple Document Analyzer")
    parser.add_argument("document_id", help="Document ID to analyze")
    parser.add_argument("query", help="Analysis query")
    parser.add_argument("--index-id", required=True, help="Index ID")
    parser.add_argument("--delay", type=float, default=2.0, help="Rate limit delay in seconds")
    
    args = parser.parse_args()
    
    # Create analyzer
    analyzer = SimpleDocumentAnalyzer(args.index_id)
    analyzer.rate_limit_delay = args.delay
    
    # Run analysis
    result = analyzer.analyze_document(args.document_id, args.query)
    
    if result["success"]:
        print("\n" + "="*80)
        print("✅ ANALYSIS COMPLETED")
        print("="*80)
        print(result["summary"])
        print(f"📁 Full results: {result['output_file']}")
    else:
        print("\n" + "="*80)
        print("❌ ANALYSIS FAILED")
        print("="*80)
        print(f"Error: {result['error']}")


if __name__ == "__main__":
    main()