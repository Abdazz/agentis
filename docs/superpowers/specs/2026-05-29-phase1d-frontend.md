# Phase 1D — Frontend Design Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Next.js 15 frontend for Agentis — task submission, SSE live trace, task history, auth pages, settings, and EN/FR i18n — as an independent git repo physically nested inside the parent `agentis/` repo.

---

## 1. Repository Structure

The frontend lives at `agentis/frontend/` as an **independent git repository**. The parent repo (`agentis/`) gitignores both `backend/` and `frontend/`. The three repos are:

| Repo | Physical path | Purpose |
|------|--------------|---------|
| `agentis` | `~/…/agentis/` | Parent: docker-compose, infra, nginx, K8s configs |
| `agentis-backend` | `~/…/agentis/backend/` | FastAPI backend (Phases 1A–1C) |
| `agentis-frontend` | `~/…/agentis/frontend/` | Next.js 15 frontend (Phase 1D) |

**Parent `.gitignore` additions:**
```
backend/
frontend/
```

---

## 2. Technology Stack

| Concern | Choice | Version |
|---------|--------|---------|
| Framework | Next.js (App Router) | 15 |
| UI components | shadcn/ui + Tailwind CSS | latest |
| Themes | next-themes | latest |
| Server state | TanStack Query | v5 |
| Client state | Zustand | latest |
| i18n | next-intl | latest |
| Forms | React Hook Form + Zod | latest |
| HTTP client | Native `fetch` + custom wrapper | — |
| SSE | Native `EventSource` + custom wrapper | — |
| Tests | Vitest + React Testing Library | latest |

---

## 3. Architecture Decision: Direct API Calls

The browser's Client Components call the FastAPI backend directly (`NEXT_PUBLIC_API_URL`). No BFF proxy layer. Server Components fetch from FastAPI server-side (Node.js → FastAPI) for initial page data only.

| Operation | Caller | Method |
|-----------|--------|--------|
| Task list initial load | Server Component (Node.js) | Server fetch |
| Task submission `POST /api/v1/tasks` | Client Component | Browser fetch |
| SSE stream `/api/v1/tasks/{id}/stream` | Client Component | Browser EventSource |
| Auth refresh `POST /api/v1/auth/refresh` | Client Component | Browser fetch (interceptor) |
| Settings `PATCH /api/v1/auth/users/me` | Client Component | Browser fetch |

---

## 4. File Structure

```
frontend/
├── app/
│   └── [locale]/
│       ├── layout.tsx              # Root layout: ThemeProvider, QueryProvider, AuthInitializer
│       ├── page.tsx                # / — Centered Hero task submission
│       ├── login/page.tsx
│       ├── register/page.tsx
│       ├── tasks/
│       │   ├── page.tsx            # /tasks — task history (Server Component)
│       │   └── [id]/page.tsx       # /tasks/[id] — live trace
│       └── settings/page.tsx
├── components/
│   ├── ui/                         # shadcn/ui generated components
│   ├── task-form.tsx               # Goal textarea + file upload + submit
│   ├── task-feed.tsx               # Terminal Feed SSE display
│   ├── task-list.tsx               # Paginated task history
│   ├── nav.tsx                     # Top navbar: logo, links, locale switcher, theme switcher
│   └── theme-switcher.tsx          # 3-theme selector
├── lib/
│   ├── api.ts                      # HTTP client: fetch wrapper + 401 → refresh interceptor
│   ├── auth.ts                     # Zustand store: access_token (memory only)
│   └── sse.ts                      # EventSource wrapper: backoff, Last-Event-ID, cleanup
├── messages/
│   ├── fr.json                     # French translations (default)
│   └── en.json                     # English translations
├── middleware.ts                   # next-intl locale detection + redirect
├── next.config.ts
├── tailwind.config.ts
└── Dockerfile
```

---

## 5. Authentication Flow

Follows spec §9.6 exactly:

1. `POST /api/v1/auth/login` → FastAPI sets `httpOnly SameSite=Strict` cookie (`refresh_token`) + returns `access_token` in body
2. `access_token` stored in Zustand **memory only** — never `localStorage`, never a cookie
3. All API requests: `Authorization: Bearer {access_token}`
4. On 401 response: `lib/api.ts` interceptor calls `POST /api/v1/auth/refresh` (cookie sent automatically) → new `access_token` → original request retried transparently
5. On page reload: Zustand is empty → root layout `AuthInitializer` component calls `POST /api/v1/auth/refresh` on mount → restores access token
6. Logout: `POST /api/v1/auth/logout` → cookie cleared by server → Zustand cleared → redirect to `/login`

---

## 6. Theme System

Three themes implemented as CSS custom property sets on `<html>`. `next-themes` manages persistence in `localStorage` and SSR hydration.

| Theme | HTML class | Primary color | Default |
|-------|-----------|---------------|---------|
| Light Clean | `theme-light` | Blue `#2563eb` | ✓ |
| Dark Professional | `theme-dark-pro` | Indigo `#6366f1` | |
| Dark Accent | `theme-dark-accent` | Orange `#f97316` | |

`ThemeSwitcher` component appears in the navbar and in `/settings`. Tailwind CSS variables (`--color-primary`, `--color-background`, etc.) drive all component colors — no hardcoded color classes in components.

---

## 7. i18n (next-intl)

- **Default locale:** `fr` (matches `AGENTIS_DEFAULT_LANGUAGE=fr`)
- **URL pattern:** `/fr/…` and `/en/…`
- Middleware redirects `/` → `/fr/` automatically
- Locale switcher in navbar; preference saved to backend via `PATCH /api/v1/auth/users/me` on change
- System prompts and API responses remain in English — translation is a frontend concern only

---

## 8. Page Designs

### 8.1 `/` — Centered Hero

- Textarea centered vertically on the page, auto-resize as user types
- File attachment button: type whitelist, 50 MB/file max, 5 files max, validated before submit
- "Lancer" button → `POST /api/v1/tasks` → redirect to `/tasks/{id}` on success
- Below the input: 4 most recent tasks (Server Component fetch, `GET /api/v1/tasks?limit=4`)
- Unauthenticated users are redirected to `/login`

### 8.2 `/tasks` — Task History

- First page rendered via Server Component (fast initial load)
- Client-side filters: status, date range
- Infinite scroll via TanStack Query `useInfiniteQuery` (cursor pagination)
- Each row: task title, status badge, creation date, duration — click → `/tasks/{id}`

### 8.3 `/tasks/[id]` — Live Trace (Terminal Feed)

**Layout:**
- **Header:** task title, status badge, elapsed time, "Annuler" button (calls `DELETE /api/v1/tasks/{id}`)
- **Feed:** chronological SSE event lines, color-coded badges by type:

| Event type | Badge color | Label |
|-----------|-------------|-------|
| `plan_created` / `plan_updated` | Blue | PLAN |
| `think` | Purple | THINK |
| `tool_call` | Amber | TOOL |
| `tool_result` | Green | RESULT |
| `context_summarized` | Gray | SUMMARY |
| `task_completed` | Green | DONE |
| `task_failed` | Red | ERROR |

- Auto-scroll to bottom; paused when user scrolls up; resumes on user-triggered scroll-to-bottom
- **Footer:** confidence score bar from last `plan_updated` event

**SSE behavior (`lib/sse.ts`):**
- `EventSource` with `withCredentials: true`
- Tracks last received `id` → sent as `Last-Event-ID` on reconnect
- Exponential backoff: 1s → 2s → 4s → 8s → 30s cap
- Closes cleanly on `task_completed` or `task_failed`
- For a completed task (direct navigation): fetches `GET /api/v1/tasks/{id}/stream?replay=true` — same component, stream ends immediately

### 8.4 `/settings`

Sections:
- **Langue:** EN / FR radio (saves via `PATCH /users/me`, reloads locale)
- **Thème:** 3-theme selector (saves to `localStorage` via next-themes)
- **Clés API:** read/create/revoke personal API keys (`GET|POST|DELETE /api/v1/auth/api-keys`)
- **Usage tokens:** read-only usage stats (`GET /api/v1/auth/users/me`)

Form: React Hook Form + Zod validation, `PATCH /api/v1/auth/users/me` on save.

---

## 9. Docker Integration

New `ui` service added to the parent `docker-compose.yml`:

```yaml
ui:
  build: ./frontend
  ports:
    - "3000:3000"
  environment:
    NEXT_PUBLIC_API_URL: http://localhost:8000
    NEXT_PUBLIC_DEFAULT_LOCALE: fr
  depends_on:
    - api
```

The `frontend/Dockerfile` uses the official Next.js multi-stage pattern: `deps` → `builder` → `runner` (Node.js Alpine, non-root user).

**Environment variables (frontend):**

```env
NEXT_PUBLIC_API_URL=http://localhost:8000   # FastAPI base URL
NEXT_PUBLIC_DEFAULT_LOCALE=fr
```

No secrets in frontend environment variables — all sensitive config remains in FastAPI.

---

## 10. Testing Strategy

| Type | Tool | Scope |
|------|------|-------|
| Unit | Vitest | `lib/api.ts` (401 interceptor, refresh retry), `lib/sse.ts` (backoff, Last-Event-ID, cleanup) |
| Component | React Testing Library | `TaskFeed` (SSE event rendering with mocked stream), `TaskForm` (Zod validation, file constraints) |
| E2E (optional Phase 1D) | Playwright | Login → submit task → see live trace |

E2E tests are optional in Phase 1D (require full backend stack). Unit and component tests are required.

---

## 11. Backend Endpoints Required (not yet implemented)

The following endpoints must be added to the FastAPI backend (`backend/app/routers/auth.py`) as part of Phase 1D setup — the frontend `/settings` page depends on them:

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/auth/users/me` | Return current user profile (name, email, language) |
| `PATCH /api/v1/auth/users/me` | Update user profile (name, language preference) |
| `GET /api/v1/auth/users/me/usage` | Return current month token usage (read-only) |

These are small additions to the existing auth router.

---

## 12. Out of Scope (Phase 2+)

- `/admin/*` routes (dashboard, users, audit, tools, config)
- HITL WebSocket (`/tasks/[id]` input form)
- Organization management UI
- Webhook notifications UI
- MinIO presigned URL uploads
