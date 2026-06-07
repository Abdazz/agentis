# Phase 2 — Production Hardening : Design Spec

**Version:** 1.0.0  
**Date:** 2026-06-07  
**Scope:** 13 items répartis en 4 sous-phases séquentielles (OIDC/SSO et K3s/Helm différés en Phase 3)  
**Approche:** Feature-led — chaque sous-phase livre de la valeur testable dans le navigateur

---

## Décisions de périmètre

| Item | Décision |
|------|----------|
| OIDC/SSO | ❌ Différé Phase 3 |
| K3s Helm chart | ❌ Différé Phase 3 |
| MinIO en dev | ✅ Ajouté au docker-compose |
| Tests navigateur | Manuel par Claude (skill `verify`) après chaque sous-phase |
| UI HITL | Panel inline bas du Terminal Feed (Option A) |
| Admin layout | Sidebar dédiée avec layout séparé (Option A) |

---

## Architecture globale

### Services ajoutés au docker-compose

| Service | Port | Ajouté en |
|---------|------|-----------|
| Qdrant | `:6333` (REST) / `:6334` (gRPC) | 2A |
| MinIO | `:9000` (API) / `:9001` (console) | 2B |
| Prometheus | `:9090` | 2C |
| Grafana | `:3002` | 2C |
| Loki | `:3100` | 2C |

### Nouveaux composants backend

- Router `/api/v1/admin/*` — audit log, users, stats, orgs, backups
- WebSocket endpoint `WSS /ws/tasks/{id}` — HITL bidirectionnel
- Celery Beat activé — 6 jobs périodiques nouveaux
- Module `app/memory/long_term.py` — Qdrant + Voyage AI
- Module `app/storage/` — abstraction MinIO/local FS

### Nouveaux composants frontend

- Layout `app/[locale]/admin/layout.tsx` avec sidebar dédiée
- Pages : `/admin`, `/admin/users`, `/admin/audit`, `/admin/organizations`
- Extension `components/task-feed.tsx` — panel HITL inline
- Composant `components/hitl-panel.tsx` — WebSocket HITL

---

## Phase 2A — Outils + Mémoire long-terme

### Outil `doc_parser`

Suit le pattern RPC existant (client JSON-RPC dans l'orchestrateur, exécution Docling dans le sandbox).

**Interface RPC :**
```
doc_parser.parse(file_path: str) → {text, metadata, truncated}
doc_parser.extract_tables(file_path: str) → {tables: [{headers, rows}]}
doc_parser.convert(file_path: str, target_format: str) → {output_path}
```

**Implémentation :**
- `backend/app/tools/doc_parser.py` — RPC client (comme `browser.py`)
- `sandbox/tools/doc_parser_server.py` — exécution Docling réelle
- Types supportés : PDF, DOCX, XLSX, HTML, Markdown, texte brut

### Outil `http_caller`

**Interface RPC :**
```
http_caller.request(method, url, headers, body, timeout) → {status, body, headers, duration_ms}
```

**Règles HITL :**
- Requêtes GET : libres
- Non-GET vers domaine hors whitelist : flag `pending_hitl_approval` dans AgentState → nœud REFLECT transfère vers HITL
- Whitelist configurable via `AGENTIS_HTTP_CALLER_SAFE_DOMAINS` (CSV)

**Implémentation :**
- `backend/app/tools/http_caller.py` — RPC client
- `sandbox/tools/http_caller_server.py` — httpx async dans le sandbox

### Mémoire long-terme (Qdrant)

**Collection Qdrant :** `agentis_memory`
- Vecteurs : 1024-dim, Voyage AI `voyage-multilingual-2`
- Recherche : hybrid dense + sparse (BM25)
- Payload : `{id, user_id, org_id, content, summary, source_task_id, importance, tags, language, created_at}`

**Table PostgreSQL `memory_entries` :** point_id (Qdrant), user_id, task_id, created_at, importance

**Flux de mémorisation :**
1. Nœud REPORT : extrait les faits clés de la session via LLM
2. Embeddings via Voyage AI API
3. Upsert dans Qdrant + insert `memory_entries`

**Flux de récupération :**
1. Nœud REFLECT (avant REPORT) : embedding du contexte courant
2. Hybrid search Qdrant top-5
3. Injection dans le contexte LLM comme `SystemMessage`

**Initialisation :** check idempotent au démarrage de l'API — crée la collection si absente.

**Module :** `backend/app/memory/long_term.py`

### Celery Beat — jobs mémoire

| Job | Fréquence | Action |
|-----|-----------|--------|
| `decay_memory_importance` | Toutes les 24h | `importance *= 0.95` pour chaque entrée non accédée |
| `prune_memory` | Toutes les 24h | Supprime Qdrant + PostgreSQL pour `importance < 0.05` |

### Tests manuels 2A

1. Uploader un PDF via `task-form` → vérifier que `doc_parser` l'analyse (logs SSE)
2. Soumettre une 2e tâche similaire → vérifier injection mémoire dans les logs THINK
3. Appeler un endpoint externe en GET → pas de HITL
4. Appeler un endpoint externe en POST → panel HITL s'affiche (testé en 2B)

---

## Phase 2B — HITL + Fichiers + Artefacts

### WebSocket HITL

**Endpoint :** `WSS /ws/tasks/{id}` — FastAPI WebSocket router

**Protocole :**
```json
// Serveur → Client
{"type": "hitl_request", "question": "...", "options": ["Confirmer", "Annuler"], "timeout_seconds": 3600}

// Client → Serveur
{"type": "hitl_response", "choice": "Confirmer"}
```

**Flux :**
1. Orchestrateur publie `hitl:{task_id}` sur Redis pub/sub avec question + options
2. WebSocket handler souscrit et forward au client connecté
3. Client répond → handler publie `hitl_response:{task_id}` sur Redis
4. Orchestrateur (bloqué sur `await redis.subscribe`) reçoit la réponse et continue

**Buffering :** si aucun client connecté → event buffé en Redis (TTL 10 min) → cancel automatique après timeout.

**UI (Frontend) :** 

- `components/hitl-panel.tsx` — panel inline au bas du Terminal Feed
- S'affiche quand le status tâche passe à `waiting_for_input`
- Connexion WebSocket dans `useEffect` de `TaskFeed`
- Layout : question de l'agent + boutons (options) + indicateur de timeout

### File Upload

**Endpoint :** `POST /api/v1/tasks` étendu pour `multipart/form-data`

**Validation :**
- Max 5 fichiers, max 50 MB par fichier
- Validation magic bytes (python-magic) + extension
- Types : PDF, DOCX, XLSX, TXT, MD, JSON, CSV

**Stockage :** MinIO bucket `agentis-uploads/{user_id}/{task_id}/{filename}`

**Transmission au sandbox :** paths MinIO passés dans les paramètres task, le sandbox télécharge via SDK MinIO interne.

### Artefacts + MinIO

**Endpoints :**
- `GET /api/v1/tasks/{id}/artifacts` — liste les artefacts d'une tâche
- `GET /api/v1/tasks/{id}/artifacts/{artifact_id}/download` — génère presigned URL MinIO (1h) + redirect 302

**MinIO buckets :**
- `agentis-uploads` — fichiers d'entrée task
- `agentis-artifacts` — fichiers produits par l'agent
- `agentis-backups` — backups (Phase 2D)

**Module :** `backend/app/storage/minio_client.py` + `backend/app/storage/local_client.py` (interface commune, switch via `AGENTIS_STORAGE_BACKEND`)

### Celery Beat — artifact cleanup

| Job | Fréquence | Action |
|-----|-----------|--------|
| `cleanup_artifacts` | Toutes les 24h | Supprime MinIO + marque `deleted` les artifacts > 30 jours |

### Tests manuels 2B

1. Soumettre une tâche avec fichier PDF → voir le fichier dans MinIO console `:9001`
2. Voir les artefacts produits listés dans `/tasks/[id]`
3. Cliquer "Télécharger" → URL presigned MinIO → fichier téléchargé
4. Déclencher action destructive (http_caller POST) → panel HITL inline visible
5. Cliquer "Confirmer" → l'agent reprend le SSE feed
6. Cliquer "Annuler" → tâche annulée, status mis à jour

---

## Phase 2C — Admin + Observabilité

### Admin Dashboard (Frontend)

**Layout :** `app/[locale]/admin/layout.tsx` — sidebar fixe, séparé du layout utilisateur normal.

**Route guard :** middleware vérifie `role ∈ {admin, operator}` → sinon redirect `/`.

**Lien d'accès :** dans `Nav` — lien "Admin" conditionnel visible uniquement pour admin/operator.

**Pages :**

| Page | Route | Contenu |
|------|-------|---------|
| Dashboard | `/admin` | Métriques : tâches/jour (7j), utilisateurs actifs, tokens ce mois, taux d'échec |
| Utilisateurs | `/admin/users` | Tableau paginé, actions : désactiver, modifier role |
| Audit Log | `/admin/audit` | Filtres : user_id, event_type, from/to dates |
| Organisations | `/admin/organizations` | Phase 2D — table + create form |

### Audit Log API

**Endpoint :** `GET /api/v1/admin/audit-log`  
**Query params :** `user_id`, `event_type`, `from`, `to`, `limit` (max 100), `cursor`  
**Append-only :** aucune route DELETE/PATCH sur audit_log  
**Émission :** fonction utilitaire `audit.record(event_type, user_id, data, request)` appelée depuis middleware FastAPI et handlers clés (login, logout, task create, key create/revoke, user disable)

### Admin API

```
GET  /api/v1/admin/stats              — métriques globales
GET  /api/v1/admin/users              — liste utilisateurs (paginé)
PATCH /api/v1/admin/users/{id}        — modifier role / désactiver
GET  /api/v1/admin/audit-log          — audit log filtré
```

### Prometheus + Grafana + Loki

**Prometheus `:9090` :**
- `prometheus-fastapi-instrumentator` — métriques HTTP (latence, status codes, RPS)
- `celery-exporter` — métriques worker (tasks/s, failures, queue depth)

**Grafana `:3002` :**
- Provisioning via `grafana/provisioning/datasources/` (Prometheus + Loki auto-configurés)
- Dashboard préconfigurés : API Overview, Agent Tasks, Celery Workers

**Loki `:3100` :**
- `python-logging-loki` — handler structlog → Loki
- Labels : `service`, `level`, `task_id`, `user_id`

### Celery Beat — token reset

| Job | Fréquence | Action |
|-----|-----------|--------|
| `reset_monthly_tokens` | 1er du mois, 00:00 UTC | `UPDATE users SET token_used_this_month = 0` |

### Tests manuels 2C

1. Naviguer vers `/admin` → vérifier les 4 métriques
2. `/admin/users` → désactiver un utilisateur → tenter login → vérifier blocage
3. `/admin/audit` → filtrer par event_type `login` → voir les entrées
4. Ouvrir Grafana `:3002` → vérifier datasource Prometheus active → dashboard API visible

---

## Phase 2D — Organisation + Webhooks + Backup

### Organisation Model

**Tables existantes :** `organizations`, `organization_memberships` (créées Phase 1A, vides)

**Nouveaux endpoints :**
```
GET    /api/v1/admin/organizations              — liste
POST   /api/v1/admin/organizations              — créer
PATCH  /api/v1/admin/organizations/{id}         — modifier (nom, llm_provider_override, tool_policies)
POST   /api/v1/admin/organizations/{id}/members — ajouter membre (user_id, role)
DELETE /api/v1/admin/organizations/{id}/members/{user_id}
```

**Org active :** header `X-Organization-ID` ou champ `active_organization_id` dans settings utilisateur.

**Page frontend :** `/admin/organizations` — table des orgs + modal création + gestion membres.

### Webhooks HMAC

**Configuration :** dans les settings utilisateur — URL + secret. Stockés dans table `user_webhooks` (nouvelle migration Alembic : user_id, url, secret_encrypted, status: healthy/unhealthy, failure_count). Le secret est chiffré via Fernet (`cryptography` lib) avec `AGENTIS_WEBHOOK_SECRET_KEY` — il doit être récupérable en clair pour calculer le HMAC, donc pas hashé comme un mot de passe.

**Déclenchement :** à la complétion ou l'échec d'une tâche ayant `notify_webhook` défini.

**Payload POST :**
```json
{
  "event": "task.completed",
  "task_id": "...",
  "status": "completed",
  "summary": "...",
  "timestamp": "2026-06-07T12:00:00Z"
}
```

**Signature :** header `X-Agentis-Signature: sha256=<HMAC-SHA256(payload_bytes, secret)>`

**Retry :** Celery task `deliver_webhook` — 5 tentatives (10s, 40s, 160s, 640s, 2560s). Après 5 échecs : status `unhealthy`, livraisons suspendues.

**UI settings :** section "Webhook" dans `/settings` — URL, secret (masqué), statut, bouton re-enable.

### Backup Automation

| Job | Fréquence | Action |
|-----|-----------|--------|
| `backup_postgres` | Toutes les 24h | `pg_dump → .sql.gz → MinIO agentis-backups/postgres/YYYY-MM-DD.sql.gz` (rétention 30j) |
| `backup_qdrant` | Toutes les 24h | `POST /collections/agentis_memory/snapshots → téléchargement → MinIO agentis-backups/qdrant/` (rétention 7j) |

**Endpoint admin :** `GET /api/v1/admin/backups` — liste les backups disponibles par date.

**Page admin :** section dans `/admin` dashboard — derniers backups + statut.

### Tests manuels 2D

1. Créer une org → ajouter un utilisateur comme membre → vérifier que l'org apparaît dans ses settings
2. Configurer un webhook URL (ex: `https://webhook.site/...`) → lancer une tâche → vérifier réception avec signature HMAC
3. Vérifier les backups dans MinIO console `:9001` (bucket `agentis-backups`)
4. `GET /api/v1/admin/backups` → liste les fichiers de backup

---

## Migrations Alembic requises

| Migration | Tables modifiées | Déclenchée par |
|-----------|-----------------|----------------|
| Phase 2A | Aucune (Qdrant externe) — table `memory_entries` nouvelle | 2A |
| Phase 2B | Aucune (MinIO externe) | — |
| Phase 2D | Table `user_webhooks` nouvelle, colonne `active_organization_id` dans `users` | 2D |

Toutes les migrations sont backward-compatible (nouvelles tables ou colonnes nullable).

---

## Résumé des variables d'environnement ajoutées

```env
# Qdrant
AGENTIS_QDRANT_URL=http://qdrant:6333
AGENTIS_QDRANT_COLLECTION=agentis_memory

# Voyage AI (embeddings)
AGENTIS_VOYAGE_API_KEY=<secret>
AGENTIS_VOYAGE_MODEL=voyage-multilingual-2

# MinIO
AGENTIS_MINIO_ENDPOINT=minio:9000
AGENTIS_MINIO_ACCESS_KEY=agentis
AGENTIS_MINIO_SECRET_KEY=agentis123
AGENTIS_MINIO_USE_SSL=false

# HTTP Caller whitelist
AGENTIS_HTTP_CALLER_SAFE_DOMAINS=api.github.com,api.openai.com

# Prometheus
AGENTIS_PROMETHEUS_ENABLED=true

# Loki
AGENTIS_LOKI_URL=http://loki:3100

# Webhooks
AGENTIS_WEBHOOK_SECRET_KEY=<secret-pour-HMAC>
```

---

## Dépendances Python ajoutées

```
# Phase 2A
qdrant-client>=1.9
voyageai>=0.2
docling>=2.0        # dans sandbox

# Phase 2B
python-magic>=0.4
minio>=7.2

# Phase 2C
prometheus-fastapi-instrumentator>=6.1
python-loki-logger>=1.0     # structlog → Loki via HTTP

# Phase 2D
celery[redis]       # déjà présent — beat scheduler activé
cryptography>=42.0  # Fernet pour chiffrement secret webhook
```

---

## Dépendances frontend ajoutées

```
# Phase 2B
# WebSocket natif navigateur — pas de lib supplémentaire
```

---

## Séquence de tests manuels finaux (post-Phase 2D)

1. `docker compose up` → tous les services healthy
2. Ouvrir `http://localhost:3000` → login
3. Soumettre une tâche avec fichier PDF → voir `doc_parser` dans le SSE feed
4. Soumettre une tâche déclenchant une action non-GET → voir panel HITL inline → confirmer
5. Voir artefact produit → télécharger via presigned URL
6. `/admin` → vérifier métriques en temps réel
7. Grafana `:3002` → dashboard API actif
8. Créer org, ajouter membre, tester webhook HMAC
9. MinIO `:9001` → vérifier buckets uploads + artifacts + backups
