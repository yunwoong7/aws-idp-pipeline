"""
VerificationAgent State Models
"""

from typing import Dict, List, Any, Optional, TypedDict
from langchain_core.messages import BaseMessage
from pydantic import BaseModel

class VerificationClaim(BaseModel):
    """Individual verification claim"""
    id: str
    claim: str
    status: str  # VERIFIED, CONTRADICTED, NOT_FOUND
    evidence: Optional[str] = None
    source_document_id: Optional[str] = None
    confidence: Optional[float] = None

class VerificationSummary(BaseModel):
    """Verification summary statistics"""
    total_claims: int = 0
    verified: int = 0
    contradicted: int = 0
    not_found: int = 0
    
    def update_from_claims(self, claims: List[VerificationClaim]):
        """Update summary from claims list"""
        self.total_claims = len(claims)
        self.verified = len([c for c in claims if c.status == "VERIFIED"])
        self.contradicted = len([c for c in claims if c.status == "CONTRADICTED"])
        self.not_found = len([c for c in claims if c.status == "NOT_FOUND"])

class VerificationState(TypedDict, total=False):
    """VerificationAgent state model"""
    # Input documents
    source_document_ids: List[str]
    target_document_id: str
    index_id: Optional[str]
    
    # Messages
    messages: List[BaseMessage]
    
    # Document contents
    source_documents_content: Dict[str, str]  # document_id -> content
    target_document_content: str
    
    # Extracted claims
    extracted_claims: List[str]
    
    # Verification results (stored as dicts for JSON serialization)
    verification_claims: List[Dict[str, Any]]
    
    # Processing state
    current_phase: str  # init, loading, extraction, verification, summary
    current_claim_index: int
    
    # Summary (as dict for JSON serialization)
    summary: Dict[str, Any]
    
    # Error handling
    error: Optional[str]
    
    # Metadata
    model_id: str
    started_at: Optional[str]
    completed_at: Optional[str]

class InputState(BaseModel):
    """Input state for VerificationAgent"""
    source_document_ids: List[str]
    target_document_id: str
    index_id: Optional[str] = None
    model_id: str = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    messages: List[BaseMessage] = []