# Phase Final — Remaining Features

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the three remaining spec gaps not yet addressed in any prior session:
1. **Grafana + Loki** provisioning (datasources, dashboards, Loki config) — spec §12 Feature ADMIN-4
2. **`/admin/orgs` page** — Organization management UI — spec §12 Feature ADMIN-6
3. **Admin sidebar i18n** — replace hardcoded strings with `useTranslations` — spec §11 BR-LANG-21

**Context: what is already done** (do NOT re-implement):
- HITL frontend: `HitlPanel.tsx` + `useHitl.ts` — fully implemented
- Per-org LLM override: wired in `backend/app/orchestrator/runner.py` via `build_llm(provider=org_llm_provider, model=org_llm_model)`
- Per-org tool restrictions: enforced in `backend/app/routers/tasks.py`
- Per-org token budgets: enforced in `backend/app/orchestrator/budget.py`
- Voyage AI self-hosted: `long_term.py` reads `settings.voyage_base_url` if set
- Usage quota reset: `backend/app/worker/beat_jobs.py` `reset_monthly_tokens` task
- K3s Helm chart: explicitly out of scope (Docker Compose prod is the deployment target)

**Tech Stack:** Docker Compose v2, Grafana 11, Loki 3, Next.js 15 App Router, next-intl, shadcn/ui, TanStack Query v5, FastAPI

**Deployment target:** Docker Compose on Debian VPS (NOT K3s). All infra changes are `docker-compose.yml` + config files under `infra/`.

---

## Task 1: Loki config file + Grafana provisioning

**Why:** The `docker-compose.yml` references `/etc/loki/local-config.yaml` which doesn't exist → Loki crashes on start. Grafana has no datasource or dashboard provisioning → starts blank.

**Files:**
- Create: `infra/loki/local-config.yaml`
- Create: `infra/grafana/provisioning/datasources/agentis.yaml`
- Create: `infra/grafana/provisioning/dashboards/agentis.yaml`
- Create: `infra/grafana/dashboards/agentis-overview.json`
- Modify: `docker-compose.yml` — mount the new config files into loki + grafana

**Spec metrics to dashboard (from §12 ADMIN-4):**
- `agentis_tasks_total` (counter, labels: status, language)
- `agentis_task_duration_seconds` (histogram, labels: status)
- `agentis_tool_calls_total` (counter, labels: tool, outcome)
- `agentis_llm_tokens_total` (counter, labels: provider, model, direction)
- `agentis_llm_latency_seconds` (histogram, labels: provider, model)
- `agentis_active_sessions` (gauge)
- `agentis_sandbox_containers_active` (gauge, labels: state)
- `agentis_context_summarizations_total` (counter)
- `agentis_hitl_events_total` (counter, labels: resolution)

**Grafana alerts (from §12 ADMIN-4):**
- Task failure rate > 10% over 5 minutes
- Average task duration > 10 minutes
- LLM error rate > 5%
- Sandbox container count > 80% of max_concurrent
- Disk usage > 80%
- p95 LLM latency > 30 seconds

- [ ] **Step 1: Create `infra/loki/local-config.yaml`**

```yaml
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096

common:
  instance_addr: 127.0.0.1
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

query_range:
  results_cache:
    cache:
      embedded_cache:
        enabled: true
        max_size_mb: 100

schema_config:
  configs:
    - from: 2020-10-24
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

ruler:
  alertmanager_url: http://localhost:9093

limits_config:
  allow_structured_metadata: false
```

- [ ] **Step 2: Create `infra/grafana/provisioning/datasources/agentis.yaml`**

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    uid: agentis-prometheus
    editable: false

  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    uid: agentis-loki
    editable: false
    jsonData:
      maxLines: 1000
```

- [ ] **Step 3: Create `infra/grafana/provisioning/dashboards/agentis.yaml`**

```yaml
apiVersion: 1
providers:
  - name: Agentis Dashboards
    type: file
    disableDeletion: true
    updateIntervalSeconds: 60
    options:
      path: /var/lib/grafana/dashboards
```

- [ ] **Step 4: Create `infra/grafana/dashboards/agentis-overview.json`**

Create a minimal but complete Grafana dashboard JSON (uid: `agentis-overview`) with these panels:

**Row 1 — Task Overview (4 stat panels):**
- Tasks today: `increase(agentis_tasks_total[1d])`
- Running now: `agentis_active_sessions`
- Failure rate: `rate(agentis_tasks_total{status="failed"}[5m]) / rate(agentis_tasks_total[5m]) * 100`
- Avg duration: `rate(agentis_task_duration_seconds_sum[10m]) / rate(agentis_task_duration_seconds_count[10m])`

**Row 2 — LLM (2 time-series panels):**
- Token rate by direction: `rate(agentis_llm_tokens_total[5m])` grouped by `direction`
- LLM latency p95: `histogram_quantile(0.95, rate(agentis_llm_latency_seconds_bucket[5m]))`

**Row 3 — Tools + Sandbox (2 time-series panels):**
- Tool calls by tool: `rate(agentis_tool_calls_total[5m])` grouped by `tool`
- Sandbox containers: `agentis_sandbox_containers_active` grouped by `state`

**Row 4 — Logs (1 logs panel):**
- Loki query: `{container="agentis-api"}` showing last 200 lines

Include alert thresholds on relevant panels matching the spec §12 ADMIN-4 thresholds listed above.

Use Grafana JSON model format with `"schemaVersion": 38`. Keep the JSON valid and complete (all panels must have valid `gridPos`, `type`, `targets`, `title` fields).

- [ ] **Step 5: Modify `docker-compose.yml` — mount config files**

In the `loki:` service, add a volume mount:
```yaml
    volumes:
      - ./infra/loki/local-config.yaml:/etc/loki/local-config.yaml:ro
      - loki_data:/loki
```
Also add `loki_data:` to the top-level `volumes:` block.

In the `grafana:` service, add volume mounts:
```yaml
    volumes:
      - grafana_data:/var/lib/grafana
      - ./infra/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./infra/grafana/dashboards:/var/lib/grafana/dashboards:ro
```

- [ ] **Step 6: Smoke-test**

```bash
cd /home/yulcom/web/perso/agentis
docker compose --profile observability up loki grafana -d
sleep 5
curl -s http://localhost:3100/ready  # should return "ready"
curl -s http://localhost:3002/api/health  # should return {"database":"ok"}
```

---

## Task 2: `/admin/orgs` — Organization management page

**Why:** `Organization` model + backend router (`GET/POST /api/v1/organizations`, `PATCH /api/v1/organizations/{id}`) are already implemented. No frontend page exists. Spec §12 Feature ADMIN-6 requires an admin UI to create/manage organizations (name, slug, LLM override, tool restrictions, token budget, max concurrent tasks).

**Backend context:**
- `GET /api/v1/organizations` — lists the current user's orgs
- `POST /api/v1/organizations` — creates an org (body: `{name, slug}`)
- `PATCH /api/v1/organizations/active` — sets user's active org
- Org model fields: `id`, `name`, `slug`, `llm_provider`, `llm_model`, `allowed_tools` (JSON array), `token_budget_monthly`, `max_concurrent_tasks`

**Missing backend:** `GET /api/v1/admin/organizations` (admin list all orgs) and `PATCH /api/v1/admin/organizations/{id}` (admin update org settings). These need to be added to `backend/app/routers/admin.py`.

**Files:**
- Modify: `backend/app/routers/admin.py` — add admin org list + update endpoints
- Modify: `backend/tests/test_routers/test_admin.py` — add tests
- Create: `frontend/app/[locale]/admin/orgs/page.tsx`
- Create: `frontend/hooks/useAdminOrgs.ts`
- Modify: `frontend/components/admin/AdminSidebar.tsx` — add Orgs link
- Modify: `frontend/messages/en.json` + `fr.json` — add `admin.orgs.*` keys

**i18n keys to add:**

```json
"admin": {
  "orgs": {
    "title": "Organizations",
    "subtitle": "Manage organizations, LLM overrides, and token budgets",
    "navLabel": "Organizations",
    "create": "New Organization",
    "name": "Name",
    "slug": "Slug",
    "llmProvider": "LLM Provider",
    "llmModel": "LLM Model",
    "tokenBudget": "Monthly Token Budget",
    "maxConcurrent": "Max Concurrent Tasks",
    "allowedTools": "Allowed Tools",
    "members": "Members",
    "save": "Save",
    "saved": "Saved.",
    "empty": "No organizations yet.",
    "createError": "Failed to create organization.",
    "saveError": "Failed to save changes.",
    "noOverride": "Use global default"
  }
}
```

- [ ] **Step 1: Write failing tests for admin org endpoints**

```python
# Add to backend/tests/test_routers/test_admin.py

@pytest.mark.asyncio
async def test_admin_list_orgs_requires_admin(client: AsyncClient):
    resp = await client.get("/api/v1/admin/organizations")
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_admin_list_orgs(client: AsyncClient, admin_auth_headers: dict, db_session):
    from app.models.org import Organization
    from datetime import datetime, timezone
    org = Organization(name="Test Org", slug="test-org", created_at=datetime.now(timezone.utc),
                       updated_at=datetime.now(timezone.utc))
    db_session.add(org)
    await db_session.commit()
    resp = await client.get("/api/v1/admin/organizations", headers=admin_auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    slugs = [o["slug"] for o in data]
    assert "test-org" in slugs

@pytest.mark.asyncio
async def test_admin_update_org(client: AsyncClient, operator_auth_headers: dict, db_session):
    from app.models.org import Organization
    from datetime import datetime, timezone
    org = Organization(name="Patch Org", slug="patch-org", created_at=datetime.now(timezone.utc),
                       updated_at=datetime.now(timezone.utc))
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    resp = await client.patch(
        f"/api/v1/admin/organizations/{org.id}",
        headers=operator_auth_headers,
        json={"token_budget_monthly": 500_000, "max_concurrent_tasks": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_budget_monthly"] == 500_000
    assert body["max_concurrent_tasks"] == 3
```

- [ ] **Step 2: Run tests (expect failure)**

```bash
cd backend && python3 -m pytest tests/test_routers/test_admin.py::test_admin_list_orgs -v
```

- [ ] **Step 3: Add `GET /admin/organizations` and `PATCH /admin/organizations/{id}` to `backend/app/routers/admin.py`**

Add after existing endpoints:

```python
from app.models.org import Organization as OrgModel
from pydantic import BaseModel as _BaseModel
from typing import Optional as _Optional

class OrgUpdate(_BaseModel):
    name: _Optional[str] = None
    llm_provider: _Optional[str] = None
    llm_model: _Optional[str] = None
    allowed_tools: _Optional[list[str]] = None
    token_budget_monthly: _Optional[int] = None
    max_concurrent_tasks: _Optional[int] = None

@router.get("/organizations")
async def admin_list_organizations(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrgModel).where(OrgModel.deleted_at.is_(None)).order_by(OrgModel.created_at.desc())
    )
    orgs = result.scalars().all()
    return [
        {
            "id": str(o.id), "name": o.name, "slug": o.slug,
            "llm_provider": o.llm_provider, "llm_model": o.llm_model,
            "allowed_tools": o.allowed_tools, "token_budget_monthly": o.token_budget_monthly,
            "max_concurrent_tasks": o.max_concurrent_tasks,
            "created_at": o.created_at.isoformat(),
        }
        for o in orgs
    ]

@router.patch("/organizations/{org_id}")
async def admin_update_organization(
    org_id: UUID,
    body: OrgUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(OrgModel, org_id)
    if org is None or org.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Organization not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    org.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(org)
    return {
        "id": str(org.id), "name": org.name, "slug": org.slug,
        "llm_provider": org.llm_provider, "llm_model": org.llm_model,
        "allowed_tools": org.allowed_tools, "token_budget_monthly": org.token_budget_monthly,
        "max_concurrent_tasks": org.max_concurrent_tasks,
    }
```

- [ ] **Step 4: Run tests (expect pass)**

```bash
cd backend && python3 -m pytest tests/test_routers/test_admin.py -v -k "org"
```

- [ ] **Step 5: Create `frontend/hooks/useAdminOrgs.ts`**

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'

export interface AdminOrg {
  id: string
  name: string
  slug: string
  llm_provider: string | null
  llm_model: string | null
  allowed_tools: string[] | null
  token_budget_monthly: number | null
  max_concurrent_tasks: number
  created_at: string
}

export function useAdminOrgs() {
  return useQuery({
    queryKey: ['admin', 'orgs'],
    queryFn: async () => {
      const r = await apiFetch('/api/v1/admin/organizations')
      if (!r.ok) throw new Error('Failed to fetch organizations')
      return r.json() as Promise<AdminOrg[]>
    },
  })
}

export function useUpdateOrg() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<AdminOrg> & { id: string }) => {
      const r = await apiFetch(`/api/v1/admin/organizations/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      if (!r.ok) throw new Error('Failed to update organization')
      return r.json() as Promise<AdminOrg>
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'orgs'] }),
  })
}

export function useCreateOrg() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (data: { name: string; slug: string }) => {
      const r = await apiFetch('/api/v1/organizations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      if (!r.ok) throw new Error('Failed to create organization')
      return r.json()
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'orgs'] }),
  })
}
```

- [ ] **Step 6: Create `frontend/app/[locale]/admin/orgs/page.tsx`**

Build a client component page that:
1. Lists all organizations in a table (columns: Name, Slug, LLM Provider/Model, Token Budget, Max Concurrent, Actions)
2. Has a "New Organization" button that opens a dialog (name + slug fields)
3. Each row has an "Edit" button that opens an edit dialog (all `OrgUpdate` fields)
4. Edit dialog: provider dropdown (anthropic/openai/mistral/groq/deepseek/ollama + empty="Use global default"), model text input, token budget number input, max concurrent number input
5. Uses `useAdminOrgs`, `useCreateOrg`, `useUpdateOrg` hooks
6. All strings via `useTranslations('admin.orgs')`

Use shadcn/ui `Dialog`, `Table`, `TableRow`, `TableCell`, `Input`, `Button`, `Select` components (all already present in `frontend/components/ui/`).

- [ ] **Step 7: Add Orgs to `AdminSidebar.tsx`**

Add before the Config item:
```typescript
import { Building2 } from 'lucide-react'
// in navItems array:
{ href: '/admin/orgs', label: t('orgs.navLabel'), icon: Building2, operatorOnly: false },
```

- [ ] **Step 8: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

---

## Task 3: Admin sidebar i18n + missing translation keys

**Why:** Spec BR-LANG-21: "All UI labels, error messages, ARIA labels, and help text are fully translated. No untranslated strings ship to production." The current `AdminSidebar.tsx` has hardcoded `'Utilisateurs'`, `'Audit Log'`, `'Tools'`, `'Dashboard'` strings.

**Files:**
- Modify: `frontend/components/admin/AdminSidebar.tsx` — replace all hardcoded labels with `t()`
- Modify: `frontend/messages/en.json` — add `admin.nav.*` keys
- Modify: `frontend/messages/fr.json` — add `admin.nav.*` keys

**i18n keys to add:**

```json
"admin": {
  "nav": {
    "dashboard": "Dashboard",
    "users": "Users",
    "auditLog": "Audit Log",
    "tools": "Tools"
  }
}
```

French:
```json
"admin": {
  "nav": {
    "dashboard": "Tableau de bord",
    "users": "Utilisateurs",
    "auditLog": "Journal d'audit",
    "tools": "Outils"
  }
}
```

- [ ] **Step 1: Add keys to `frontend/messages/en.json` and `frontend/messages/fr.json`**

In the `admin` object, add the `nav` sub-object and the `orgs` sub-object (from Task 2 Step 6) together in a single edit per file.

- [ ] **Step 2: Update `AdminSidebar.tsx` to use translation keys**

Replace hardcoded labels:
```typescript
{ href: '/admin', label: t('nav.dashboard'), icon: LayoutDashboard, operatorOnly: false },
{ href: '/admin/users', label: t('nav.users'), icon: Users, operatorOnly: false },
{ href: '/admin/audit', label: t('nav.auditLog'), icon: ScrollText, operatorOnly: false },
{ href: '/admin/tools', label: t('nav.tools'), icon: Wrench, operatorOnly: false },
{ href: '/admin/orgs', label: t('orgs.navLabel'), icon: Building2, operatorOnly: false },
{ href: '/admin/config', label: t('config.navLabel'), icon: Settings2, operatorOnly: true },
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 4: Commit all three tasks together**

```bash
# In the agentis root repo
git add infra/ docker-compose.yml
git commit -m "feat(observability): Loki config, Grafana datasources + dashboard provisioning"

# In the frontend repo
cd frontend
git add app/ hooks/ components/ messages/
git commit -m "feat(admin): /admin/orgs page, org management endpoints, sidebar i18n"

# In the backend repo
cd ../backend
git add app/routers/admin.py tests/
git commit -m "feat(admin): GET/PATCH /admin/organizations/{id} endpoints"
```

---

## Summary

| Task | Files changed | Spec feature |
|------|--------------|--------------|
| T1: Grafana/Loki | `infra/loki/`, `infra/grafana/`, `docker-compose.yml` | ADMIN-4 |
| T2: `/admin/orgs` | `backend/routers/admin.py`, `frontend/app/admin/orgs/`, `hooks/useAdminOrgs.ts` | ADMIN-6 |
| T3: Sidebar i18n | `AdminSidebar.tsx`, `messages/*.json` | LANG-3 BR-LANG-21 |

After these three tasks, **all spec features are implemented**. No further backend work is required.
