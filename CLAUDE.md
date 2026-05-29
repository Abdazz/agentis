# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

Agentis is currently in the **specification/planning phase**. The authoritative reference is `docs/agentis_spec.md` (v2.0.0 — unified technical + functional spec). No code has been written yet.

## What is Agentis?

A self-hosted autonomous AI agent platform. Users submit natural-language goals; the agent decomposes them into sub-tasks, invokes tools (browser, code executor, web search, file system), reflects on results, and delivers structured artifacts — all inside an isolated sandbox (Kata Container micro-VM in production).

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15 (App Router), shadcn/ui, Tailwind CSS, next-intl (EN/FR) |
| Server state | TanStack Query v5 + Zustand |
| API Gateway | FastAPI (Python 3.12), JWT + API key auth |
| Task Queue | Celery + Redis (DB0 — broker) |
| Orchestrator | LangGraph (StateGraph) + LangChain (`BaseChatModel`) |
| LLM Interface | Anthropic (default), OpenAI, Groq, DeepSeek, Ollama — swap via config |
| Database | PostgreSQL 16 + PgBouncer (connection pooling, transaction mode) |
| Migrations | Alembic (`alembic upgrade head` runs as K8s init container) |
| Cache | Redis DB1 (short-term memory, separate from broker) |
| Vector Store | Qdrant (self-hosted) — hybrid dense+sparse search, NOT pgvector |
| Embeddings | Voyage AI `voyage-multilingual-2` (1024-dim, EN+FR) |
| Sandbox | Kata Containers (micro-VM, K3s prod) / hardened Docker (dev) |
| Browser | Playwright — runs **inside sandbox only**, orchestrator uses JSON-RPC client |
| File Storage | MinIO (prod) or local FS (single-node dev) |
| Secrets | HashiCorp Vault (user integration secrets never reach LLM context) |
| Observability | Langfuse (LLM traces), Prometheus, Grafana, Loki + structlog |
| Deployment | Docker Compose (dev), K3s + Helm (prod) |

## Architecture

### Orchestrator Loop (LangGraph StateGraph)

```
START → PLAN → THINK → ACT → OBSERVE → REFLECT → (back to THINK or PLAN)
                     → REPORT → END
```

- `PLAN`: decompose goal into ordered sub-tasks (JSON Plan)
- `THINK`: LLM selects next tool or decides goal is met (`.bind_tools()`)
- `ACT`: LangGraph `ToolNode` dispatches to Tool Registry RPC client
- `OBSERVE`: normalize tool output, update scratchpad
- `REFLECT`: update plan, compute confidence score, decide continue/HITL/report
- `REPORT`: summarize result, list artifacts, emit `task_completed` SSE event

State persisted at every step via `PostgresSaver(pgbouncer_pool)`. Any worker can resume any task from the last checkpoint.

### Tool Architecture

Tools in the Tool Registry are **RPC clients only**. All actual execution (Playwright, Python, Bash, file I/O) happens inside the Kata Container sandbox. Communication is JSON-RPC 2.0 over Unix socket (dev) or TCP+mTLS (prod) on sandbox port 9999.

Secrets for tool execution (email API keys, calendar credentials) are fetched from Vault at call time — never stored in `AgentState` or `task_steps`.

### Memory Layers

| Layer | Storage | TTL | Scope |
|-------|---------|-----|-------|
| Working | LangGraph `AgentState` (in-process, checkpointed) | Session | Plan, tool history, scratchpad |
| Short-term | Redis DB1 | 24h | Recent task summaries, user preferences |
| Long-term | Qdrant (vectors) + PostgreSQL (refs) | Permanent | Semantic user knowledge base |
| Episodic | PostgreSQL `task_steps` | Permanent | Full trace for replay and audit |

Context window managed proactively: at 80% of model budget, oldest messages are summarized by the LLM and replaced with a `SystemMessage` summary.

### Sandbox

Each agent session gets a dedicated Kata Container (micro-VM):
- CPU: 2 cores, RAM: 2 GB, Disk: 5 GB, Timeout: 30 min
- Root FS read-only; only `/workspace` writable
- Egress via Squid proxy with domain allowlist (per-session ACLs via Redis)
- Pre-installed: Python 3.12, Node.js 22, Playwright, Docling, LibreOffice, pandoc, ffmpeg

### Frontend Routes

| Route | Purpose |
|-------|---------|
| `/` | New task submission |
| `/login`, `/register` | Auth |
| `/tasks` | Task history (filtered, cursor-paginated) |
| `/tasks/[id]` | Live task trace (SSE) + HITL chat (WebSocket) |
| `/settings` | Language, API keys, token usage, memory |
| `/admin` | Usage metrics, tool management, LLM config |
| `/admin/users` | User management |
| `/admin/audit` | Audit log viewer |

Real-time: **SSE** (`GET /tasks/{id}/stream`, supports `Last-Event-ID` reconnect) for live trace; **WebSocket** (`WSS /ws/tasks/{id}`) for HITL responses.

## Key Architectural Decisions

- **Kata Containers** (not Docker): hardware VM isolation per session; no privileged pods in K3s.
- **Playwright in sandbox only**: orchestrator is a pure RPC client — zero direct browser access.
- **PgBouncer** (transaction mode): required for LangGraph `PostgresSaver` at scale.
- **Redis DB0/DB1 separation**: DB0 for Celery broker, DB1 for memory cache — independent tuning.
- **Qdrant over pgvector**: purpose-built vector DB, native hybrid search, rich payload filtering.
- **System prompts in English only**: LLMs reason better in English; user language injected as a final instruction (`LANGUAGE_INSTRUCTION` dict, see spec §11.2).
- **`BaseChatModel` abstraction**: LLM provider is config-only (`AGENTIS_LLM_PROVIDER`), no code change needed to switch.
- **Voyage AI API first**: self-hosted endpoint added in Phase 3 for data-residency customers (same SDK, change `base_url`).

## RBAC Roles

`user` → `admin` → `operator` (each level adds capabilities; see spec §3.2 Feature AUTH-3).

## Key Environment Variables

```env
# LLM
AGENTIS_LLM_PROVIDER=anthropic                  # anthropic|openai|mistral|groq|deepseek|ollama
AGENTIS_LLM_MODEL=claude-sonnet-4-5-20251022
AGENTIS_LLM_API_KEY=<secret>

# Database (via PgBouncer)
AGENTIS_DATABASE_URL=postgresql://agentis:pass@pgbouncer:5432/agentis
AGENTIS_POSTGRES_DIRECT_URL=postgresql://agentis:pass@postgres:5432/agentis  # Alembic only

# Redis (two separate DBs)
AGENTIS_REDIS_BROKER_URL=redis://redis:6379/0   # Celery
AGENTIS_REDIS_CACHE_URL=redis://redis:6379/1    # Memory cache

# Storage & sandbox
AGENTIS_STORAGE_BACKEND=local                   # local|minio
AGENTIS_SANDBOX_RUNTIME=kata                    # kata|gvisor|docker
AGENTIS_SANDBOX_MAX_CONCURRENT=10
AGENTIS_SANDBOX_TIMEOUT_SECONDS=1800
AGENTIS_DEFAULT_LANGUAGE=fr

# Observability
AGENTIS_LANGFUSE_HOST=http://langfuse:3000
```

Full configuration reference: see spec §19.

## Development Roadmap

- **Phase 1** (Months 1–3): Orchestrator ReAct loop, 4 core tools (browser/code/search/fs), Kata sandbox, Next.js UI + SSE, PostgreSQL + PgBouncer + Alembic, JWT + API key auth, Docker Compose, EN/FR, Langfuse, context window management, token budgets
- **Phase 2** (Months 4–5): doc_parser, http_caller, Qdrant long-term memory, HITL WebSocket, K3s Helm, audit log, admin dashboard, Prometheus/Grafana, Organization model, webhook notifications, MinIO presigned URLs
- **Phase 3** (Months 6–9): MCP auto-discovery, email/calendar tools, OpenAPI tool generator, per-org LLM override, Voyage AI self-hosted, ClamAV file scanning
- **Phase 4** (v2): multi-agent collaboration, voice, fine-tuned OSS LLM, agent marketplace
