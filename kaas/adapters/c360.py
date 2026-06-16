"""
Dummy C360 retriever adapter.

In production this calls:
  POST /v1/retrievers/{retrieverApiName}/text-retrieval
with client-credentials auth. Here we return static placeholder chunks
so the rest of the pipeline can be developed and tested independently.
"""
from __future__ import annotations

import time
from kaas.core.models import Chunk, ChunkMetadata


DUMMY_CHUNKS: dict[str, list[dict]] = {
    "agentforce": [
        {
            "chunk_id": "dummy-agentforce-001",
            "score": 0.92,
            "text": "[DUMMY] Agentforce email channel setup: navigate to Setup > Channels > Email and configure your SMTP settings. Ensure the from-address is verified in your org.",
            "source_url": "https://help.salesforce.com/s/articleView?id=agentforce_email_setup",
            "doc_version": "spring-25",
            "section": "Email Channel Setup",
        },
        {
            "chunk_id": "dummy-agentforce-002",
            "score": 0.87,
            "text": "[DUMMY] To configure Agentforce topics and actions, open the Agent Builder and drag the desired action onto the canvas. Topics define when the agent engages.",
            "source_url": "https://help.salesforce.com/s/articleView?id=agentforce_topics",
            "doc_version": "spring-25",
            "section": "Agent Builder",
        },
    ],
    "sales_cloud": [
        {
            "chunk_id": "dummy-sales-001",
            "score": 0.88,
            "text": "[DUMMY] Sales Cloud email alerts: create a workflow rule under Process Automation > Workflow Rules, add an Email Alert action with a pre-defined email template.",
            "source_url": "https://help.salesforce.com/s/articleView?id=sales_cloud_email_alerts",
            "doc_version": "spring-25",
            "section": "Workflow Rules",
        },
    ],
    "default": [
        {
            "chunk_id": "dummy-default-001",
            "score": 0.75,
            "text": "[DUMMY] Generic Salesforce help article placeholder. Replace with real C360 retrieval output.",
            "source_url": "https://help.salesforce.com/s/articleView?id=placeholder",
            "doc_version": None,
            "section": "General",
        },
    ],
}


def retrieve(
    query: str,
    product: str,
    locale: str = "en-US",
    version: str | None = None,
    top_k: int = 5,
    retriever_name: str = "default-retriever",
) -> tuple[list[Chunk], int]:
    """Return dummy chunks and a simulated latency in ms."""
    start = time.monotonic()

    raw = DUMMY_CHUNKS.get(product, DUMMY_CHUNKS["default"])
    chunks = [
        Chunk(
            chunk_id=c["chunk_id"],
            score=c["score"],
            text=c["text"],
            source_url=c["source_url"],
            doc_version=c.get("doc_version"),
            metadata=ChunkMetadata(section=c.get("section"), locale=locale),
        )
        for c in raw[:top_k]
    ]

    elapsed_ms = int((time.monotonic() - start) * 1000)
    # Simulate realistic latency for dummy mode
    simulated_ms = elapsed_ms + 120
    return chunks, simulated_ms
