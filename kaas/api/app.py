from __future__ import annotations

from fastapi import FastAPI
from kaas.api.routes import router

app = FastAPI(
    title="KaaS — Knowledge as a Service",
    version="0.1.0",
    description="Retrieval orchestration service. REST API is the canonical interface; MCP server layer is additive.",
)

app.include_router(router, prefix="/v1")
