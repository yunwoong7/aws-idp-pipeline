"""
VerificationAgent Workflow Nodes
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from langchain_core.messages import AIMessage, HumanMessage

from ..state.model import VerificationState, VerificationClaim, VerificationSummary
from ..prompt import prompt_manager
from ..utils import (
    parse_json_response,
    extract_claims_fallback,
    validate_content_length,
    validate_verification_status,
    safe_float_conversion,
    VerificationConfig
)

logger = logging.getLogger(__name__)

async def initialization_node(state: VerificationState) -> VerificationState:
    """Initialize verification process"""
    source_count = len(state.get('source_document_ids', []))
    target_id = state.get('target_document_id')
    logger.info(f"Starting verification process: {source_count} source documents, target: {target_id}")
    
    # Initialize state
    state.update({
        "current_phase": "init",
        "current_claim_index": 0,
        "extracted_claims": [],
        "verification_claims": [],
        "source_documents_content": {},
        "target_document_content": "",
        "started_at": datetime.now().isoformat(),
        "summary": VerificationSummary().dict()
    })
    
    return state

async def document_loading_node(state: VerificationState) -> VerificationState:
    """Load document contents from storage"""
    logger.info("Loading document contents from OpenSearch")
    
    state["current_phase"] = "loading"
    
    try:
        source_ids = state.get("source_document_ids", [])
        target_id = state.get("target_document_id", "")
        index_id = state.get("index_id", "")
        
        # Import document content service
        from ..document_content_service import get_document_content
        logger.debug(f"Document content service available for index: {index_id}")
        
        # Load source documents
        source_contents = {}
        for doc_id in source_ids:
            try:
                content = await get_document_content(doc_id, index_id)
                if validate_content_length(content, f"Source document {doc_id}"):
                    source_contents[doc_id] = content.strip()
                    logger.debug(f"Loaded source document {doc_id}: {len(content)} characters")
                else:
                    logger.error(f"Source document {doc_id} has insufficient content")
                    state["error"] = f"Source document {doc_id} has insufficient content"
                    return state
            except Exception as e:
                logger.error(f"Failed to load source document {doc_id}: {e}")
                state["error"] = f"Failed to load source document {doc_id}: {str(e)}"
                return state
        
        state["source_documents_content"] = source_contents
        logger.info(f"Successfully loaded {len(source_contents)} source documents")
        
        # Load target document
        if target_id:
            try:
                content = await get_document_content(target_id, index_id)
                if validate_content_length(content, f"Target document {target_id}"):
                    state["target_document_content"] = content.strip()
                    logger.debug(f"Loaded target document {target_id}: {len(content)} characters")
                else:
                    logger.error(f"Target document {target_id} has insufficient content")
                    state["error"] = f"Target document {target_id} has insufficient content"
                    return state
            except Exception as e:
                logger.error(f"Failed to load target document {target_id}: {e}")
                state["error"] = f"Failed to load target document {target_id}: {str(e)}"
                return state
    
    except ImportError as e:
        logger.error(f"Document content service not available: {e}")
        state["error"] = "Document content service not available"
        return state
    except Exception as e:
        logger.error(f"Document loading failed: {e}")
        state["error"] = f"Failed to load documents: {str(e)}"
        return state
    
    return state

async def claim_extraction_node(state: VerificationState, model) -> VerificationState:
    """Extract verifiable claims from target document"""
    logger.info("Extracting verifiable claims from target document")
    
    state["current_phase"] = "extraction"
    
    target_content = state.get("target_document_content", "")
    if not target_content:
        logger.error("No target document content available for claim extraction")
        state["error"] = "No target document content available"
        return state
    
    try:
        # Format prompt for claim extraction
        prompt = prompt_manager.format_prompt(
            "claim_extraction",
            target_content=target_content
        )
        
        # Create message and invoke model
        message = HumanMessage(content=prompt)
        response = await model.ainvoke([message])
        
        # Parse response
        response_text = response.content
        logger.debug(f"Claim extraction response length: {len(response_text)}")
        
        # Try to parse JSON response
        extracted_claims = parse_json_response(response_text, "array")
        
        if extracted_claims and isinstance(extracted_claims, list):
            # Filter and validate claims
            valid_claims = [
                claim for claim in extracted_claims 
                if isinstance(claim, str) and len(claim.strip()) >= VerificationConfig.MIN_CLAIM_LENGTH
            ]
            state["extracted_claims"] = valid_claims[:VerificationConfig.MAX_CLAIMS_LIMIT]
            logger.info(f"Successfully extracted {len(valid_claims)} valid claims")
        else:
            # Fallback to text extraction
            logger.warning("JSON parsing failed, using fallback text extraction")
            fallback_claims = extract_claims_fallback(response_text)
            if fallback_claims:
                state["extracted_claims"] = fallback_claims
                logger.info(f"Extracted {len(fallback_claims)} claims using fallback method")
            else:
                logger.error("Could not extract any valid claims from target document")
                state["error"] = "Could not extract any valid claims from target document"
                return state
    
    except Exception as e:
        logger.error(f"Claim extraction failed: {e}")
        state["error"] = f"Claim extraction failed: {str(e)}"
        return state
    
    return state

async def claim_verification_node(state: VerificationState, model) -> VerificationState:
    """Verify extracted claims against source documents"""
    logger.info("Starting claim verification against source documents")
    
    state["current_phase"] = "verification"
    
    extracted_claims = state.get("extracted_claims", [])
    source_contents = state.get("source_documents_content", {})
    
    if not extracted_claims:
        logger.error("No claims available for verification")
        state["error"] = "No claims to verify"
        return state
    
    if not source_contents:
        logger.error("No source documents available for verification")
        state["error"] = "No source documents available"
        return state
    
    # Prepare source documents text
    source_docs_text = "\n\n".join([
        f"SOURCE DOCUMENT {doc_id}:\n{content}"
        for doc_id, content in source_contents.items()
    ])
    
    verified_claims = []
    total_claims = len(extracted_claims)
    
    # Verify each claim individually for better accuracy
    for i, claim in enumerate(extracted_claims):
        try:
            state["current_claim_index"] = i
            logger.info(f"Verifying claim {i+1}/{total_claims}: {claim[:50]}...")
            
            # Format prompt for single claim verification
            prompt = prompt_manager.format_prompt(
                "single_claim_verification",
                claim=claim,
                source_documents=source_docs_text
            )
            
            # Create message and invoke model
            message = HumanMessage(content=prompt)
            response = await model.ainvoke([message])
            
            # Parse verification result
            response_text = response.content
            result = parse_json_response(response_text, "object")
            
            if result and isinstance(result, dict):
                # Validate and normalize result
                status = validate_verification_status(result.get("status", "NOT_FOUND"))
                confidence = safe_float_conversion(result.get("confidence", 0.0))
                
                verification_claim = VerificationClaim(
                    id=f"claim_{i+1}",
                    claim=claim,
                    status=status,
                    evidence=result.get("evidence", ""),
                    source_document_id=result.get("source_document_id"),
                    confidence=confidence
                )
                
                verified_claims.append(verification_claim)
                logger.debug(f"Claim {i+1} verified with status: {status}")
                
            else:
                logger.warning(f"Failed to parse verification result for claim {i+1}")
                # Create fallback result
                verification_claim = VerificationClaim(
                    id=f"claim_{i+1}",
                    claim=claim,
                    status="NOT_FOUND",
                    evidence="",
                    confidence=VerificationConfig.DEFAULT_CONFIDENCE
                )
                verified_claims.append(verification_claim)
        
        except Exception as e:
            logger.error(f"Failed to verify claim {i+1}: {e}")
            # Create error result
            verification_claim = VerificationClaim(
                id=f"claim_{i+1}",
                claim=claim,
                status="NOT_FOUND",
                evidence="",
                confidence=VerificationConfig.DEFAULT_CONFIDENCE
            )
            verified_claims.append(verification_claim)
    
    # Convert VerificationClaim objects to dicts for state storage
    state["verification_claims"] = [claim.dict() for claim in verified_claims]
    
    # Update summary
    summary = VerificationSummary()
    summary.update_from_claims(verified_claims)
    summary_dict = summary.dict()
    state["summary"] = summary_dict
    
    logger.info(f"Verification complete: {summary_dict['total_claims']} total, "
                f"{summary_dict['verified']} verified, {summary_dict['contradicted']} contradicted, "
                f"{summary_dict['not_found']} not found")
    
    return state

async def summary_generation_node(state: VerificationState, model) -> VerificationState:
    """Generate comprehensive verification summary"""
    logger.info("Generating verification summary report")
    
    state["current_phase"] = "summary"
    state["completed_at"] = datetime.now().isoformat()
    
    try:
        verification_claims = state.get("verification_claims", [])
        target_doc_id = state.get("target_document_id", "")
        source_doc_ids = state.get("source_document_ids", [])
        
        if not verification_claims:
            logger.warning("No verification claims available for summary generation")
            return state
        
        # Format verification results for summary
        results_text = "\n".join([
            f"- Claim: {claim['claim']}\n  Status: {claim['status']}\n  Evidence: {claim.get('evidence', 'N/A')}\n"
            for claim in verification_claims
        ])
        
        # Generate summary using model
        prompt = prompt_manager.format_prompt(
            "summary_generation",
            verification_results=results_text,
            target_document_id=target_doc_id,
            source_document_ids=", ".join(source_doc_ids)
        )
        
        message = HumanMessage(content=prompt)
        response = await model.ainvoke([message])
        
        # Add summary to messages
        summary_message = AIMessage(content=response.content)
        current_messages = state.get("messages", [])
        current_messages.append(summary_message)
        state["messages"] = current_messages
        
        logger.info("Verification summary generated successfully")
        
    except Exception as e:
        logger.error(f"Summary generation failed: {e}")
        state["error"] = f"Summary generation failed: {str(e)}"
    
    return state