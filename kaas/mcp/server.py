"""
KaaS MCP Server — thin wrapper over the REST core.

Exposes three tools:
  - search_knowledge  →  POST /v1/retrieve
  - submit_feedback   →  POST /v1/feedback
  - get_health        →  GET  /v1/health

Run standalone:
  python -m kaas.mcp.server

Or mount alongside the FastAPI app (stdio transport for Agentforce / Claude Desktop).
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

_BASE_URL = os.getenv("KAAS_BASE_URL", "http://localhost:8000")
_API_KEY = os.getenv("KAAS_MCP_API_KEY", "dev-key-1")
_HEADERS = {"X-API-Key": _API_KEY, "Content-Type": "application/json"}

mcp = FastMCP("kaas")


def _client() -> httpx.Client:
    return httpx.Client(base_url=_BASE_URL, headers=_HEADERS, timeout=30)


# ---------------------------------------------------------------------------
# Tool: search_knowledge
# ---------------------------------------------------------------------------

@mcp.tool()
def search_knowledge(
    query: str,
    agent_id: str,
    locale: str = "en-US",
    product: str | None = None,
    version: str | None = None,
    ambiguity_behavior: str = "fan_out",
    top_k: int = 5,
    max_products: int = 3,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Retrieve knowledge chunks from KaaS.

    Returns grounded, product-scoped chunks plus a query_intelligence block
    that includes ambiguity signals and a suggested clarification when the
    query spans multiple products.

    Args:
        query: The user's natural-language question.
        agent_id: Identifier of the calling agent (e.g. "help-agent-orgcs").
        locale: BCP-47 locale for content filtering (default "en-US").
        product: Optional product override — skip classifier if already known.
        version: Optional release version filter (e.g. "spring-25").
        ambiguity_behavior: "fan_out" | "top_only" | "signal_only".
        top_k: Maximum chunks to return per product (1–20).
        max_products: Maximum products to fan out to (1–5).
        correlation_id: Caller-supplied ID propagated through all downstream calls.
    """
    payload: dict[str, Any] = {
        "query": query,
        "agent_id": agent_id,
        "filters": {"locale": locale},
        "options": {
            "ambiguity_behavior": ambiguity_behavior,
            "top_k": top_k,
            "max_products": max_products,
        },
    }
    if product:
        payload["filters"]["product"] = product
    if version:
        payload["filters"]["version"] = version
    if correlation_id:
        payload["correlation_id"] = correlation_id

    with _client() as client:
        resp = client.post("/v1/retrieve", json=payload)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Tool: submit_feedback
# ---------------------------------------------------------------------------

@mcp.tool()
def submit_feedback(
    feedback_token: str,
    correct_product: str,
    agent_id: str,
    feedback_type: str = "product_correction",
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    Submit a product correction or quality signal after a retrieval response.

    Use the feedback_token returned by search_knowledge to link this correction
    back to the original request for classifier training.

    Args:
        feedback_token: Opaque token from the search_knowledge response.
        correct_product: The product the user indicated was correct.
        agent_id: Identifier of the calling agent.
        feedback_type: "product_correction" | "irrelevant_chunks" | "missing_content".
        session_id: Optional session identifier for grouping corrections.
    """
    payload: dict[str, Any] = {
        "feedback_token": feedback_token,
        "correct_product": correct_product,
        "feedback_type": feedback_type,
        "agent_id": agent_id,
    }
    if session_id:
        payload["session_id"] = session_id

    with _client() as client:
        resp = client.post("/v1/feedback", json=payload)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Tool: get_health
# ---------------------------------------------------------------------------

@mcp.tool()
def get_health() -> dict[str, Any]:
    """
    Check KaaS service health.

    Returns the service status, classifier version, taxonomy version, and
    C360 connectivity status.
    """
    with _client() as client:
        resp = client.get("/v1/health")
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Entry point — stdio transport (for Claude Desktop / Agentforce MCP client)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
