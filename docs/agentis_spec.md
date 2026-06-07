# Agentis — Unified Technical & Functional Specification

**Version:** 2.0.0
**Date:** 2026-05-29
**Status:** Approved for Implementation
**Supersedes:** `docs/manus_clone_technical_specs.md` (v1.0.0)
**Prepared for:** YULCOM Technologies
**Language:** English

> **What changed from v1.0:** This document corrects 40 inconsistencies and gaps identified in the original spec. It integrates functional requirements (epics, features, business rules, acceptance criteria) with all architectural and technology decisions into a single authoritative reference.

---

## Table of Contents

1. [Project Vision & Scope](#1-project-vision--scope)
2. [System Architecture](#2-system-architecture)
3. [Epic 1 — Authentication & Authorization](#3-epic-1--authentication--authorization)
4. [Epic 2 — Task Management](#4-epic-2--task-management)
5. [Epic 3 — Agent Orchestration](#5-epic-3--agent-orchestration)
6. [Epic 4 — Tool Registry & Execution](#6-epic-4--tool-registry--execution)
7. [Epic 5 — Sandbox Environment](#7-epic-5--sandbox-environment)
8. [Epic 6 — Memory System](#8-epic-6--memory-system)
9. [Epic 7 — Frontend & Real-Time Streaming](#9-epic-7--frontend--real-time-streaming)
10. [Epic 8 — API Gateway](#10-epic-8--api-gateway)
11. [Epic 9 — Multilinguality](#11-epic-9--multilinguality)
12. [Epic 10 — Admin & Observability](#12-epic-10--admin--observability)
13. [Epic 11 — Multi-Agent Collaboration (Phase 4)](#13-epic-11--multi-agent-collaboration-phase-4)
14. [Data Model](#14-data-model)
15. [API Reference](#15-api-reference)
16. [Security Model](#16-security-model)
17. [Infrastructure & Deployment](#17-infrastructure--deployment)
18. [Technology Stack](#18-technology-stack)
19. [Configuration Reference](#19-configuration-reference)
20. [Development Roadmap](#20-development-roadmap)

---

## 1. Project Vision & Scope

### 1.1 What is Agentis?

Agentis is a **self-hosted, open-source autonomous AI agent platform**. Users submit natural-language goals; the agent decomposes them into sub-tasks, invokes tools (web browsing, code execution, file management, API calls), reasons over intermediate results, adapts its plan, and delivers structured artifacts — all inside an isolated, ephemeral Docker sandbox.

Agentis is not a chatbot. It operates in a **task-completion loop**: Plan → Think → Act → Observe → Reflect → Report. The user submits a goal and receives a completed result; they may optionally monitor progress or intervene.

### 1.2 Positioning

| Dimension | Agentis |
|-----------|---------|
| Deployment | Self-hosted (on-premise or private cloud) |
| Languages | English + French (extensible) |
| LLM Backend | Pluggable (Claude, OpenAI, Mistral, Groq, DeepSeek, Ollama) |
| Execution | Kata Containers per session (hardware-isolated micro-VMs) |
| Target users | Teams, enterprises, research institutions |
| License | MIT (open-source core) + commercial add-ons |

### 1.3 Goals

- Users submit a natural-language goal and the agent autonomously completes it.
- Support long-horizon tasks spanning multiple tool invocations, retries, and plan revisions (up to 30 iterations by default).
- Deliver a bilingual (EN/FR) web interface with real-time task streaming.
- Allow operators to restrict, audit, and observe every action the agent takes.
- On-premise deployment with no dependency on external cloud providers.
- Expose an open API for programmatic task submission.

### 1.4 Non-Goals (v1.0)

- Multi-agent collaboration (Phase 4).
- Mobile-native applications (responsive web only in v1).
- Real-time voice interface.
- Built-in LLM hosting (relies on existing inference endpoints).

### 1.5 Glossary

| Term | Definition |
|------|------------|
| Task | A user-submitted goal that the agent attempts to complete. |
| Step | One node execution in the agent loop (think, act, observe, reflect). |
| Artifact | A file produced by the agent during a task (PDF, CSV, image, etc.). |
| Sandbox | An isolated Kata Container per session where tools execute. |
| HITL | Human-in-the-Loop: a point where the agent pauses for user input. |
| Tool | A discrete capability the agent can invoke (browser, code executor, etc.). |
| Checkpoint | A persisted snapshot of the agent's state at a given step. |
| Organization | A group of users sharing LLM config, tool policies, and billing (Phase 2). |

---

## 2. System Architecture

### 2.1 High-Level Diagram

```
+------------------------------------------------------------------+
|                        USER INTERFACE                            |
|         (Next.js 15 App Router + shadcn/ui, EN/FR)              |
+-----------------------------+------------------------------------+
                              | REST + SSE + WebSocket
+-----------------------------v------------------------------------+
|                         API GATEWAY                              |
|           (FastAPI, JWT/API-Key auth, rate limiting)             |
+-------+-------------------+-------------------+------------------+
        |                   |                   |
+-------v------+  +---------v------+  +---------v---------+
| ORCHESTRATOR |  | MEMORY SERVICE |  |  TASK MANAGER     |
| (LangGraph)  |  | (Qdrant+Redis) |  |  (Celery + Redis) |
|              |  |                |  |                   |
| Plan>Think   |  | short-term:    |  | task_id routing   |
| >Act>Observe |  |   Redis DB 1   |  | retry, scheduling |
| >Reflect     |  | long-term:     |  | PgBouncer pool    |
|              |  |   Qdrant       |  |                   |
| PostgresSaver|  | episodic:      |  |                   |
| (checkpoints)|  |   PostgreSQL   |  |                   |
+-----------+--+  +----------------+  +-------------------+
            |
+-----------v-------------------------------------------------+
|                     TOOL REGISTRY                            |
|  (Tool Router — selects sandbox RPC target per tool call)   |
|  +----------+ +----------+ +----------+ +---------------+   |
|  | Browser  | |  Code    | | File Sys | |  HTTP Caller  |   |
|  | RPC      | | Executor | | Tool     | |  Tool         |   |
|  | Client   | | RPC      | | RPC      | |  RPC Client   |   |
|  +----+-----+ +----+-----+ +----+-----+ +-------+-------+   |
+-------|------------|------------|----------------|------------+
        |            |            |                |
        | (JSON-RPC over Unix socket or TCP)        |
+-------v------------v------------v----------------v------------+
|          SANDBOX (Kata Container, per-session micro-VM)        |
|  - Playwright (Chromium headless)                              |
|  - Python 3.12 runtime                                         |
|  - Node.js 22                                                  |
|  - File system (/workspace, ephemeral)                         |
|  - Outbound via Squid egress proxy                             |
+----------------------------------------------------------------+
        |
+-------v-----------------------------------------+
|            OBSERVABILITY STACK                  |
|  Langfuse (LLM traces)                          |
|  Prometheus + Grafana (metrics + dashboards)    |
|  Loki (structured logs via structlog)           |
+-------------------------------------------------+
```

### 2.2 Key Architectural Decisions

#### ADR-01 — LangGraph State vs Celery Workers

**Problem:** LangGraph's working memory is in-process; Celery distributes tasks across N workers. If a task is enqueued on worker #2 and later resumes on worker #4, state is lost.

**Decision:** Each Celery worker runs the full agent loop synchronously via `graph.astream()`. Celery transports only the `task_id` (not agent state). State is persisted at every step via `PostgresSaver(conn)` (LangGraph's built-in checkpointer backed by PostgreSQL). Any worker can resume any task by loading the checkpoint. PgBouncer provides connection pooling to prevent PostgreSQL exhaustion.

```
Celery queue  →  worker picks up task_id
                  worker calls graph.astream(input, config={"thread_id": task_id})
                  each step: PostgresSaver writes state to DB
                  on restart: state loaded from last checkpoint
```

**Consequence:** Tasks are blocking per-worker. Size the worker pool (AGENTIS_WORKER_CONCURRENCY) to match expected concurrent agent sessions.

#### ADR-02 — Where Playwright Runs

**Problem:** The original spec listed Playwright both as a `BrowserTool` in the orchestrator and as pre-installed in the sandbox, creating ambiguity about execution location — a critical security decision.

**Decision:** Playwright runs **exclusively inside the Kata Container sandbox**. The `BrowserTool` in the Tool Registry is an RPC client only. It serializes a command, sends it over a Unix socket (or loopback TCP) to the Playwright server process running inside the sandbox, and deserializes the response. The orchestrator process has zero direct browser access.

**Consequence:** All DOM interaction, screenshot capture, and cookie handling occur in the isolated sandbox. Malicious page content cannot escape to the orchestrator.

#### ADR-03 — Sandbox Runtime: Kata Containers

**Problem:** The original spec suggested "Docker-in-Docker or socket proxy" without deciding. DinD in K3s requires privileged pods, which nullifies sandbox isolation guarantees.

**Decision:** Use **Kata Containers** (hardware VM isolation via QEMU/KVM) as the sandbox runtime on K3s. Each agent session gets a dedicated micro-VM with an independent kernel. On hosts without VT-x support (CI, some cloud VMs), fall back to **gVisor (runsc)** as the RuntimeClass.

Development (Docker Compose): use regular Docker containers with `--security-opt no-new-privileges --read-only --cap-drop ALL`, network namespace isolation, and a dedicated bridge network per session.

#### ADR-04 — Celery Only (No Prefect)

**Problem:** The original spec mentioned "Celery/Prefect" without deciding.

**Decision:** Celery + Redis exclusively. Prefect adds valuable workflow observability but doubles operational overhead. LLM observability is provided by Langfuse; application metrics by Prometheus. Prefect is deferred to Phase 4 if multi-agent orchestration requires complex workflow graphs.

#### ADR-05 — Redis: Separate Databases Per Role

**Problem:** The original spec used a single Redis instance for both Celery message broker and short-term memory cache, creating contention and independent scaling issues.

**Decision:**
- `Redis DB 0` — Celery broker and result backend.
- `Redis DB 1` — Short-term memory (task summaries, user preferences, 24h TTL).

Both can run on the same Redis instance in development. In production, provision two logical Redis databases or two separate Redis instances.

#### ADR-06 — Voyage AI: API First, Self-Hosted in Phase 3

**Decision:** Use Voyage AI API (`voyage-multilingual-2`) in Phases 1 and 2. No operational overhead, identical SDK interface. For Phase 3 customers with data residency requirements, deploy the Voyage AI self-hosted endpoint (same `VoyageAIEmbeddings` class, change `base_url`). No code change required.

#### ADR-07 — Organization Model Deferred to Phase 2

Multi-tenancy (Organizations with shared config, billing, and tool policies) is architecturally included in the data model from Phase 1 (the `organizations` and `organization_memberships` tables are created) but the product-facing features (org management UI, org-level LLM config, shared task history) are implemented in Phase 2.

---

## 3. Epic 1 — Authentication & Authorization

### 3.1 Overview

Agentis supports three authentication mechanisms: email/password for interactive users, JWT bearer tokens for web sessions, and API keys for programmatic access. Role-based access control (RBAC) governs what authenticated principals can do.

### 3.2 Features

#### Feature AUTH-1: Email/Password Registration & Login

**Description:** Users create accounts with email and password. Passwords are hashed with bcrypt (cost factor 12). On login, the server issues an access token (JWT, 1 hour TTL) and a refresh token (opaque, 30 days TTL).

**Business Rules:**
- BR-AUTH-01: Email must be unique across the platform. Case-insensitive comparison.
- BR-AUTH-02: Password minimum 12 characters, must contain at least one uppercase, one digit.
- BR-AUTH-03: Failed login attempts are rate-limited: 5 attempts per email per 15 minutes, then 429 with `Retry-After` header.
- BR-AUTH-04: Access token is a signed JWT (RS256). Payload: `sub` (user_id), `org_id`, `role`, `iat`, `exp`.
- BR-AUTH-05: Refresh token is an opaque 32-byte random token stored as SHA-256 hash in `refresh_tokens` table.
- BR-AUTH-06: Each refresh token is single-use. On use, the old token is revoked and a new pair (access + refresh) is issued. This is **refresh token rotation**.
- BR-AUTH-07: If a refresh token is used after revocation (replay attack), all sessions for that user are immediately invalidated.

**Token Transport:**
- Access token: stored in JavaScript memory (not localStorage, not cookies). Sent as `Authorization: Bearer <token>` header on every API request.
- Refresh token: stored in `httpOnly`, `SameSite=Strict`, `Secure` cookie. Never accessible to JavaScript.

**Acceptance Criteria:**
- AC-AUTH-01: A user can register with a valid email and password and immediately log in.
- AC-AUTH-02: An expired access token results in a 401 response; the frontend transparently calls `/auth/refresh` and retries.
- AC-AUTH-03: A replayed refresh token immediately locks the user's account (all sessions destroyed).
- AC-AUTH-04: Logout revokes the current refresh token and clears the cookie.

**Edge Cases:**
- EC-AUTH-01: User registers with an email that has a pending verification → email verification resent, existing unverified account updated.
- EC-AUTH-02: Refresh token in cookie is missing (cleared browser data) → 401, user redirected to login.

#### Feature AUTH-2: API Key Authentication

**Description:** Users generate API keys for programmatic access (CI/CD pipelines, integrations). API keys are long-lived but revocable.

**Business Rules:**
- BR-AUTH-10: API keys are formatted as `agentis_sk_<random_32_bytes_base62>`. The prefix distinguishes them from JWTs at the gateway level.
- BR-AUTH-11: Only the SHA-256 hash of the key is stored. The plaintext key is shown once at creation and never again.
- BR-AUTH-12: API keys are sent via `X-API-Key` header (NOT `Authorization: Bearer`). The gateway checks this header first; if absent, it checks `Authorization: Bearer` for JWT.
- BR-AUTH-13: API keys carry the permissions of the user who created them, scoped to the role at time of creation (not dynamically updated).
- BR-AUTH-14: A key can be labeled, and its `last_used_at` is updated on each use (debounced: max once per minute to avoid write amplification).
- BR-AUTH-15: A user can create a maximum of 10 active API keys.
- BR-AUTH-16: API keys expire after 365 days unless `expires_at` is set explicitly at creation.

**Acceptance Criteria:**
- AC-AUTH-10: A user creates an API key, the plaintext is shown once in the UI.
- AC-AUTH-11: An API call with the valid key succeeds; with a revoked key, returns 401.
- AC-AUTH-12: `last_used_at` is updated within 1 minute of key use.

#### Feature AUTH-3: RBAC

**Description:** Three roles control what authenticated principals can do.

| Role | Capabilities |
|------|-------------|
| `user` | Submit tasks, view own tasks/history/memory, manage own API keys, manage own settings |
| `admin` | All `user` capabilities + view all users, query audit log, view all tasks |
| `operator` | All `admin` capabilities + manage LLM provider config, enable/disable tools, set rate limits, manage organizations |

**Business Rules:**
- BR-AUTH-20: Role is stored on the JWT payload and checked on every endpoint. Database role is the source of truth; JWT role may be stale (refresh required after role change).
- BR-AUTH-21: An `admin` cannot elevate their own role to `operator`.
- BR-AUTH-22: Role changes take effect at the next token refresh.

#### Feature AUTH-4: OIDC/SSO (Phase 2)

**Description:** Enterprise SSO via OIDC (Google Workspace, Azure AD, Okta). When OIDC is configured for an organization, password login is disabled for members of that organization.

**Business Rules:**
- BR-AUTH-30: OIDC configuration is per-organization, managed by `operator` role.
- BR-AUTH-31: OIDC users are auto-provisioned on first login with `user` role.
- BR-AUTH-32: OIDC users cannot create API keys until their account is confirmed by an `admin`.

---

## 4. Epic 2 — Task Management

### 4.1 Overview

A Task represents a user goal submitted to the agent. Tasks have a lifecycle from submission through completion, and produce artifacts as outputs. This epic covers the full lifecycle, including cancellation, file inputs, and artifact management.

### 4.2 Task Lifecycle

```
SUBMITTED → PLANNING → RUNNING → COMPLETED
                              → FAILED
                              → CANCELLED
          ↕ (at any RUNNING step)
          WAITING_FOR_INPUT → RUNNING (on user response)
          WAITING_FOR_INPUT → CANCELLED (on timeout)
```

**State transition rules:**
- `SUBMITTED → PLANNING`: immediately after Celery worker picks up the task.
- `PLANNING → RUNNING`: after the agent completes the initial plan.
- `RUNNING → WAITING_FOR_INPUT`: when the agent emits a `user_input_required` event.
- `WAITING_FOR_INPUT → CANCELLED`: after `AGENTIS_HITL_TIMEOUT_SECONDS` (default: 3600) without user response.
- Any state → `CANCELLED`: on explicit user cancellation (DELETE /tasks/{id}).
- `RUNNING → FAILED`: on unrecoverable error or max iteration limit reached.

### 4.3 Features

#### Feature TASK-1: Task Submission

**Description:** A user submits a natural-language goal. The system validates the input, enqueues the task, and returns a task ID and stream URL immediately. Task execution is fully asynchronous.

**Business Rules:**
- BR-TASK-01: `goal` field is required. Max 10,000 characters.
- BR-TASK-02: `language` defaults to the user's account language setting if not specified.
- BR-TASK-03: `max_iterations` defaults to 30; operator can set a platform-wide maximum (default: 50). User-requested values above the platform maximum are clamped silently.
- BR-TASK-04: `allowed_tools` defaults to all tools enabled for the user's organization. If specified, it must be a subset of organization-allowed tools.
- BR-TASK-05: File inputs (`input_files`) are uploaded as multipart and stored before task enqueue. Files must be ≤ 50 MB each, max 5 files per task. Supported types: PDF, DOCX, XLSX, PPTX, CSV, TXT, PNG, JPG, MP3, MP4.
- BR-TASK-06: A task is enqueued to Celery immediately after validation. The response is returned to the caller before the agent starts.
- BR-TASK-07: A user can have a maximum of 5 concurrently `RUNNING` tasks (configurable per org by operator).
- BR-TASK-08: Task `goal` is stored as-is (no sanitization) but never executed as code; it is only passed to the LLM as a prompt string.

**Acceptance Criteria:**
- AC-TASK-01: Task is created and visible in task history within 500ms of POST /tasks.
- AC-TASK-02: SSE stream URL is returned in the response and starts emitting events within 5 seconds.
- AC-TASK-03: File inputs are accessible to the agent in the sandbox at `/workspace/inputs/`.
- AC-TASK-04: Submitting a task when at the concurrency limit returns 429 with a clear error message.

#### Feature TASK-2: Task Monitoring

**Description:** The task view shows the live execution trace: each think/act/observe/reflect step streamed in real time via SSE.

**Business Rules:**
- BR-TASK-10: The SSE stream emits events as defined in Section 9 (Frontend). Events include `plan_created`, `think`, `tool_call`, `tool_result`, `plan_updated`, `user_input_required`, `task_completed`, `task_failed`.
- BR-TASK-11: The stream uses `Last-Event-ID` semantics. If a client reconnects, the server replays all events since the provided `Last-Event-ID` from the `task_steps` table (episodic memory).
- BR-TASK-12: A completed task's full trace is always available via `GET /tasks/{id}/stream?replay=true`, regardless of whether the original SSE session is still active.

**Acceptance Criteria:**
- AC-TASK-10: Disconnecting and reconnecting to the SSE stream replays all missed events.
- AC-TASK-11: The plan sidebar updates in real time as sub-tasks are completed.

#### Feature TASK-3: Task Cancellation

**Description:** A user cancels a running task. The system must gracefully stop the agent and clean up resources.

**Business Rules:**
- BR-TASK-20: A task can be cancelled from any state except `COMPLETED` and `FAILED`.
- BR-TASK-21: Cancellation sequence (ordered):
  1. Task status set to `CANCELLED` in DB (atomic update with optimistic lock).
  2. Celery task is revoked via `celery.control.revoke(task_id, terminate=True)`.
  3. The sandbox container for the session is stopped (`docker stop --time=10`).
  4. Any artifacts already produced are retained and remain downloadable.
  5. A `task_failed` SSE event with `reason: "cancelled"` is emitted to connected clients.
- BR-TASK-22: If the sandbox container cannot be stopped within 15 seconds, it is forcefully killed (`docker kill`) and the error is logged.
- BR-TASK-23: Cancellation is idempotent: cancelling an already-cancelled task returns 200 with the current state.

**Acceptance Criteria:**
- AC-TASK-20: After cancellation, no new tool calls are initiated.
- AC-TASK-21: Sandbox container is fully stopped within 20 seconds of cancellation request.
- AC-TASK-22: Artifacts produced before cancellation are still downloadable.

#### Feature TASK-4: Task History & Filtering

**Description:** Users view their task history with filtering and pagination.

**Business Rules:**
- BR-TASK-30: `GET /tasks` supports cursor-based pagination (`after` cursor, `limit` 1–100, default 20).
- BR-TASK-31: Filter parameters: `status` (one or more), `language`, `created_after` (ISO8601), `created_before` (ISO8601), `search` (full-text search on `goal` field).
- BR-TASK-32: Default sort: `created_at DESC`.
- BR-TASK-33: A `user` role sees only their own tasks. An `admin` can query all tasks with an additional `user_id` filter.
- BR-TASK-34: Soft-deleted tasks (`deleted_at IS NOT NULL`) are excluded from all list results unless `include_deleted=true` is passed (admin only).

**Acceptance Criteria:**
- AC-TASK-30: A user with 1000 tasks can paginate through all of them with consistent ordering.
- AC-TASK-31: `search` filter performs full-text search and returns results within 200ms for up to 100,000 tasks.

#### Feature TASK-5: Artifact Management

**Description:** The agent produces files (PDFs, CSVs, images) stored in MinIO (or local FS). Users can list, preview, and download artifacts.

**Business Rules:**
- BR-TASK-40: Artifacts are stored with a `storage_key` formatted as `{backend}://{bucket_or_path}/{task_id}/{filename}`. Example: `minio://agentis-artifacts/f47ac10b.../report.pdf` or `local:///var/agentis/files/f47ac10b.../report.pdf`. This prefix disambiguates storage backend.
- BR-TASK-41: Artifact retention is 90 days by default (configurable: `AGENTIS_ARTIFACT_RETENTION_DAYS`). A Celery beat job runs daily and deletes artifacts older than the retention period.
- BR-TASK-42: When a task is soft-deleted by the user, its artifacts are NOT immediately deleted. They are garbage-collected when the retention period expires.
- BR-TASK-43: When a task is hard-deleted (admin or retention cleanup), artifacts are deleted from storage before the DB record is removed.
- BR-TASK-44: Artifact download URLs are **signed URLs** with a 1-hour expiry (MinIO presigned URL or a time-limited HMAC-signed local route). Direct storage paths are never exposed.
- BR-TASK-45: Max total artifact size per task: 2 GB. The sandbox enforces this via disk quota.

**Acceptance Criteria:**
- AC-TASK-40: A user can download an artifact produced by a completed task.
- AC-TASK-41: After 90 days (or configured retention), artifacts are no longer downloadable.
- AC-TASK-42: Artifact download URL expires after 1 hour; re-requesting the download endpoint issues a new signed URL.

#### Feature TASK-6: Human-in-the-Loop (HITL)

**Description:** The agent pauses mid-execution and requests user input. The user responds via the chat interface. Execution resumes immediately.

**Business Rules:**
- BR-TASK-50: HITL is triggered when: (a) the agent is about to perform a destructive action (email send, file delete, external POST), (b) operator policy requires confirmation for a specific tool, (c) the agent's confidence score (from the reflect step) is below `AGENTIS_HITL_CONFIDENCE_THRESHOLD` (default: 0.3).
- BR-TASK-51: The HITL event is delivered via WebSocket to the connected frontend. The task transitions to `WAITING_FOR_INPUT`.
- BR-TASK-52: The user's response is submitted via `POST /tasks/{id}/input`. The response is validated against `options` if provided (free text otherwise).
- BR-TASK-53: HITL timeout: if no response after `AGENTIS_HITL_TIMEOUT_SECONDS` (default: 3600), the task is cancelled with reason `hitl_timeout`.
- BR-TASK-54: If no WebSocket client is connected when a HITL event fires, the event is buffered for 10 minutes. After 10 minutes with no client, the task is cancelled.
- BR-TASK-55: Destructive action definition: any tool call that modifies external state outside the sandbox (email.send, calendar.create_event, http_caller with non-GET methods to non-whitelisted domains).

**Acceptance Criteria:**
- AC-TASK-50: When HITL fires, the UI shows the agent's question and any provided options.
- AC-TASK-51: Submitting a response resumes task execution within 2 seconds.
- AC-TASK-52: A task in `WAITING_FOR_INPUT` for 1 hour is automatically cancelled.

---

## 5. Epic 3 — Agent Orchestration

### 5.1 Overview

The Orchestrator is the agent's brain, implemented as a LangGraph `StateGraph`. It implements a ReAct-style loop (Plan → Think → Act → Observe → Reflect) with explicit planning, tool execution, and reflection steps. This epic covers the loop logic, LLM provider management, context window management, and error handling.

### 5.2 Agent Loop (LangGraph StateGraph)

```
START → [PLAN] → [THINK] → [ACT] → [OBSERVE] → [REFLECT] → back to [THINK] or [PLAN]
                         → [REPORT] → END
```

**Node responsibilities:**

| Node | Responsibility |
|------|---------------|
| PLAN | Decompose goal into ordered sub-tasks. Produce a structured `Plan` JSON. |
| THINK | Given current plan + memory, select next action (tool call) or decide goal is met. |
| ACT | Invoke selected tool via Tool Registry RPC. Handled by LangGraph `ToolNode`. |
| OBSERVE | Normalize tool output. Extract key facts. Update scratchpad. |
| REFLECT | Assess progress. Update plan (mark sub-tasks done, add new ones). Decide: continue, request HITL, or report. Compute confidence score. |
| REPORT | Summarize task result. List artifacts. Emit `task_completed` event. |

**LangGraph graph definition (reference implementation):**

```python
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.postgres import PostgresSaver

graph = StateGraph(AgentState)
graph.add_node("plan",    plan_node)
graph.add_node("think",   think_node)
graph.add_node("act",     ToolNode(tools))
graph.add_node("observe", observe_node)
graph.add_node("reflect", reflect_node)
graph.add_node("report",  report_node)

graph.set_entry_point("plan")
graph.add_edge("plan",    "think")
graph.add_conditional_edges("think",   route_after_think)   # → act | report
graph.add_edge("act",     "observe")
graph.add_edge("observe", "reflect")
graph.add_conditional_edges("reflect", route_after_reflect) # → think | plan | report

agent = graph.compile(checkpointer=PostgresSaver(pool))  # pool = PgBouncer connection pool
```

### 5.3 AgentState Schema

```python
class AgentState(TypedDict):
    task_id:         str
    user_id:         str
    goal:            str
    language:        str                # "en" | "fr"
    plan:            Plan
    messages:        list[BaseMessage]  # LangChain message history
    scratchpad:      str                # Accumulated observations
    iteration:       int                # Current loop count
    max_iterations:  int
    confidence:      float              # Set by reflect node (0.0 - 1.0)
    allowed_tools:   list[str]
    artifacts:       list[Artifact]
    hitl_pending:    bool
    hitl_response:   str | None
```

### 5.4 Features

#### Feature ORCH-1: LLM Provider Management

**Description:** The orchestrator uses LangChain's `BaseChatModel` as its unified LLM interface. The provider is configured at startup and can be changed via environment variables without code changes.

**Business Rules:**
- BR-ORCH-01: The active LLM provider is determined by `AGENTIS_LLM_PROVIDER`. Supported values: `anthropic`, `openai`, `mistral`, `groq`, `deepseek`, `ollama`.
- BR-ORCH-02: All nodes call the LLM via `llm.bind_tools(tools).invoke(messages)`. No provider-specific code outside `build_llm()`.
- BR-ORCH-03: LLM calls are wrapped in a circuit breaker (3 failures in 60 seconds → open, 30-second cooldown). On open circuit, the task transitions to `FAILED` with `error_code: "llm_unavailable"`.
- BR-ORCH-04: LLM call timeout: 120 seconds per call. On timeout, retried once. On second timeout, circuit breaker increments failure count.
- BR-ORCH-05: An operator can configure a per-organization LLM provider override (Phase 2), allowing some orgs to use Groq for speed and others to use Claude for quality.

**Acceptance Criteria:**
- AC-ORCH-01: Changing `AGENTIS_LLM_PROVIDER` in env and restarting workers switches the active provider.
- AC-ORCH-02: When the LLM is unavailable for 3 consecutive calls, the task fails gracefully with a user-visible error message.

#### Feature ORCH-2: Context Window Management

**Description:** For long tasks (30 iterations), the accumulated message history, memory context, and tool outputs may exceed the LLM's context window. The system must manage this proactively.

**Business Rules:**
- BR-ORCH-10: The system tracks token count per step via LangChain's token counting utilities.
- BR-ORCH-11: Before each THINK call, the system computes `total_tokens = system_prompt_tokens + memory_tokens + messages_tokens + scratchpad_tokens`.
- BR-ORCH-12: If `total_tokens > AGENTIS_CONTEXT_BUDGET` (default: 80% of model context window), the messages history is **summarized**: the oldest 50% of messages are replaced with a single `SystemMessage` containing an LLM-generated summary. The original messages are preserved in the `task_steps` table for replay.
- BR-ORCH-13: Memory injection budget: at most `AGENTIS_MEMORY_INJECTION_TOKENS` (default: 2000 tokens) from long-term memory per THINK call. Fewer memories are injected if the budget is tight.
- BR-ORCH-14: Tool outputs are truncated to `AGENTIS_TOOL_OUTPUT_MAX_TOKENS` (default: 8000 tokens) before being added to messages. Truncated outputs include a note: `[OUTPUT TRUNCATED — {N} characters removed. Full output available in task_steps.]`.
- BR-ORCH-15: Context window sizes by provider: Claude (200k), GPT-4o (128k), Groq Llama3 (128k), DeepSeek (64k). The budget percentage in BR-ORCH-12 applies to the active model's window.

**Acceptance Criteria:**
- AC-ORCH-10: A 30-iteration task on a 64k-context model completes without a context length error.
- AC-ORCH-11: The summarization event is logged as a `task_step` of type `context_summarized`.

#### Feature ORCH-3: Token Budget & Cost Control

**Description:** The platform enforces token budgets to prevent runaway costs.

**Business Rules:**
- BR-ORCH-20: Token budget levels: per-task, per-user/month, per-org/month. All three are checked before each LLM call.
- BR-ORCH-21: Default budgets (configurable by operator): per-task 100,000 tokens; per-user/month 2,000,000 tokens; per-org/month configurable (no default).
- BR-ORCH-22: When a budget would be exceeded by the next LLM call (estimated using BR-ORCH-11), the task is halted gracefully: the reflect node is invoked one final time with the instruction "produce a partial report", then the task completes with status `COMPLETED` and a `partial: true` flag.
- BR-ORCH-23: Monthly usage resets at midnight UTC on the 1st of each month. A Celery beat job handles the reset.
- BR-ORCH-24: Users can view their token usage in `/settings`. Operators can view org usage in `/admin`.

#### Feature ORCH-4: Retry Strategy

**Description:** Transient errors in tool calls or LLM calls are automatically retried with exponential backoff.

**Business Rules:**
- BR-ORCH-30: Tool call errors are classified as `transient` (network timeout, HTTP 429, HTTP 5xx) or `permanent` (invalid params, HTTP 400, HTTP 404).
- BR-ORCH-31: Transient errors: retry up to 3 times with exponential backoff (1s, 4s, 16s). After 3 failures, the reflect node is informed via an `error` observation and decides whether to try an alternative approach.
- BR-ORCH-32: Permanent errors: no retry. The reflect node is immediately informed and must adapt the plan.
- BR-ORCH-33: The retry count is tracked in `AgentState` per tool call. The reflect node can see retry history.
- BR-ORCH-34: Max total failures per task: 10. After 10 failures (regardless of tool), the task transitions to `FAILED`.

#### Feature ORCH-5: Graceful Shutdown

**Description:** When a Celery worker is stopped (K8s rolling update, SIGTERM), running agent loops must be interrupted gracefully without losing state.

**Business Rules:**
- BR-ORCH-40: Workers listen for SIGTERM. On receiving it, they call `celery.worker.consumer.Consumer.stop_consuming()` to stop accepting new tasks.
- BR-ORCH-41: Running tasks are allowed to complete their current **step** (not the full loop). The step completion is acknowledged by checking a Redis flag `agentis:task:{task_id}:shutdown_requested` before each new iteration.
- BR-ORCH-42: After the current step completes, the task state is checkpointed via `PostgresSaver`. The task status remains `RUNNING`.
- BR-ORCH-43: The task is re-enqueued to Celery so another worker picks it up. The new worker loads the checkpoint and continues from the last step.
- BR-ORCH-44: Shutdown grace period: 60 seconds (Kubernetes `terminationGracePeriodSeconds: 60`). If a step has not completed within 60 seconds, the worker is killed; the task status is set to `FAILED` with `error_code: "worker_killed"` by the Kubernetes pre-stop hook.

---

## 6. Epic 4 — Tool Registry & Execution

### 6.1 Overview

The Tool Registry is a catalog of discrete capabilities the agent can invoke. Each tool is a self-describing unit. At runtime, tools are RPC clients that communicate with processes inside the sandbox container.

### 6.2 Tool Architecture

```python
class BaseTool(ABC):
    name: str           # Unique identifier, snake_case
    description: str    # LLM-readable description (injected into system prompt)
    input_schema: dict  # JSON Schema for parameters
    output_schema: dict # JSON Schema for results

    @abstractmethod
    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        """
        SessionContext provides: sandbox_socket_path, session_id, secrets_accessor.
        The execute() method sends a JSON-RPC request to the sandbox and returns the result.
        """
        ...
```

All tool `execute()` methods are RPC clients. They do not run code locally.

**RPC protocol:** JSON-RPC 2.0 over Unix domain socket (development) or TCP with mTLS (production). The sandbox container exposes a tool server on port 9999. The orchestrator connects to it via the sandbox manager.

### 6.3 Secret Injection

Secrets (API keys for email, calendar, HTTP integrations) are never passed to the LLM's context. The flow:

1. The orchestrator's `think` node produces a tool call: `{"tool": "email", "params": {"to": "...", "subject": "..."}}`.
2. The Tool Registry's `execute()` method calls `session.secrets_accessor.get("email_api_key")`.
3. `secrets_accessor` retrieves the secret from HashiCorp Vault (or K8s Secret) using the session's service account credentials.
4. The secret is injected into the RPC request headers, never into `params` (which are visible in `task_steps`).
5. The sandbox receives the RPC call with the secret in a separate authentication header, not in the tool parameters.

### 6.4 Built-in Tools

#### Tool: `browser`

| Property | Value |
|----------|-------|
| Engine | Playwright (Chromium, headless), runs **inside sandbox** |
| Communication | JSON-RPC to sandbox port 9999 |
| Auth support | Cookie injection (cookies stored in sandbox session, not visible to LLM) |
| Rate limiting | Per-domain: 1 request/second (configurable) |

Actions:
```
browser.navigate(url: str) → {title: str, url: str}
browser.click(selector: str) → {success: bool}
browser.fill(selector: str, value: str) → {success: bool}
browser.extract_text(selector?: str) → {text: str, truncated: bool}
browser.screenshot() → {image_base64: str, mime_type: "image/png"}
browser.find_links(filter_pattern?: str) → {links: [{text, url}]}
browser.wait_for_selector(selector: str, timeout_ms?: int) → {found: bool}
browser.scroll(direction: "up"|"down", pixels: int) → {success: bool}
```

**Business Rules:**
- BR-TOOL-01: URLs must pass the sandbox egress proxy domain allowlist before navigation.
- BR-TOOL-02: `extract_text` output is truncated at `AGENTIS_TOOL_OUTPUT_MAX_TOKENS` tokens (Section 5.4 BR-ORCH-14).
- BR-TOOL-03: Screenshots are stored as artifacts if `save_as_artifact: true` is passed.
- BR-TOOL-04: The browser session (cookies, localStorage) persists within a task but is destroyed when the sandbox is torn down.

#### Tool: `code_executor`

| Property | Value |
|----------|-------|
| Runtimes | Python 3.12, Node.js 22, Bash |
| Execution | Inside sandbox container |
| Timeout | 120s per execution (configurable) |
| Output | stdout (truncated), stderr (truncated), generated files list |

Actions:
```
code_executor.run_python(code: str, timeout_s?: int) → ExecutionResult
code_executor.run_node(code: str, timeout_s?: int) → ExecutionResult
code_executor.run_bash(command: str, timeout_s?: int) → ExecutionResult
```

`ExecutionResult: {stdout: str, stderr: str, exit_code: int, generated_files: [str], truncated: bool}`

**Business Rules:**
- BR-TOOL-10: Code execution has no access to the host filesystem or network (except via the sandbox egress proxy).
- BR-TOOL-11: Generated files in `/workspace/outputs/` are automatically added to `task_steps` as pending artifacts.
- BR-TOOL-12: Execution timeout of 120s applies to the subprocess inside the sandbox. The RPC call has a separate 130s timeout.

#### Tool: `file_system`

Operates on `/workspace/` inside the sandbox only.

```
file_system.write(path: str, content: str|bytes) → {success: bool, size_bytes: int}
file_system.read(path: str) → {content: str, truncated: bool}
file_system.list(directory: str) → {entries: [{name, type, size_bytes, modified_at}]}
file_system.delete(path: str) → {success: bool}
file_system.copy(src: str, dst: str) → {success: bool}
file_system.compress(paths: [str], archive_name: str) → {archive_path: str}
```

**Business Rules:**
- BR-TOOL-20: Paths must stay within `/workspace/`. Paths containing `../` are rejected with a permanent error.
- BR-TOOL-21: Total workspace disk usage is enforced via the container disk quota (5 GB default).

#### Tool: `web_search`

| Property | Value |
|----------|-------|
| Backends | Brave Search API (default), SearXNG (self-hosted), Tavily |
| Configuration | `AGENTIS_SEARCH_BACKEND` env var |

```
web_search.search(query: str, num_results?: int, language?: str, time_range?: str) 
  → {results: [{title, url, snippet, published_at}]}
```

**Business Rules:**
- BR-TOOL-30: `num_results` max 20, default 10.
- BR-TOOL-31: `time_range` values: `day`, `week`, `month`, `year`.
- BR-TOOL-32: The search query is passed through the sandbox egress proxy; results do not require the browser tool.

#### Tool: `doc_parser`

```
doc_parser.parse(file_path: str) → {text: str, metadata: dict, truncated: bool}
doc_parser.extract_tables(file_path: str) → {tables: [{headers: [str], rows: [[str]]}]}
doc_parser.convert(file_path: str, target_format: str) → {output_path: str}
```

Supported formats: PDF, DOCX, XLSX, PPTX, HTML, Markdown, CSV, ODP, ODS, ODT.
Engine: Docling (primary), LibreOffice headless (format conversion).

#### Tool: `http_caller`

```
http_caller.request(
  method: "GET"|"POST"|"PUT"|"PATCH"|"DELETE",
  url: str,
  headers?: dict,
  body?: dict|str,
  auth?: {type: "bearer"|"api_key"|"basic", credentials: "<secret_ref>"}
) → {status_code: int, headers: dict, body: str, truncated: bool}
```

**Business Rules:**
- BR-TOOL-40: `url` must pass the sandbox egress proxy allowlist.
- BR-TOOL-41: `credentials` is a reference to a secret name in the Vault, not the secret value itself. The Tool Registry resolves it via `secrets_accessor`.
- BR-TOOL-42: Non-GET requests to external URLs trigger HITL (Section 4.3 BR-TASK-55) unless the URL is in the operator-configured safe domain list.

#### Tool: `email` (operator-enabled, Phase 2)

```
email.send(to: [str], subject: str, body: str, attachments?: [str]) → {message_id: str}
email.read_inbox(limit?: int, filter?: str) → {emails: [Email]}
email.search(query: str) → {emails: [Email]}
```

Always triggers HITL before `email.send`.

#### Tool: `calendar` (operator-enabled, Phase 2)

```
calendar.create_event(title: str, start: ISO8601, end: ISO8601, attendees?: [str], description?: str) → {event_id: str}
calendar.list_events(date_from: ISO8601, date_to: ISO8601) → {events: [Event]}
calendar.delete_event(event_id: str) → {success: bool}
```

Always triggers HITL before `create_event` and `delete_event`.

### 6.5 Tool Extension API

Third-party tools registered via:
1. **Python plugin**: implement `BaseTool`, install in worker environment, auto-discovered via entry points.
2. **MCP Server**: any MCP-compatible server auto-registers tools via `mcp://` discovery URL. The sandbox is not required for MCP tools running outside it.
3. **OpenAPI spec**: provide a Swagger/OpenAPI 3.0 URL; tools are auto-generated with `http_caller` as the execution backend.

---

## 7. Epic 5 — Sandbox Environment

### 7.1 Overview

Every agent session runs inside an isolated sandbox — a Kata Container (micro-VM with hardware isolation) in production, or a hardened Docker container in development. The sandbox is ephemeral: created at task start, destroyed at task end.

### 7.2 Sandbox Lifecycle

```
TASK_SUBMITTED → sandbox_manager.create_session(task_id)
                   → provision Kata Container (or Docker)
                   → start tool server on port 9999
                   → mount input files at /workspace/inputs/
                   → return sandbox_endpoint
TASK_RUNNING   → tool calls routed to sandbox via JSON-RPC
TASK_DONE      → sandbox_manager.destroy_session(task_id)
                   → stop container
                   → collect output files → promote to artifacts
                   → clean ephemeral filesystem
```

### 7.3 Container Specification

```yaml
# Production (K3s + Kata Containers)
runtimeClassName: kata-containers
resources:
  requests:
    cpu: "0.5"
    memory: "512Mi"
  limits:
    cpu: "2.0"
    memory: "2Gi"
    ephemeral-storage: "5Gi"
securityContext:
  readOnlyRootFilesystem: true
  runAsNonRoot: true
  runAsUser: 1000
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
network:
  # Outbound via Squid proxy only
  egress_proxy: "http://squid.agentis-system.svc.cluster.local:3128"
lifecycle:
  postStart: ["start-tool-server.sh"]
  preStop:   ["collect-artifacts.sh"]
timeout_seconds: 1800  # 30 minutes max
```

### 7.4 Pre-installed Software

- Python 3.12 + pip (pandas, numpy, matplotlib, scipy, reportlab, openpyxl, Pillow, requests)
- Node.js 22 + npm
- Playwright (Chromium, Firefox — Chromium is default)
- Docling + LibreOffice headless
- pandoc, ffmpeg, curl, jq, git (read-only, for cloning repos if needed)
- agentis-tool-server (internal — handles JSON-RPC dispatch)

### 7.5 Egress Proxy (Squid)

**Business Rules:**
- BR-SAND-01: All outbound HTTP/HTTPS traffic from the sandbox is routed through a Squid proxy.
- BR-SAND-02: The base allowlist (operator-configured): common public knowledge sources, search APIs, PyPI, npm registry, GitHub (for code tasks).
- BR-SAND-03: A single Squid instance serves all sandboxes. Per-sandbox dynamic ACLs are implemented via Squid's `external_acl_type` pointing to an Agentis ACL service that checks `task_id → allowed_domains` in Redis.
- BR-SAND-04: An operator can add or remove domains from the global allowlist. A task submission can further restrict (subset) but never expand beyond the org's allowlist.
- BR-SAND-05: All proxy requests are logged with `task_id` for audit.
- BR-SAND-06: SSL bumping (MITM inspection) is NOT performed. CONNECT tunneling is allowed to allowlisted HTTPS destinations only.

### 7.6 Session Pool Management

**Business Rules:**
- BR-SAND-10: The sandbox manager maintains a pool of **warm containers** (pre-started, waiting for assignment) to reduce session startup latency. Default pool size: `AGENTIS_SANDBOX_WARM_POOL_SIZE` (default: 2).
- BR-SAND-11: When a task is submitted, a warm container is assigned immediately. The tool server is already running.
- BR-SAND-12: When a warm container is used, a new one is provisioned to replenish the pool (async, non-blocking).
- BR-SAND-13: Warm containers have a TTL of 5 minutes. If not assigned within 5 minutes, they are destroyed and replaced. This prevents stale state accumulation.
- BR-SAND-14: If the pool is empty and no warm container is available, the task starts with a cold container. Cold start SLA: ≤ 10 seconds.
- BR-SAND-15: Max concurrent sandboxes: `AGENTIS_SANDBOX_MAX_CONCURRENT` (default: 10). Tasks beyond this limit queue in Celery until a sandbox is available.

---

## 8. Epic 6 — Memory System

### 8.1 Overview

Four memory layers serve different purposes and scopes. The orchestrator assembles context from all layers before each THINK call.

### 8.2 Memory Layers

| Layer | Storage | TTL | Scope | Purpose |
|-------|---------|-----|-------|---------|
| Working | LangGraph `AgentState` (in-process) | Session | Current task | Plan, tool history, scratchpad |
| Short-term | Redis DB 1 | 24h | User | Recent task summaries, user preferences |
| Long-term | Qdrant (vectors) + PostgreSQL (refs) | Permanent | User | Semantic knowledge base |
| Episodic | PostgreSQL `task_steps` | Permanent | Task | Full trace for replay and audit |

### 8.3 Features

#### Feature MEM-1: Working Memory

Working memory is `AgentState` (Section 5.3). It is persisted to PostgreSQL via `PostgresSaver` at every step. No additional implementation needed beyond the LangGraph setup.

#### Feature MEM-2: Short-Term Memory

**Business Rules:**
- BR-MEM-10: At task completion (or failure), the orchestrator generates a 2-3 sentence summary of the task and stores it in Redis DB 1 with key `mem:short:{user_id}:recent` as a list (LPUSH, max 20 entries via LTRIM).
- BR-MEM-11: User preferences expressed during tasks (e.g., "I prefer tables in English") are extracted by the reflect node and stored in Redis DB 1 with key `mem:short:{user_id}:prefs`.
- BR-MEM-12: Short-term memory is injected into the system prompt (max 500 tokens).

#### Feature MEM-3: Long-Term Memory (Qdrant)

**Business Rules:**
- BR-MEM-20: At task completion, the orchestrator generates **memory entries** from the task — key facts discovered, user-specific knowledge gained — and embeds them using `voyage-multilingual-2`.
- BR-MEM-21: Each memory entry is stored in Qdrant (`agentis_memory` collection) with payload: `{id, user_id, org_id, content, summary, source_task_id, created_at, importance, tags, language}`.
- BR-MEM-22: A reference record is created in the `memory_entries` PostgreSQL table linking the Qdrant point ID to the source task.
- BR-MEM-23: At THINK time, the orchestrator retrieves the top-10 semantically relevant memories using **hybrid search** (dense cosine + sparse BM25), filtered by `user_id`. Results are ranked by `score × importance`.
- BR-MEM-24: Injection budget: max `AGENTIS_MEMORY_INJECTION_TOKENS` (default: 2000) tokens of memory per THINK call.
- BR-MEM-25: Users can delete all their memory from `/settings`. This triggers a Celery task that deletes all Qdrant points for the user and the PostgreSQL reference records.
- BR-MEM-26: Users can delete a specific memory entry via `DELETE /memory/{id}`.

**Qdrant Initialization:**
- BR-MEM-27: On first startup, the system checks if the `agentis_memory` collection exists via Qdrant's REST API. If not, it creates it with:
  ```json
  {
    "vectors": {"size": 1024, "distance": "Cosine"},
    "sparse_vectors": {"bm25": {"modifier": "idf"}},
    "on_disk_payload": true
  }
  ```
- BR-MEM-28: Qdrant collection initialization is idempotent. Re-running startup with an existing collection produces no error.

#### Feature MEM-4: Memory Maintenance

**Business Rules:**
- BR-MEM-30: **Importance decay**: a Celery beat job runs every Sunday at 02:00 UTC. It selects all memory entries older than 30 days and reduces their `importance` score by 10% (multiplicative: `importance = importance × 0.9`). Minimum importance floor: 0.1.
- BR-MEM-31: **Pruning**: entries with `importance < 0.05` are deleted (Qdrant point + PostgreSQL record). This threshold is reached after ~27 decay cycles (~6 months of no access).
- BR-MEM-32: **Importance refresh**: when a memory entry is retrieved and used in a THINK call, its `importance` is updated to `min(1.0, importance + 0.1)`. This implements a use-based recency bias.
- BR-MEM-33: **Summarization**: task transcripts > 50 steps are summarized before episodic storage. Raw steps are retained in `task_steps` but the task record's `result_summary` field holds the LLM-generated summary.

---

## 9. Epic 7 — Frontend & Real-Time Streaming

### 9.1 Overview

The frontend is a Next.js 15 App Router application. It delivers a bilingual interface with real-time task monitoring via SSE and HITL support via WebSockets.

### 9.2 Technology Decisions

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Framework | Next.js 15 (App Router) | SSR, streaming, layouts |
| UI components | shadcn/ui + Tailwind CSS | Accessible, unstyled base |
| Server state | TanStack Query (React Query v5) | Cache, background refetch, pagination |
| Client state | Zustand | Lightweight, no boilerplate |
| i18n | next-intl | Next.js native, Server Components compatible |
| Forms | React Hook Form + Zod | Type-safe validation |
| Real-time | SSE (task trace) + WebSocket (HITL) | SSE for unidirectional; WS for bidirectional |

### 9.3 Routes

| Route | Description |
|-------|-------------|
| `/` | New task submission form |
| `/login` | Email/password login |
| `/register` | Account registration |
| `/tasks` | Task history with filters |
| `/tasks/[id]` | Live task view |
| `/settings` | Language, API keys, memory, token usage |
| `/admin` | Operator dashboard (requires `admin`/`operator` role) |
| `/admin/users` | User management |
| `/admin/audit` | Audit log viewer |
| `/admin/tools` | Tool enable/disable |
| `/admin/config` | LLM provider configuration (operator only) |

### 9.4 SSE Event Stream

Event types emitted by the server on `GET /tasks/{id}/stream`:

```typescript
type AgentEvent =
  | { id: string; type: "plan_created";          data: Plan }
  | { id: string; type: "think";                 data: { content: string; tokens: number } }
  | { id: string; type: "tool_call";             data: { tool: string; params: object; call_id: string } }
  | { id: string; type: "tool_result";           data: { tool: string; output: object; call_id: string; duration_ms: number } }
  | { id: string; type: "plan_updated";          data: Plan }
  | { id: string; type: "context_summarized";    data: { tokens_freed: number } }
  | { id: string; type: "user_input_required";   data: { prompt: string; options?: string[]; timeout_s: number } }
  | { id: string; type: "task_completed";        data: { summary: string; artifacts: Artifact[] } }
  | { id: string; type: "task_failed";           data: { error: string; error_code: string; retryable: boolean } }
```

**Business Rules:**
- BR-FRONT-01: Each SSE event has an `id` field (sequential integer). The `Last-Event-ID` header on reconnect causes the server to replay all events from that ID.
- BR-FRONT-02: The frontend sets `EventSource` with `withCredentials: true` (for cookie authentication).
- BR-FRONT-03: On SSE connection loss, the frontend attempts reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s), passing the last received `id` as `Last-Event-ID`.
- BR-FRONT-04: A heartbeat event `{ type: "heartbeat" }` is emitted every 30 seconds to keep the connection alive through proxies/load balancers.

### 9.5 WebSocket (HITL)

WebSocket connection: `wss://{host}/ws/tasks/{task_id}` (authenticated via cookie or `?token=` query param for clients that cannot set headers).

**Business Rules:**
- BR-FRONT-10: The WebSocket connection is established when the user opens a task view. The connection is maintained for the task's lifetime.
- BR-FRONT-11: On receiving `user_input_required` via SSE, the frontend shows an input form and sends the response over WebSocket: `{"type": "user_input", "task_id": "...", "response": "..."}`.
- BR-FRONT-12: If the WebSocket is disconnected when a HITL event fires, the event is buffered server-side (Section 4.3 BR-TASK-54).

### 9.6 Authentication Flow (Frontend)

1. `POST /auth/login` → response sets `refresh_token` as `httpOnly SameSite=Strict` cookie.
2. `access_token` from response body is stored in Zustand (memory only, never persisted to localStorage).
3. All API calls attach `Authorization: Bearer {access_token}`.
4. On 401 response: frontend calls `POST /auth/refresh` (cookie is sent automatically). Response includes new `access_token`. Original request is retried transparently via TanStack Query's `onError` callback.
5. On page reload: `access_token` is lost. Frontend calls `POST /auth/refresh` on mount (cookie is still valid).
6. On logout: `POST /auth/logout` revokes refresh token. Cookie cleared by server via `Set-Cookie: refresh_token=; Max-Age=0`. Zustand state cleared.

### 9.7 File Upload

**Business Rules:**
- BR-FRONT-20: File inputs for tasks are uploaded via `multipart/form-data` in the same `POST /tasks` request (fields: `goal`, `language`, `options`, `files[]`).
- BR-FRONT-21: Upload progress is shown via the `XMLHttpRequest` progress event (or fetch + ReadableStream for browsers supporting it).
- BR-FRONT-22: Files are validated on the frontend before upload: type whitelist, max size 50 MB per file, max 5 files. Server-side validation is the authority.

---

## 10. Epic 8 — API Gateway

### 10.1 Overview

The API Gateway is a FastAPI application. It handles authentication, rate limiting, request routing, and real-time event relay.

### 10.2 Standard Error Response

All error responses follow this schema:

```json
{
  "error": {
    "code": "string",          // machine-readable, snake_case
    "message": "string",       // human-readable, in request language
    "details": {}              // optional, validation errors etc.
  },
  "request_id": "uuid"
}
```

Common error codes:
- `invalid_input` (400)
- `unauthenticated` (401)
- `forbidden` (403)
- `not_found` (404)
- `rate_limited` (429)
- `llm_unavailable` (503)
- `sandbox_unavailable` (503)
- `internal_error` (500)

### 10.3 Rate Limiting

**Business Rules:**
- BR-API-01: Rate limits apply per authenticated principal (user or API key).
- BR-API-02: Default limits (configurable by operator):
  - `POST /tasks`: 60 requests/hour per user.
  - All other endpoints: 1000 requests/hour per user.
  - Anonymous (health check): 100 requests/minute per IP.
- BR-API-03: Rate limit headers returned on every response: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (Unix timestamp).
- BR-API-04: When rate limited: HTTP 429 with `Retry-After` header (seconds until reset).
- BR-API-05: Rate limit state stored in Redis DB 0 (shared with Celery broker) using the sliding window algorithm.

### 10.4 Request Tracing

- BR-API-10: Every request gets a `X-Request-ID` header (generated by the gateway if not provided by the client).
- BR-API-11: `request_id` is included in all error responses and logs.
- BR-API-12: `X-Request-ID` is propagated to Celery tasks and Langfuse traces for end-to-end correlation.

---

## 11. Epic 9 — Multilinguality

### 11.1 Supported Languages

| Language | UI | Agent responses | System prompts |
|----------|----|-----------------|----------------|
| French (fr) | Full | Full | Source of truth (EN) → response (FR) |
| English (en) | Full | Full | Source of truth (EN) → response (EN) |

### 11.2 Features

#### Feature LANG-1: Language Selection

**Business Rules:**
- BR-LANG-01: User sets their default language in `/settings`. Default: browser `Accept-Language` header (matched to `en` or `fr`; fallback `en`).
- BR-LANG-02: Per-task language override: the `language` field in `POST /tasks` body. Also available as a selector in the task submission UI.
- BR-LANG-03: Auto-detection: if `language` is omitted from the API request AND no `Accept-Language` match, detect from the `goal` text using `lingua` (ISO 639-1 codes). If detection confidence < 0.8, default to the user's account language.
- BR-LANG-04: The user can explicitly override the detected language from the task submission UI before submitting.

#### Feature LANG-2: Agent System Prompts

**Business Rules:**
- BR-LANG-10: All system prompts are written and maintained **exclusively in English**. No translated versions exist.
- BR-LANG-11: The user's language preference is injected as the final instruction in the assembled system prompt:
  ```python
  LANGUAGE_INSTRUCTION = {
      "fr": "Always respond to the user in French (fr), regardless of the language of your internal reasoning or tool outputs.",
      "en": "Always respond to the user in English (en).",
  }
  ```
- BR-LANG-12: Tool outputs (webpage content, search results, documents) may be in any language. The agent processes them and responds in the user's language.

#### Feature LANG-3: UI i18n

**Business Rules:**
- BR-LANG-20: All UI strings in `/messages/en.json` and `/messages/fr.json`.
- BR-LANG-21: All UI labels, error messages, ARIA labels, and help text are fully translated. No untranslated strings ship to production.
- BR-LANG-22: The locale is stored in a `NEXT_LOCALE` cookie and in the URL prefix (`/fr/`, `/en/`). The cookie takes precedence.

---

## 12. Epic 10 — Admin & Observability

### 12.1 Features

#### Feature ADMIN-1: Audit Log

**Business Rules:**
- BR-ADMIN-01: Every tool call, LLM call, user login, task event, and admin action is logged immutably to the `audit_log` table.
- BR-ADMIN-02: The application DB user has INSERT only on `audit_log` — no UPDATE or DELETE grants. Physical deletion requires a DBA.
- BR-ADMIN-03: `admin` can query audit log filtered by `user_id`, `event_type`, `session_id`, `created_at` range.
- BR-ADMIN-04: Audit log retention: 2 years. A DBA-level maintenance job archives and purges records older than 2 years.

#### Feature ADMIN-2: Tool Management

**Business Rules:**
- BR-ADMIN-10: Operators can enable/disable tools globally or per-organization via `PATCH /admin/tools/{name}`.
- BR-ADMIN-11: When a tool is disabled globally, tasks currently using that tool are NOT interrupted. The next invocation of that tool in a running task returns a permanent error: `"tool_disabled"`. The reflect node must adapt.
- BR-ADMIN-12: A disabled tool is not injected into the system prompt for new tasks started after the disable action.
- BR-ADMIN-13: Per-organization tool restrictions are checked at task submission. If a requested tool is org-disabled, the task is rejected with `invalid_input`.

#### Feature ADMIN-3: LLM Configuration (Operator)

**Business Rules:**
- BR-ADMIN-20: Operators configure the LLM provider and model via the admin UI or environment variables. Changes take effect for new tasks; running tasks continue with the provider that was active at start.
- BR-ADMIN-21: Operator can set per-org LLM provider overrides (Phase 2).
- BR-ADMIN-22: LLM API keys are stored encrypted in PostgreSQL (AES-256-GCM) and never returned in API responses.

#### Feature ADMIN-4: Observability Stack

**Langfuse (LLM Traces):**
Each LLM call is traced with: `task_id`, `step`, input messages, output, token counts, latency, cost estimate. Integrated via LangChain callback.

**Prometheus Metrics:**

| Metric | Type | Labels |
|--------|------|--------|
| `agentis_tasks_total` | Counter | `status`, `language` |
| `agentis_task_duration_seconds` | Histogram | `status` |
| `agentis_tool_calls_total` | Counter | `tool`, `outcome` |
| `agentis_llm_tokens_total` | Counter | `provider`, `model`, `direction` |
| `agentis_llm_latency_seconds` | Histogram | `provider`, `model` |
| `agentis_active_sessions` | Gauge | — |
| `agentis_sandbox_containers_active` | Gauge | `state` (warm/assigned) |
| `agentis_context_summarizations_total` | Counter | — |
| `agentis_hitl_events_total` | Counter | `resolution` (answered/timeout/cancelled) |

**Grafana Alerts:**
- Task failure rate > 10% over 5 minutes.
- Average task duration > 10 minutes.
- LLM error rate > 5%.
- Sandbox container count > 80% of `AGENTIS_SANDBOX_MAX_CONCURRENT`.
- Disk usage > 80%.
- p95 LLM latency > 30 seconds.

#### Feature ADMIN-5: Webhook Notifications

**Business Rules:**
- BR-ADMIN-30: Task submissions can include `notify_webhook: url`. On task completion or failure, the server sends a POST to the webhook URL.
- BR-ADMIN-31: Webhook payload includes: `{task_id, status, summary, artifacts, completed_at}`.
- BR-ADMIN-32: Webhook requests are authenticated with an HMAC-SHA256 signature in the `X-Agentis-Signature` header: `HMAC(secret, body)`. The secret is the API key of the user who submitted the task.
- BR-ADMIN-33: Failed webhook deliveries are retried 5 times with exponential backoff (10s, 40s, 160s, 640s, 2560s). After 5 failures, the webhook URL is flagged as `unhealthy` and further deliveries are suspended until the user re-enables it.

#### Feature ADMIN-6: Organization Management (Phase 2)

**Business Rules:**
- BR-ADMIN-40: An operator creates organizations via `POST /admin/organizations`.
- BR-ADMIN-41: Users join organizations via invite link or admin assignment.
- BR-ADMIN-42: An organization has: `name`, `slug`, `llm_config` (optional override), `allowed_tools` (subset), `token_budget_monthly`, `max_concurrent_tasks`.
- BR-ADMIN-43: A user can belong to multiple organizations. Their active organization context is sent as `X-Organization-ID` header or set in account settings.

---

## 13. Epic 11 — Multi-Agent Collaboration (Phase 4)

### 13.1 Vision

Phase 4 introduces **agent teams**: multiple specialized agents working in parallel or sequence to complete a goal, coordinated by a meta-orchestrator.

### 13.2 High-Level Architecture (Phase 4)

```
META-ORCHESTRATOR (Supervisor Agent)
    ↓ decomposes goal into sub-goals
    ↓ assigns sub-goals to specialized agents
+------------------+  +------------------+  +------------------+
| Research Agent   |  | Analysis Agent   |  | Writer Agent     |
| (browser, search)|  | (code_executor)  |  | (file_system)    |
+------------------+  +------------------+  +------------------+
    ↓                      ↓                     ↓
    └──────────── shared message bus (Redis pub/sub) ──────────┘
                           ↓
               META-ORCHESTRATOR aggregates results → REPORT
```

### 13.3 Non-Goals for Phase 4

- Agents do not share the same sandbox. Each agent has its own isolated sandbox.
- Agents communicate results via the message bus, never via direct memory access.
- The human user interacts only with the meta-orchestrator; individual agent HITL events are escalated up to the meta-orchestrator level.

---

## 14. Data Model

### 14.1 Schema

```sql
-- ============================================================
-- ENUMS
-- ============================================================

CREATE TYPE task_status AS ENUM (
    'submitted', 'planning', 'running', 'waiting_for_input',
    'completed', 'failed', 'cancelled'
);

CREATE TYPE task_step_type AS ENUM (
    'think', 'tool_call', 'tool_result', 'reflect', 'plan_update',
    'user_input', 'context_summarized', 'report'
);

CREATE TYPE user_role AS ENUM ('user', 'admin', 'operator');

-- ============================================================
-- ORGANIZATIONS (Phase 2 schema, Phase 1 tables created empty)
-- ============================================================

CREATE TABLE organizations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    slug                TEXT UNIQUE NOT NULL,
    llm_provider        TEXT,                    -- override global config
    llm_model           TEXT,
    allowed_tools       TEXT[],                  -- NULL = all tools allowed
    token_budget_monthly BIGINT,                 -- NULL = no limit
    max_concurrent_tasks INT DEFAULT 5,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ              -- soft delete
);

CREATE TABLE organization_memberships (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    role            user_role NOT NULL DEFAULT 'user',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(organization_id, user_id)
);

-- ============================================================
-- USERS
-- ============================================================

CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email               TEXT UNIQUE NOT NULL,
    email_lower         TEXT UNIQUE NOT NULL GENERATED ALWAYS AS (lower(email)) STORED,
    name                TEXT,
    password_hash       TEXT,                    -- NULL for OIDC-only users
    role                user_role NOT NULL DEFAULT 'user',
    language            TEXT NOT NULL DEFAULT 'fr',
    active_org_id       UUID REFERENCES organizations(id),
    token_used_this_month BIGINT NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ
);

CREATE INDEX idx_users_email_lower ON users(email_lower);
CREATE INDEX idx_users_active ON users(deleted_at) WHERE deleted_at IS NULL;

-- ============================================================
-- AUTH
-- ============================================================

CREATE TABLE refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ,
    last_ip     INET
);

CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_hash ON refresh_tokens(token_hash);

CREATE TABLE api_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash        TEXT UNIQUE NOT NULL,
    label           TEXT,
    last_used_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ
);

CREATE INDEX idx_api_keys_user ON api_keys(user_id);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);

-- ============================================================
-- TASKS
-- ============================================================

CREATE TABLE tasks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id),
    organization_id     UUID REFERENCES organizations(id),
    goal                TEXT NOT NULL,
    status              task_status NOT NULL DEFAULT 'submitted',
    language            TEXT NOT NULL DEFAULT 'fr',
    plan                JSONB,
    allowed_tools       TEXT[],
    max_iterations      INT NOT NULL DEFAULT 30,
    result_summary      TEXT,
    error_message       TEXT,
    error_code          TEXT,
    partial             BOOLEAN NOT NULL DEFAULT FALSE,  -- token budget hit
    notify_webhook      TEXT,
    total_tokens        BIGINT NOT NULL DEFAULT 0,
    total_steps         INT NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    deleted_at          TIMESTAMPTZ  -- soft delete
);

-- Core query patterns
CREATE INDEX idx_tasks_user_status   ON tasks(user_id, status, created_at DESC);
CREATE INDEX idx_tasks_org           ON tasks(organization_id, created_at DESC);
CREATE INDEX idx_tasks_status        ON tasks(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_tasks_active        ON tasks(deleted_at) WHERE deleted_at IS NULL;
-- Full-text search on goal
CREATE INDEX idx_tasks_goal_fts      ON tasks USING gin(to_tsvector('simple', goal));

-- ============================================================
-- TASK STEPS (episodic memory)
-- ============================================================

CREATE TABLE task_steps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    step_number     INT NOT NULL,
    step_type       task_step_type NOT NULL,
    content         JSONB NOT NULL,
    tokens_used     INT NOT NULL DEFAULT 0,
    duration_ms     INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(task_id, step_number)
);

CREATE INDEX idx_task_steps_task     ON task_steps(task_id, step_number);
CREATE INDEX idx_task_steps_type     ON task_steps(task_id, step_type);

-- ============================================================
-- ARTIFACTS
-- ============================================================

CREATE TABLE artifacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    mime_type       TEXT,
    size_bytes      BIGINT NOT NULL DEFAULT 0,
    storage_key     TEXT NOT NULL,  -- format: "{backend}://{path}", e.g. "minio://bucket/..."
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,    -- set to NOW() + retention on creation
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX idx_artifacts_task      ON artifacts(task_id);
CREATE INDEX idx_artifacts_expiry    ON artifacts(expires_at) WHERE deleted_at IS NULL;

-- ============================================================
-- MEMORY
-- ============================================================

CREATE TABLE memory_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES organizations(id),
    qdrant_point_id UUID NOT NULL UNIQUE,
    source_task_id  UUID REFERENCES tasks(id) ON DELETE SET NULL,
    importance      FLOAT NOT NULL DEFAULT 0.5,
    tags            TEXT[],
    language        TEXT NOT NULL DEFAULT 'en',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_accessed_at TIMESTAMPTZ
);

CREATE INDEX idx_memory_user        ON memory_entries(user_id, importance DESC);
CREATE INDEX idx_memory_task        ON memory_entries(source_task_id);
CREATE INDEX idx_memory_decay       ON memory_entries(updated_at) WHERE importance > 0.05;

-- ============================================================
-- AUDIT LOG
-- ============================================================

CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id         UUID,          -- NULL for system events
    organization_id UUID,
    session_id      UUID,
    task_id         UUID,
    event_type      TEXT NOT NULL,
    event_data      JSONB NOT NULL,
    ip_address      INET,
    outcome         TEXT,          -- 'success' | 'failure' | 'blocked'
    request_id      UUID
);

-- No foreign keys on audit_log intentionally (immutable, append-only)
-- App user: INSERT only (no UPDATE, DELETE grants)
CREATE INDEX idx_audit_user_time    ON audit_log(user_id, created_at DESC);
CREATE INDEX idx_audit_task         ON audit_log(task_id, created_at DESC);
CREATE INDEX idx_audit_session      ON audit_log(session_id);
CREATE INDEX idx_audit_event_type   ON audit_log(event_type, created_at DESC);
```

### 14.2 Migration Strategy

- All schema changes via **Alembic** (Python migration tool, integrated with SQLAlchemy).
- Migration files in `backend/alembic/versions/`.
- `alembic upgrade head` runs automatically as a Kubernetes init container before API pods start.
- Rollback: `alembic downgrade -1`. Each migration must have a corresponding `downgrade()` function.
- Zero-downtime migrations: prefer additive changes (add columns, add indexes, add tables). Destructive changes (drop columns, rename) require multi-step migrations with backwards-compatible transitions.

---

## 15. API Reference

### 15.1 Base URL

```
https://agentis.{your-domain}/api/v1
```

### 15.2 Authentication

| Method | Header | Format |
|--------|--------|--------|
| JWT Bearer | `Authorization: Bearer <token>` | RS256 JWT |
| API Key | `X-API-Key: <key>` | `agentis_sk_<base62>` |
| WebSocket | Cookie `refresh_token` or `?token=<jwt>` query param | |

### 15.3 Endpoints

#### Authentication

```
POST   /auth/register              Register new user
POST   /auth/login                 Login, returns access_token (body) + refresh_token (cookie)
POST   /auth/refresh               Refresh access token (refresh_token from cookie)
POST   /auth/logout                Revoke refresh token, clear cookie
```

#### Tasks

```
POST   /tasks                      Submit task (multipart/form-data for file inputs)
GET    /tasks                      List tasks (paginated, filterable)
GET    /tasks/{id}                 Get task details
DELETE /tasks/{id}                 Cancel task
GET    /tasks/{id}/stream          SSE event stream (supports Last-Event-ID)
POST   /tasks/{id}/input           Submit HITL response
GET    /tasks/{id}/artifacts       List task artifacts
GET    /tasks/{id}/artifacts/{aid}/download  Get signed download URL
```

#### Memory

```
GET    /memory                     List memory entries (paginated)
DELETE /memory                     Delete all user memory (async)
DELETE /memory/{id}                Delete specific memory entry
```

#### Settings

```
GET    /settings                   Get user settings
PATCH  /settings                   Update settings (language, etc.)
GET    /settings/usage             Token usage for current month
POST   /api-keys                   Create API key
GET    /api-keys                   List API keys
DELETE /api-keys/{id}              Revoke API key
```

#### Admin

```
GET    /admin/users                List users (paginated, filterable)
PATCH  /admin/users/{id}/role      Update user role
GET    /admin/audit-log            Query audit log (filterable)
GET    /admin/metrics              Usage statistics summary
GET    /admin/tools                List registered tools with status
PATCH  /admin/tools/{name}         Enable/disable tool
GET    /admin/tools/{name}/usage   Tool usage statistics
POST   /admin/organizations        Create organization (Phase 2)
GET    /admin/organizations        List organizations (Phase 2)
PATCH  /admin/organizations/{id}   Update org config (Phase 2)
GET    /admin/config/llm           Get current LLM config (keys redacted)
PATCH  /admin/config/llm           Update LLM config
```

#### WebSocket

```
WSS    /ws/tasks/{id}              Bidirectional HITL channel
```

### 15.4 POST /tasks Request Schema

```json
{
  "goal":           "string (required, max 10000 chars)",
  "language":       "string (optional, 'en'|'fr', defaults to user setting)",
  "options": {
    "max_iterations":   "integer (optional, default 30)",
    "allowed_tools":    "string[] (optional, subset of org-enabled tools)",
    "notify_webhook":   "string (optional, URL)"
  }
}
```

For file inputs: `multipart/form-data` with `goal`, `language`, `options` as JSON string fields, and `files[]` as file parts.

### 15.5 GET /tasks Query Parameters

```
after:          string (cursor for next page)
limit:          integer (1-100, default 20)
status:         string[] (filter by status, comma-separated)
language:       string (en|fr)
created_after:  ISO8601 datetime
created_before: ISO8601 datetime
search:         string (full-text search on goal)
include_deleted: boolean (admin only)
user_id:        uuid (admin only)
```

### 15.6 Cursor Pagination Response Schema

```json
{
  "data": [ ... ],
  "pagination": {
    "next_cursor": "string | null",
    "has_more": "boolean",
    "total": "integer (approximate)"
  }
}
```

---

## 16. Security Model

### 16.1 Authentication Security

- Passwords: bcrypt, cost factor 12.
- JWT: RS256. Private key stored in HashiCorp Vault (or K8s Secret). Rotated annually.
- Access tokens: 1 hour TTL, in-memory only (no storage).
- Refresh tokens: 30-day TTL, httpOnly SameSite=Strict Secure cookie, rotation on each use.
- Replay attack detection: see BR-AUTH-07. All sessions revoked on suspected replay.

### 16.2 CSRF Protection

- Access token in memory (not cookie) is the primary CSRF defense.
- Refresh token cookie is SameSite=Strict — prevents cross-site requests from triggering refresh.
- API endpoints check for `Content-Type: application/json` on state-modifying requests (simple defense against HTML form CSRF).

### 16.3 Transport Security

- All traffic over TLS 1.2+ (TLS 1.3 preferred).
- K3s: cert-manager with Let's Encrypt (or internal PKI).
- mTLS between orchestrator and sandbox tool server.
- `Strict-Transport-Security: max-age=63072000; includeSubDomains` header on all responses.

### 16.4 Sandbox Security

- Kata Containers: each sandbox is a QEMU micro-VM with its own kernel.
- `seccomp` profile: restricted syscall set.
- No host mounts.
- Read-only root filesystem; only `/workspace` is writable.
- Network egress via Squid proxy only; no direct internet access.
- Container killed automatically after `AGENTIS_SANDBOX_TIMEOUT_SECONDS` (default: 1800).
- All tool server communications authenticated with a per-session HMAC token.

### 16.5 Secret Management

- Operator API keys (LLM, search): stored in PostgreSQL, encrypted AES-256-GCM. Decrypted in memory only.
- User integration credentials (email, calendar): stored in HashiCorp Vault.
- Sandbox-injected secrets: never appear in `task_steps` content, only in tool execution layer.
- No secrets in Git, Docker images, or environment variable files committed to version control.

### 16.6 Input Validation

- All API inputs validated with Pydantic (FastAPI) before processing.
- `goal` text is treated as user content, never executed. Passed to LLM as a prompt string.
- File uploads: type validation (magic bytes, not just extension), size limits, virus scan via ClamAV (Phase 2).
- SQL: SQLAlchemy ORM with parameterized queries. No raw string SQL interpolation.

---

## 17. Infrastructure & Deployment

### 17.1 Deployment Topology

```
+------------------------------------------------------------------+
|                   K3s Cluster (on-premise)                        |
|                                                                    |
|  Namespace: agentis-system                                         |
|  +----------------+  +----------------+  +--------------------+   |
|  | agentis-api    |  | agentis-worker |  | agentis-ui         |   |
|  | (FastAPI)      |  | (Celery)       |  | (Next.js)          |   |
|  | Replicas: 2    |  | Replicas: 4    |  | Replicas: 2        |   |
|  | HPA: CPU 70%   |  | HPA: queue len |  |                    |   |
|  +----------------+  +----------------+  +--------------------+   |
|                                                                    |
|  +----------------+  +----------------+  +--------------------+   |
|  | PostgreSQL     |  | Redis          |  | Qdrant             |   |
|  | (StatefulSet)  |  | (StatefulSet)  |  | (StatefulSet)      |   |
|  | + PgBouncer    |  | DB0: Celery    |  |                    |   |
|  |   (Deployment) |  | DB1: Cache     |  |                    |   |
|  +----------------+  +----------------+  +--------------------+   |
|                                                                    |
|  +----------------+  +----------------+  +--------------------+   |
|  | Langfuse       |  | Prometheus     |  | Grafana + Loki     |   |
|  +----------------+  +----------------+  +--------------------+   |
|                                                                    |
|  +-------------------------------------------------------+        |
|  | Sandbox Pool (Kata Containers, RuntimeClass: kata)    |        |
|  | Namespace: agentis-sandboxes (network-isolated)       |        |
|  | Squid proxy sidecar per node                          |        |
|  +-------------------------------------------------------+        |
|                                                                    |
|  +--------------------+  +-------------------------------+        |
|  | HashiCorp Vault    |  | MinIO (artifacts, S3-compat)  |        |
|  | (secrets)          |  |                               |        |
|  +--------------------+  +-------------------------------+        |
+------------------------------------------------------------------+
```

### 17.2 PgBouncer Configuration

PgBouncer sits between all services and PostgreSQL:

```ini
[databases]
agentis = host=postgres port=5432 dbname=agentis

[pgbouncer]
pool_mode = transaction      # Required for LangGraph PostgresSaver
max_client_conn = 500
default_pool_size = 20
reserve_pool_size = 5
```

Transaction pool mode is required because LangGraph's `PostgresSaver` acquires and releases connections within individual database transactions.

### 17.3 Docker Compose (Development)

```yaml
services:
  api:      # FastAPI — port 8000
  worker:   # Celery workers
  ui:       # Next.js — port 3000
  postgres: # PostgreSQL 16
  pgbouncer:# PgBouncer
  redis:    # Redis 7 (DB0: Celery, DB1: cache)
  qdrant:   # Qdrant (was missing from v1 spec)
  langfuse: # LLM observability
  prometheus:
  grafana:
  squid:    # Egress proxy (dev: permissive config)
  minio:    # S3-compatible artifact storage
  vault-dev:# Vault in dev mode (auto-unsealed, no persistence)
```

### 17.4 Backup Strategy

| Data | Backup method | Frequency | Retention |
|------|--------------|-----------|-----------|
| PostgreSQL | pg_dump to MinIO + WAL archiving | Daily dump + continuous WAL | 30 days |
| Qdrant | Qdrant snapshot API to MinIO | Daily | 14 days |
| MinIO (artifacts) | MinIO replication to secondary | Continuous | Per artifact retention |
| Vault | Vault snapshot to encrypted storage | Hourly | 7 days |
| Redis | RDB dump (non-critical, cache only) | — | No backup needed |

Recovery SLOs: RPO ≤ 1 hour (PostgreSQL, WAL), ≤ 24 hours (Qdrant). RTO ≤ 4 hours.

### 17.5 Minimum Hardware Requirements

| Profile | CPU | RAM | Disk | GPU |
|---------|-----|-----|------|-----|
| Development | 4 cores | 8 GB | 100 GB SSD | Not required |
| Small team (≤10 users) | 8 cores | 32 GB | 500 GB SSD | Optional |
| Production (≤100 users) | 16 cores | 64 GB | 2 TB NVMe | Optional |
| With local LLM (Ollama) | 16+ cores | 64 GB+ | 2 TB NVMe | 24 GB VRAM min |

---

## 18. Technology Stack

| Layer | Technology | Version | Rationale |
|-------|-----------|---------|-----------|
| Frontend | Next.js | 15 (App Router) | SSR, streaming, bilingual |
| UI Components | shadcn/ui + Tailwind CSS | latest | Accessible, composable |
| Server state | TanStack Query | v5 | Cache, pagination, SSE integration |
| Client state | Zustand | v4 | Lightweight, no boilerplate |
| i18n | next-intl | v3 | Native App Router support |
| API | FastAPI | 0.115+ | Async, OpenAPI auto-docs, Pydantic v2 |
| Python | Python | 3.12 | Latest stable, improved asyncio |
| Task Queue | Celery | 5.x | Battle-tested, Redis broker support |
| Queue Broker | Redis | 7.x | Fast, reliable, DB0 for Celery |
| Orchestrator | LangGraph | 0.2+ | Stateful agent graph, HITL, checkpointing |
| LLM Interface | LangChain | 0.3+ | `BaseChatModel` abstraction |
| LLM Providers | Claude (default), GPT-4o, Groq, DeepSeek, Ollama | — | Pluggable via config |
| Sandbox Runtime | Kata Containers | 3.x | Hardware VM isolation, K3s-compatible |
| Headless Browser | Playwright | 1.45+ | Reliable async automation |
| Database | PostgreSQL | 16 | Relational + JSONB + full-text search |
| Connection Pool | PgBouncer | 1.22+ | Transaction-mode pooling for LangGraph |
| Short-term cache | Redis | 7.x | DB1 for memory cache (separate from broker) |
| Vector Store | Qdrant | 1.10+ | Purpose-built vector DB, hybrid search |
| Embeddings | Voyage AI `voyage-multilingual-2` | — | Native EN+FR, 1024-dim vectors |
| Document parsing | Docling + LibreOffice | latest | Multi-format, open-source |
| File Storage | MinIO | latest | S3-compatible, on-premise, presigned URLs |
| Schema migrations | Alembic | 1.13+ | SQL migrations with Python |
| LLM Tracing | Langfuse | 2.x | LangChain callback integration |
| Metrics | Prometheus | 2.x | Standard time-series |
| Dashboards | Grafana | 10.x | Metrics + Loki logs unified |
| Log aggregation | Loki | 2.x | Cost-effective, Grafana native |
| Structured logging | structlog | 24+ | JSON logs, request context |
| Secrets | HashiCorp Vault | 1.15+ | Dynamic secrets, audit log |
| Deployment (prod) | K3s + Helm | K3s 1.29+ | Lightweight Kubernetes |
| Deployment (dev) | Docker Compose | v2 | Local dev environment |
| Language detection | lingua | 2.x | Replaces `langdetect`, higher accuracy |

---

## 19. Configuration Reference

```env
# ─── LLM ───────────────────────────────────────────────────────
AGENTIS_LLM_PROVIDER=anthropic        # anthropic|openai|mistral|groq|deepseek|ollama
AGENTIS_LLM_MODEL=claude-sonnet-4-5-20251022
AGENTIS_LLM_API_KEY=<secret>
AGENTIS_LLM_BASE_URL=                 # For Ollama: http://ollama:11434
AGENTIS_CONTEXT_BUDGET=0.8            # Fraction of model context window before summarization
AGENTIS_MEMORY_INJECTION_TOKENS=2000  # Max tokens of long-term memory per THINK call
AGENTIS_TOOL_OUTPUT_MAX_TOKENS=8000   # Max tokens per tool output before truncation

# ─── TOKEN BUDGETS ─────────────────────────────────────────────
AGENTIS_TOKEN_BUDGET_PER_TASK=100000
AGENTIS_TOKEN_BUDGET_USER_MONTHLY=2000000

# ─── DATABASE ──────────────────────────────────────────────────
AGENTIS_DATABASE_URL=postgresql://agentis:pass@pgbouncer:5432/agentis
AGENTIS_POSTGRES_DIRECT_URL=postgresql://agentis:pass@postgres:5432/agentis  # For Alembic migrations

# ─── REDIS ─────────────────────────────────────────────────────
AGENTIS_REDIS_BROKER_URL=redis://redis:6379/0   # Celery broker + result backend
AGENTIS_REDIS_CACHE_URL=redis://redis:6379/1    # Short-term memory cache

# ─── QDRANT ────────────────────────────────────────────────────
AGENTIS_QDRANT_URL=http://qdrant:6333
AGENTIS_QDRANT_COLLECTION=agentis_memory

# ─── EMBEDDINGS ────────────────────────────────────────────────
AGENTIS_VOYAGE_API_KEY=<secret>       # Voyage AI API key
AGENTIS_VOYAGE_BASE_URL=              # Set for self-hosted endpoint (Phase 3)

# ─── STORAGE ───────────────────────────────────────────────────
AGENTIS_STORAGE_BACKEND=local         # local|minio
AGENTIS_STORAGE_PATH=/var/agentis/files
AGENTIS_MINIO_ENDPOINT=minio:9000
AGENTIS_MINIO_ACCESS_KEY=<secret>
AGENTIS_MINIO_SECRET_KEY=<secret>
AGENTIS_MINIO_BUCKET=agentis-artifacts
AGENTIS_ARTIFACT_RETENTION_DAYS=90

# ─── SEARCH ────────────────────────────────────────────────────
AGENTIS_SEARCH_BACKEND=brave          # brave|searxng|tavily
AGENTIS_BRAVE_API_KEY=<secret>
AGENTIS_SEARXNG_URL=http://searxng:8080
AGENTIS_TAVILY_API_KEY=<secret>

# ─── SANDBOX ───────────────────────────────────────────────────
AGENTIS_SANDBOX_RUNTIME=kata          # kata|gvisor|docker (dev)
AGENTIS_SANDBOX_IMAGE=agentis-sandbox:latest
AGENTIS_SANDBOX_MAX_CONCURRENT=10
AGENTIS_SANDBOX_WARM_POOL_SIZE=2
AGENTIS_SANDBOX_TIMEOUT_SECONDS=1800
AGENTIS_EGRESS_PROXY_URL=http://squid.agentis-system.svc.cluster.local:3128

# ─── AUTH ──────────────────────────────────────────────────────
AGENTIS_JWT_PRIVATE_KEY_PATH=/secrets/jwt/private.pem
AGENTIS_JWT_PUBLIC_KEY_PATH=/secrets/jwt/public.pem
AGENTIS_JWT_ACCESS_TTL=3600           # seconds
AGENTIS_JWT_REFRESH_TTL=2592000       # 30 days in seconds
AGENTIS_VAULT_ADDR=http://vault:8200
AGENTIS_VAULT_TOKEN=<secret>

# ─── RATE LIMITING ─────────────────────────────────────────────
AGENTIS_RATE_LIMIT_TASK_HOUR=60
AGENTIS_RATE_LIMIT_API_HOUR=1000

# ─── AGENT BEHAVIOR ────────────────────────────────────────────
AGENTIS_DEFAULT_MAX_ITERATIONS=30
AGENTIS_MAX_ITERATIONS_CAP=50
AGENTIS_HITL_CONFIDENCE_THRESHOLD=0.3
AGENTIS_HITL_TIMEOUT_SECONDS=3600
AGENTIS_WORKER_CONCURRENCY=4

# ─── I18N ──────────────────────────────────────────────────────
AGENTIS_DEFAULT_LANGUAGE=fr           # fr|en

# ─── OBSERVABILITY ─────────────────────────────────────────────
AGENTIS_LANGFUSE_HOST=http://langfuse:3000
AGENTIS_LANGFUSE_PUBLIC_KEY=<key>
AGENTIS_LANGFUSE_SECRET_KEY=<key>
AGENTIS_LOG_LEVEL=INFO                # DEBUG|INFO|WARNING|ERROR
```

---

## 20. Development Roadmap

### Phase 1 — Core Platform (Months 1–3)

**Goal:** Working MVP with the full agent loop, 4 core tools, sandbox, streaming UI, and auth.

- [x] LangGraph orchestrator with ReAct loop (Plan/Think/Act/Observe/Reflect/Report) — phase-1c
- [x] PostgresSaver checkpointing — phase-1c
- [x] Tools: `browser` (sandbox RPC), `code_executor`, `web_search`, `file_system` — phase-1b
- [x] Kata Container sandbox with JSON-RPC tool server — phase-1b
- [x] Squid egress proxy with static domain allowlist — phase-1b
- [x] Next.js 15 UI: task submission, SSE live trace, task history — phase-1d
- [x] FastAPI gateway: JWT auth, API key auth, rate limiting — phase-1a
- [x] PostgreSQL schema (all tables from Section 14, indexes included) — phase-1a
- [x] Alembic migration setup — phase-1a
- [x] PgBouncer for connection pooling — phase-1a
- [x] Celery task queue with Redis broker — phase-1c
- [x] Short-term memory (Redis DB1) — phase-1c
- [x] Docker Compose dev environment (all services) — phase-1a/1b/1c
- [x] English + French UI (next-intl) and agent prompts — phase-1d (agent prompts ✓ phase-1c)
- [x] Langfuse integration — phase-1c
- [x] Structured logging (structlog → Loki) — phase-1a
- [x] Context window management (summarization) — phase-1c
- [x] Token budget per task — phase-1c

### Phase 2 — Production Hardening (Months 4–5)

- [ ] `doc_parser` and `http_caller` tools
- [ ] Long-term memory with Qdrant (hybrid search)
- [ ] Memory maintenance Celery beat jobs
- [ ] HITL WebSocket endpoint and UI
- [ ] K3s Helm chart with Kata Container RuntimeClass
- [ ] Audit log (append-only, admin query UI)
- [ ] Admin dashboard (users, tools, LLM config, usage metrics)
- [ ] Prometheus + Grafana + Loki production stack
- [ ] Organization model (data model only, no UI yet)
- [ ] Webhook notifications with HMAC signatures
- [ ] File upload for task inputs
- [ ] Artifact signed download URLs (MinIO presigned)
- [ ] Artifact retention cleanup job
- [ ] Monthly token usage reset job
- [ ] Backup automation (pg_dump, Qdrant snapshots)
- [ ] OIDC/SSO integration

### Phase 3 — Advanced Features (Months 6–9)

- [ ] MCP server tool auto-discovery
- [ ] `email` and `calendar` tools (operator-enabled)
- [ ] OpenAPI spec tool auto-generator
- [ ] Organization management UI (admin)
- [ ] Per-org LLM provider override
- [ ] Per-org tool restrictions and token budgets
- [ ] Multi-LLM provider switching via admin UI
- [ ] Task templates library
- [ ] Voyage AI self-hosted embedding option
- [ ] Usage billing / quota management (per-org)
- [ ] ClamAV file scanning for uploads

### Phase 4 — Multi-Agent Collaboration (Months 10+)

- [ ] Meta-orchestrator (Supervisor Agent)
- [ ] Specialized agent roles (research, analysis, writer, etc.)
- [ ] Inter-agent message bus (Redis pub/sub)
- [ ] Multi-agent task view (N parallel traces)
- [ ] Fine-tuned open-source LLM for agent reasoning
- [ ] Voice interface (Whisper ASR + TTS)
- [ ] Agent marketplace (community tool plugins)

---

*Document version: 2.0.0 — Created: 2026-05-29*
*Prepared by: Claude Code (AI Architecture Review) for YULCOM Technologies*
*Status: Ready for team review*
