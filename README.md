# KaaS — Knowledge as a Service

A **stateless retrieval orchestration service** that sits between any agent caller and Salesforce knowledge sources (C360 hybrid search, Data Graph). It owns query understanding, parallel fan-out retrieval, response packaging, and observability — so consuming agents (Help Agent, Slack Agent, Informatica Agent) don't have to.

> Design doc: `kaas_design_working_new.md` (living doc, not final spec)
> Forge ML platform: https://launchpad.forge-prod.sfdcbt.net/projects/141

---

## Architecture

```
  OrgCS (hosted)
  ┌──────────────────────┐
  │  Help Agent          │──────────────────────────────────────────┐
  │  Slack Agent         │  (same agent, different channel surface) │
  └──────────────────────┘                                          │
                                                                     │
  Informatica Agent ───────────────────────────────────────────────┤
  Future agents    ───────────────────────────────────────────────┤
                                                                     │ HTTPS (API key)
                                                                     ▼
                      ┌─────────────────────────────────────┐
                      │            KaaS Service              │
                      │      (Forge EKS, always-on)         │
                      │                                     │
                      │  ┌──────────────────────────────┐  │
                      │  │   Retrieval Orchestrator      │  │
                      │  │  (parallel fan-out + merge)   │  │
                      │  └──────┬────────────┬───────────┘  │
                      │         │            │              │
                      │  ┌──────▼──┐  ┌─────▼──────────┐  │
                      │  │  C360   │  │  Data Graph     │  │
                      │  │  Hybrid │  │  Adapter (v2)   │  │
                      │  │  Search │  │  (flagged off)  │  │
                      │  └─────────┘  └────────────────┘  │
                      │                                     │
                      │  ┌──────────────────────────────┐  │
                      │  │  Logging / Tracing / Exp Mgmt │  │
                      │  └──────────────────────────────┘  │
                      └─────────────────────────────────────┘
```

**Interface layers:**
- **Layer 1 — REST API (MVP, canonical):** clean JSON contract, any HTTP client. Auth, versioning, and observability live here.
- **Layer 2 — MCP server (v1.1, additive):** thin wrapper exposing the same capabilities as named MCP tools for Agentforce/OrgCS native integration. REST callers are unaffected.

---

## Project Structure

```
kaas-mcp-server/
├── main.py                    # uvicorn entry point
├── pyproject.toml
├── .env.example
└── kaas/
    ├── core/
    │   ├── config.py          # settings loaded from env vars
    │   └── models.py          # Pydantic request/response models
    ├── adapters/
    │   └── c360.py            # C360 retriever adapter (dummy placeholder)
    ├── api/
    │   ├── auth.py            # X-API-Key header validation
    │   ├── routes.py          # POST /v1/retrieve  POST /v1/feedback  GET /v1/health
    │   └── app.py             # FastAPI app
    └── mcp/
        └── server.py          # MCP server — search_knowledge, submit_feedback, get_health
```

---

## Quickstart

```bash
pip install -e ".[dev]"

cp .env.example .env
# edit .env — set KAAS_API_KEYS to your own keys

# Start REST API
python main.py
# or: uvicorn kaas.api.app:app --reload

# Interactive API docs
open http://localhost:8000/docs
```

### Running the MCP server

The MCP server proxies all calls to the running REST API over stdio (for Claude Desktop / Agentforce MCP client):

```bash
KAAS_BASE_URL=http://localhost:8000 \
KAAS_MCP_API_KEY=dev-key-1 \
python -m kaas.mcp.server
```

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kaas": {
      "command": "python",
      "args": ["-m", "kaas.mcp.server"],
      "env": {
        "KAAS_BASE_URL": "http://localhost:8000",
        "KAAS_MCP_API_KEY": "your-key"
      }
    }
  }
}
```

---

## API Reference

### `POST /v1/retrieve`

Main retrieval endpoint. Accepts a query + caller context, runs query intelligence, fans out to C360 hybrid search per detected product, and returns chunks grouped by product with an ambiguity signal block.

**Request**
```json
{
  "query": "how do I set up email settings",
  "agent_id": "help-agent-orgcs",
  "filters": {
    "locale": "en-US",
    "product": "agentforce",
    "version": "spring-25"
  },
  "options": {
    "ambiguity_behavior": "fan_out",
    "top_k": 5,
    "max_products": 3
  },
  "caller_context": {
    "tenant_id": "...",
    "user_id": "..."
  },
  "correlation_id": "abc-123"
}
```

`product` and `version` in `filters` are optional. If `product` is omitted, KaaS runs the product classifier and fans out. `caller_context` is optional; when absent, graph lookup is skipped.

`ambiguity_behavior`:
- `fan_out` *(default)* — retrieve across all candidate products, return chunks labeled by product
- `top_only` — retrieve from highest-confidence product only, still signal ambiguity
- `signal_only` — return only the ambiguity signal, no chunks

**Response**
```json
{
  "request_id": "kaas-uuid-...",
  "correlation_id": "abc-123",
  "trace_id": "trace-...",
  "experiment_variant": "classifier_v1_rules_only",
  "latency_ms": {
    "query_intelligence": 42,
    "retrieval_total": 310,
    "retrieval_per_product": { "agentforce": 295, "sales_cloud": 310 },
    "total": 368
  },
  "query_intelligence": {
    "normalized_query": "how do I configure email settings",
    "intent": "how_to",
    "ambiguous": true,
    "ambiguity_type": "multi_product",
    "candidate_products": [
      { "product": "agentforce",  "confidence": 0.71, "detection_method": "rule" },
      { "product": "sales_cloud", "confidence": 0.58, "detection_method": "rule" }
    ],
    "suggested_clarification": "Are you asking about email settings in Agentforce or Sales Cloud?",
    "retrieval_scope_used": "fan_out",
    "feedback_token": "fb-opaque-token-..."
  },
  "results": [
    {
      "product": "agentforce",
      "chunks": [
        {
          "chunk_id": "c-001",
          "score": 0.91,
          "text": "...",
          "source_url": "https://help.salesforce.com/...",
          "doc_version": "spring-25",
          "metadata": { "section": "Email Channel Setup", "locale": "en-US" }
        }
      ]
    }
  ]
}
```

---

### `POST /v1/feedback`

Submit a product correction or quality signal after a retrieval response. The `feedback_token` from `/v1/retrieve` links the correction back to the original request for classifier training (Phase 2).

```json
{
  "feedback_token": "fb-opaque-token-...",
  "correct_product": "sales_cloud",
  "feedback_type": "product_correction",
  "agent_id": "help-agent-orgcs",
  "session_id": "optional"
}
```

`feedback_type`: `product_correction` | `irrelevant_chunks` | `missing_content`

---

### `GET /v1/health`

Returns service liveness + dependency status.

```json
{
  "status": "ok",
  "classifier_version": "rules-v0",
  "taxonomy_version": "0.1.0",
  "c360_connectivity": "dummy"
}
```

---

## MCP Tools

| Tool | Maps to | Description |
|------|---------|-------------|
| `search_knowledge` | `POST /v1/retrieve` | Retrieve product-scoped knowledge chunks |
| `submit_feedback` | `POST /v1/feedback` | Submit a correction signal for classifier training |
| `get_health` | `GET /v1/health` | Check service health and connectivity |

---

## Configuration

All settings are loaded from environment variables (or `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `KAAS_API_KEYS` | `dev-key-1,dev-key-2` | Comma-separated inbound API keys |
| `KAAS_GRAPH_ENABLED` | `false` | Enable Data Graph parallel leg (v2) |
| `KAAS_DEFAULT_TOP_K` | `5` | Default chunks per product |
| `KAAS_DEFAULT_MAX_PRODUCTS` | `3` | Default fan-out width cap |
| `KAAS_BASE_URL` | `http://localhost:8000` | MCP server → REST API base URL |
| `KAAS_MCP_API_KEY` | `dev-key-1` | API key used by the MCP server |

---

## Authentication

All REST endpoints (except `/v1/health`) require an `X-API-Key` header. One key per agent in production, managed in secrets manager.

```bash
curl -H "X-API-Key: dev-key-1" http://localhost:8000/v1/health
```

---

## Deployment

Target: **EKS app on Forge ML platform** — [Project 141](https://launchpad.forge-prod.sfdcbt.net/projects/141). Forge EKS is the correct target (always-on custom API service, not SageMaker which is for ML inference endpoints).

CI/CD via ArgoCD + `forge-config.yml`. Custom ML models (future classifier, future reranker) deploy as SageMaker endpoints on the same Forge project.

Auth in production: service-to-service API keys stored in secrets manager. MuleSoft gateway is a thin passthrough (or retired) — new callers call KaaS directly.

---

## Consuming Agents

| Agent | Surface | Notes |
|-------|---------|-------|
| Help Agent | Help portal (customer-facing) | Hosted in OrgCS; same deployment as Slack Agent |
| Slack Agent | Slack (internal/external async) | Same codebase as Help Agent, different channel surface |
| Informatica Agent | TBD | Third-party corpus consumer; onboarding in parallel |
| Future agents | — | Internal teams onboard via API key request |

Help Agent and Slack Agent share the same `agent_id` namespace in OrgCS. Default to a single OrgCS API key unless per-surface SLA tracking is needed.

---

## Observability

| Signal | Format | Sink | Purpose |
|--------|--------|------|---------|
| Distributed traces | OTel spans (OTLP) | New Relic / Splunk | End-to-end request debugging |
| Metrics | OTel metrics (OTLP) | New Relic | Dashboards + alerting |
| Operational logs | Structured JSON | Splunk | Search by `request_id` / `agent_id` |
| Analytics events | Structured JSON | Snowflake | Classifier quality, experiment analysis |
| Experiment exposures | Structured JSON | Snowflake (v2) | GrowthBook join |
| On-call | via New Relic alerts | PagerDuty | Latency p95, error rate, ambiguous rate |

`correlation_id` in the API maps to a W3C `traceparent` header, enabling end-to-end traces across OrgCS → KaaS → C360.

---

## Classifier Evolution

| Phase | Method | Latency | Status |
|-------|--------|---------|--------|
| 1 — MVP | Rule-based (YAML taxonomy) + zero-shot LLM fallback via Einstein LLM Gateway | rules ~1ms, LLM ~400–500ms | **Current** |
| 2 | Feedback collection → labeled dataset (human review queue) | — | Planned |
| 3 | Fine-tuned lightweight classifier (SageMaker endpoint on Forge) | ~20–50ms | Planned |

---

## Phased Roadmap

### MVP — current
REST API on Forge EKS, dummy C360 adapter, rule-based classifier stub, auth, health endpoint, MCP server layer.

### V1.1
MCP server wired to Agentforce/OrgCS native MCP client; LLM fallback classifier via Einstein LLM Gateway; Neo4j/Data Graph parallel leg enabled via feature flag for internal pilot; Informatica Agent onboarded.

### V1.2
GrowthBook experiment assignment; experiment exposure events → Snowflake; graph entitlement pre-scoping live; ambiguity threshold A/B experiment.

### V2
Fine-tuned classifier on SageMaker; optional second-stage reranker; generation mode (opt-in); conversation state management.

---

## TODO

### Retrieval
- [ ] Replace dummy C360 adapter with real `POST /v1/retrievers/{retrieverApiName}/text-retrieval` calls — confirm credential type and access path with Data Cloud team (Risk #1 in design doc)
- [ ] Implement rule-based product classifier from YAML taxonomy (`products.yaml`) — coordinate `c360_filter_value` with ATS tagging team to ensure filter alignment
- [ ] Add zero-shot LLM fallback classifier via Einstein LLM Gateway (Phase 1b); batch intent detection in the same call
- [ ] Add per-product retriever routing via YAML `c360_retriever_name` field (for Informatica corpus)
- [ ] Implement version extraction from query (`"Spring '25"`, `"25.1"`, version slugs) and pass as C360 filter

### Graph (v2)
- [ ] Implement C360 Data Graph adapter — `DG_Tenants_Metrics` (tenant/contract/SKU); validate endpoint, auth schema, and response envelope
- [ ] Wire graph parallel leg in orchestrator (alongside C360 retrieval, budget 500ms, non-blocking)
- [ ] Implement merge logic: graph entitlement conflict → downrank chunks, log `graph_entitlement_conflict: true`
- [ ] Meet graph readiness gate before enabling in production (p95 < 500ms, schema validated, no PII in graph paths)

### Observability
- [ ] Wire OTel instrumentation — spans for `auth`, `query_intelligence`, `parallel_fan_out`, `c360.retrieve[product]`, `packaging`
- [ ] Structured request log → Splunk (ops); analytics events + raw query (PII-scrubbed) → Snowflake
- [ ] New Relic metrics: `kaas.latency_ms`, `kaas.error_rate`, `kaas.c360.error_rate`, `kaas.classifier.ambiguous_rate`, `kaas.classifier.llm_fallback_rate`
- [ ] PagerDuty alert thresholds: p95 > 4s for 5min, error rate > 5% for 2min
- [ ] Feedback event pipeline: write `feedback_submitted` events to label store (Snowflake) with `feedback_token → request_id` linkage

### Deployment
- [ ] Write `forge-config.yml` for EKS app deployment on [Forge Project 141](https://launchpad.forge-prod.sfdcbt.net/projects/141)
- [ ] Set up ArgoCD pipeline
- [ ] Move API keys to secrets manager; provision one key per agent (OrgCS, Informatica)
- [ ] Add `forge-config.yml` SageMaker endpoint config for future classifier model

### Product taxonomy
- [ ] Create `products.yaml` with `exact_keywords`, `fuzzy_patterns`, `negative_keywords`, `c360_filter_value`, `description` per product
- [ ] Validate each `c360_filter_value` end-to-end: known article → C360 retrieval → non-empty results (add to CI smoke tests)
- [ ] Sync with ATS tagging team on product identifier alignment (R16)

### Auth & multi-tenancy
- [ ] Enforce per-agent isolation in retrieval: OrgCS agent must not see Informatica Agent's retrieval context
- [ ] Propagate `correlation_id` as W3C `traceparent` header to C360 and graph downstream calls

### Experiments
- [ ] Implement pluggable experiment flag abstraction (config/env in MVP; GrowthBook interface slot for v2)
- [ ] Tag `experiment_variant` on every request log event from day one
- [ ] Wire GrowthBook SDK on Forge when available (R4)

### Privacy & compliance
- [ ] Confirm PIA process with Legal/Privacy team before MVP launch (A7 in design doc)
- [ ] Implement regex PII scrub (email, phone, SSN) before writing raw query to Snowflake
- [ ] Document Snowflake retention policy and access controls

### Testing
- [ ] Integration smoke test: for each product in taxonomy, assert non-empty chunks returned
- [ ] Contract test: verify C360 adapter request schema matches Data Cloud API spec
- [ ] Load test: p95 < 3–4s at expected OrgCS help portal traffic volume
