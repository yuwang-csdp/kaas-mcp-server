from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


# ---------- Request models ----------

class RetrieveFilters(BaseModel):
    locale: str = "en-US"
    product: Optional[str] = None
    version: Optional[str] = None


class RetrieveOptions(BaseModel):
    ambiguity_behavior: Literal["fan_out", "top_only", "signal_only"] = "fan_out"
    top_k: int = Field(5, ge=1, le=20)
    include_raw_chunks: bool = True
    max_products: int = Field(3, ge=1, le=5)


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    agent_id: str
    filters: RetrieveFilters = Field(default_factory=RetrieveFilters)
    options: RetrieveOptions = Field(default_factory=RetrieveOptions)
    caller_context: Optional[dict] = None
    correlation_id: Optional[str] = None


class FeedbackRequest(BaseModel):
    feedback_token: str
    correct_product: str
    feedback_type: Literal["product_correction", "irrelevant_chunks", "missing_content"]
    agent_id: str
    session_id: Optional[str] = None


# ---------- Response models ----------

class ChunkMetadata(BaseModel):
    section: Optional[str] = None
    locale: str = "en-US"


class Chunk(BaseModel):
    chunk_id: str
    score: float
    text: str
    source_url: str
    doc_version: Optional[str] = None
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata)


class ProductResult(BaseModel):
    product: str
    chunks: list[Chunk]


class CandidateProduct(BaseModel):
    product: str
    confidence: float
    detection_method: str


class QueryIntelligence(BaseModel):
    normalized_query: str
    intent: Literal["how_to", "troubleshoot", "reference", "unknown"] = "unknown"
    ambiguous: bool
    ambiguity_type: Optional[Literal["multi_product", "unclear_intent"]] = None
    candidate_products: list[CandidateProduct]
    suggested_clarification: Optional[str] = None
    retrieval_scope_used: str
    feedback_token: str


class LatencyBreakdown(BaseModel):
    query_intelligence: int
    retrieval_total: int
    retrieval_per_product: dict[str, int]
    total: int


class RetrieveResponse(BaseModel):
    request_id: str
    correlation_id: Optional[str]
    trace_id: str
    experiment_variant: str
    latency_ms: LatencyBreakdown
    query_intelligence: QueryIntelligence
    results: list[ProductResult]


class FeedbackResponse(BaseModel):
    accepted: bool
    feedback_token: str
    message: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    classifier_version: str
    taxonomy_version: str
    c360_connectivity: str
