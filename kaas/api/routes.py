from __future__ import annotations

import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from kaas.api.auth import require_api_key
from kaas.core.config import settings
from kaas.core.models import (
    CandidateProduct,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    LatencyBreakdown,
    ProductResult,
    QueryIntelligence,
    RetrieveRequest,
    RetrieveResponse,
)
from kaas.adapters import c360

router = APIRouter()

AuthDep = Annotated[str, Depends(require_api_key)]


# ---------------------------------------------------------------------------
# POST /v1/retrieve
# ---------------------------------------------------------------------------

@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve(body: RetrieveRequest, _: AuthDep) -> RetrieveResponse:
    wall_start = time.monotonic()

    request_id = f"kaas-{uuid.uuid4()}"
    trace_id = f"trace-{uuid.uuid4().hex[:16]}"
    feedback_token = f"fb-{uuid.uuid4().hex}"

    # --- Query intelligence (stub) ---
    qi_start = time.monotonic()
    caller_product = body.filters.product

    # Determine candidate products: use caller-supplied product or fan out to defaults
    if caller_product:
        candidate_products = [
            CandidateProduct(
                product=caller_product,
                confidence=1.0,
                detection_method="caller_override",
            )
        ]
        ambiguous = False
        ambiguity_type = None
        suggested_clarification = None
        retrieval_scope = "top_only"
    else:
        # Placeholder: no classifier yet — fan out across two default products
        candidate_products = [
            CandidateProduct(product="agentforce", confidence=0.71, detection_method="placeholder"),
            CandidateProduct(product="sales_cloud", confidence=0.58, detection_method="placeholder"),
        ]
        ambiguous = True
        ambiguity_type = "multi_product"
        suggested_clarification = (
            "Are you asking about Agentforce or Sales Cloud? "
            "(classifier not yet wired — this is a placeholder)"
        )
        retrieval_scope = body.options.ambiguity_behavior

    qi_ms = int((time.monotonic() - qi_start) * 1000)

    # --- Retrieval ---
    if retrieval_scope == "signal_only":
        results: list[ProductResult] = []
        retrieval_wall_ms = 0
        per_product_ms: dict[str, int] = {}
    else:
        products_to_query = [cp.product for cp in candidate_products[: body.options.max_products]]
        if retrieval_scope == "top_only":
            products_to_query = products_to_query[:1]

        results = []
        per_product_ms = {}
        retrieval_wall_start = time.monotonic()

        for product in products_to_query:
            chunks, latency = c360.retrieve(
                query=body.query,
                product=product,
                locale=body.filters.locale,
                version=body.filters.version,
                top_k=body.options.top_k,
            )
            results.append(ProductResult(product=product, chunks=chunks))
            per_product_ms[product] = latency

        retrieval_wall_ms = int((time.monotonic() - retrieval_wall_start) * 1000)

    total_ms = int((time.monotonic() - wall_start) * 1000)

    return RetrieveResponse(
        request_id=request_id,
        correlation_id=body.correlation_id,
        trace_id=trace_id,
        experiment_variant="placeholder_no_classifier",
        latency_ms=LatencyBreakdown(
            query_intelligence=qi_ms,
            retrieval_total=retrieval_wall_ms,
            retrieval_per_product=per_product_ms,
            total=total_ms,
        ),
        query_intelligence=QueryIntelligence(
            normalized_query=body.query.strip(),
            intent="unknown",
            ambiguous=ambiguous,
            ambiguity_type=ambiguity_type,
            candidate_products=candidate_products,
            suggested_clarification=suggested_clarification,
            retrieval_scope_used=retrieval_scope,
            feedback_token=feedback_token,
        ),
        results=results,
    )


# ---------------------------------------------------------------------------
# POST /v1/feedback
# ---------------------------------------------------------------------------

@router.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(body: FeedbackRequest, _: AuthDep) -> FeedbackResponse:
    # TODO: write to label store (Snowflake) in production
    return FeedbackResponse(
        accepted=True,
        feedback_token=body.feedback_token,
        message="Feedback recorded (dummy — no persistent store wired yet)",
    )


# ---------------------------------------------------------------------------
# GET /v1/health
# ---------------------------------------------------------------------------

@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        classifier_version=settings.CLASSIFIER_VERSION,
        taxonomy_version=settings.TAXONOMY_VERSION,
        c360_connectivity=settings.C360_CONNECTIVITY,
    )
