# Agentis

**Plateforme d'agents IA autonomes, auto-hébergée.**

Vous décrivez un objectif en langage naturel. L'agent le découpe en sous-tâches, utilise des outils (navigateur, exécution de code, recherche web, fichiers, e-mail, calendrier…), évalue ses résultats et livre des artefacts structurés. Toute l'exécution a lieu dans un sandbox isolé.

> Statut : les phases 1 à 4 de la roadmap sont implémentées et fusionnées dans `main`. Le suivi détaillé se trouve dans [`docs/agentis_spec.md` §20](docs/agentis_spec.md) et les prochaines étapes dans [`docs/NEXT_STEPS.md`](docs/NEXT_STEPS.md).

---

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Architecture](#architecture)
- [Stack technique](#stack-technique)
- [Structure du dépôt](#structure-du-dépôt)
- [Démarrage rapide (développement)](#démarrage-rapide-développement)
- [Configuration](#configuration)
- [Tests](#tests)
- [Déploiement en production](#déploiement-en-production)
- [Observabilité](#observabilité)
- [Sécurité](#sécurité)
- [Documentation](#documentation)
- [Roadmap](#roadmap)

---

## Fonctionnalités

**Agent**
- Boucle ReAct sur LangGraph : `PLAN → THINK → ACT → OBSERVE → REFLECT → REPORT`, avec un checkpoint PostgreSQL à chaque étape. N'importe quel worker peut reprendre une tâche.
- Score de confiance et **human-in-the-loop** (HITL) par WebSocket quand l'agent hésite ou avant une action sensible (envoi d'e-mail, création d'événement…).
- **Multi-agent** : un superviseur répartit le travail entre des agents spécialisés (recherche, analyse, rédaction…) qui communiquent par un bus Redis pub/sub.
- Gestion du contexte : quand 80 % de la fenêtre est atteinte, les anciens messages sont résumés.
- Budgets de tokens par tâche, par utilisateur (mensuel) et par organisation. Circuit breaker LLM.

**Outils**

| Outil | Rôle |
|-------|------|
| `browser` | Navigation web avec Playwright (dans le sandbox) |
| `code_executor` | Exécution Python / Bash |
| `web_search` | Recherche web (Brave, SearXNG ou Tavily) |
| `file_system` | Lecture et écriture dans `/workspace` |
| `doc_parser` | Extraction de documents (PDF, DOCX…) |
| `http_caller` | Appels HTTP vers une liste de domaines autorisés |
| `email` / `calendar` | IMAP/SMTP et CalDAV, activés par un opérateur, avec validation HITL |
| `dispatch_subtask` / `gather_results` | Délégation et agrégation multi-agent |

On peut aussi ajouter des outils sans toucher au code : découverte automatique de serveurs **MCP**, génération d'outils depuis une **spec OpenAPI**, et une **marketplace** de plugins communautaires.

**Mémoire**

| Couche | Stockage | Durée de vie |
|--------|----------|--------------|
| Travail | `AgentState` LangGraph (checkpointé) | Session |
| Court terme | Redis DB1 | 24 h |
| Long terme | Qdrant (recherche hybride dense + sparse) + PostgreSQL | Permanente |
| Épisodique | PostgreSQL `task_steps` | Permanente (replay et audit) |

**Plateforme**
- Interface web EN/FR avec trace en direct (SSE, reconnexion via `Last-Event-ID`) et historique des tâches.
- Tâches planifiées et récurrentes (cron), modèles de tâches, interface vocale (Whisper + TTS).
- Authentification JWT, clés API, OIDC/SSO (PKCE), RBAC `user` → `admin` → `operator`.
- Organisations : surcharge du LLM, restrictions d'outils et budgets par organisation.
- Webhooks signés HMAC, journal d'audit en ajout seul, scan antivirus ClamAV des fichiers envoyés.
- Sauvegardes automatiques (pg_dump, snapshots Qdrant) et nettoyage des artefacts expirés.

---

## Architecture

```
                ┌──────────────┐
  Navigateur ──▶│  Next.js UI  │──── SSE (trace) / WebSocket (HITL)
                └──────┬───────┘
                       │ REST /api/v1
                ┌──────▼───────┐        ┌──────────┐
                │ FastAPI (api)│───────▶│  Redis   │ DB0 broker · DB1 cache
                └──────┬───────┘        └────┬─────┘
                       │                     │
         ┌─────────────▼──────┐     ┌────────▼─────────┐
         │ PostgreSQL 16      │◀────│ Celery worker    │── LangGraph orchestrator
         │ (via PgBouncer)    │     │ + beat (cron)    │── LLM (Anthropic, OpenAI…)
         └────────────────────┘     └────────┬─────────┘
                ┌────────┐ ┌───────┐         │ JSON-RPC 2.0 (port 9999)
                │ Qdrant │ │ MinIO │  ┌──────▼────────────────────┐
                └────────┘ └───────┘  │ Sandbox (1 par session)   │
                                      │ Playwright, Python, Node… │──▶ Squid (allowlist)
                                      └───────────────────────────┘
```

- L'orchestrateur ne fait **que des appels RPC**. Playwright, le code et les accès fichiers s'exécutent uniquement dans le sandbox.
- Sandbox : 2 vCPU, 2 Go de RAM, 5 Go de disque, 30 min maximum. Le système de fichiers racine est en lecture seule, seul `/workspace` est inscriptible. Les sorties réseau passent par Squid avec une liste blanche de domaines. Un pool de conteneurs préchauffés réduit le temps de démarrage.
- Les secrets d'intégration (e-mail, calendrier) sont chiffrés et lus au moment de l'appel. Ils n'entrent jamais dans le contexte du LLM ni dans `task_steps`.
- Les prompts système sont en anglais. La langue de l'utilisateur, détectée automatiquement, est ajoutée en instruction finale.

---

## Stack technique

| Couche | Technologie |
|--------|-------------|
| Frontend | Next.js (App Router), React 19, shadcn/ui, Tailwind CSS, next-intl, TanStack Query, Zustand |
| API | FastAPI (Python 3.12), SQLAlchemy async, Pydantic v2 |
| File de tâches | Celery + Redis |
| Orchestration | LangGraph + LangChain (`BaseChatModel`) |
| LLM | Anthropic (par défaut), OpenAI, Mistral, Groq, DeepSeek, Ollama |
| Base de données | PostgreSQL 16 + PgBouncer (mode transaction) + Alembic |
| Vecteurs | Qdrant, embeddings Voyage AI `voyage-multilingual-2` |
| Stockage | MinIO (ou système de fichiers local) |
| Sandbox | Docker durci (dev), Kata Containers / gVisor (prod) |
| Observabilité | Langfuse, Prometheus, Grafana, Loki, structlog |
| Déploiement | Docker Compose (+ Caddy en prod) |

---

## Structure du dépôt

```
.
├── backend/                 # API FastAPI, orchestrateur, workers Celery
│   ├── app/
│   │   ├── auth/            # JWT, clés API, rate limiting
│   │   ├── orchestrator/    # Graphe LangGraph, nœuds, prompts, budgets
│   │   ├── tools/           # Registre d'outils (clients RPC)
│   │   ├── sandbox/         # Gestionnaire de conteneurs + client JSON-RPC
│   │   ├── memory/          # Mémoire court terme (Redis) / long terme (Qdrant)
│   │   ├── routers/         # Endpoints REST, SSE et WebSocket
│   │   ├── services/        # HITL, webhooks, MCP, OpenAPI, voix, ClamAV…
│   │   └── worker/          # Tâches Celery et jobs beat
│   ├── alembic/             # Migrations de base de données
│   └── tests/
├── frontend/                # Interface Next.js (EN/FR)
├── sandbox/                 # Image du sandbox + serveur d'outils JSON-RPC
├── squid/                   # Proxy de sortie (allowlist)
├── pgbouncer/
├── infra/                   # Prometheus, Loki, Grafana, scripts de déploiement
├── docs/                    # Spécification, plans de phases, prochaines étapes
├── docker-compose.yml           # Stack de base
├── docker-compose.override.yml  # Surcharges dev (hot reload, ports)
└── docker-compose.prod.yml      # Production (Caddy, aucun port interne exposé)
```

---

## Démarrage rapide (développement)

### Prérequis

- Docker et Docker Compose v2
- `openssl`
- Une clé API pour le fournisseur LLM choisi (Anthropic par défaut)
- Optionnel : une clé Voyage AI (mémoire long terme) et une clé Brave/Tavily (recherche web)

### 1. Configurer l'environnement

```bash
cp .env.example .env
# Renseignez au minimum AGENTIS_LLM_API_KEY, et en dev :
#   AGENTIS_SANDBOX_RUNTIME=docker
# Ajoutez AGENTIS_VOYAGE_API_KEY et AGENTIS_BRAVE_API_KEY selon les outils voulus.
```

Les valeurs `CHANGE_ME` du fichier d'exemple sont prévues pour la production. En dev, `docker-compose.yml` fixe déjà les identifiants Postgres, Redis et MinIO de l'API (`agentis` / `agentis`).

### 2. Générer les clés JWT

```bash
mkdir -p secrets/jwt
openssl genrsa -out secrets/jwt/private.pem 4096
openssl rsa -in secrets/jwt/private.pem -pubout -out secrets/jwt/public.pem
```

`secrets/jwt/` est ignoré par git.

### 3. Construire l'image du sandbox

```bash
docker compose --profile sandbox build sandbox   # produit agentis-sandbox:latest
```

### 4. Démarrer la stack

```bash
docker compose up -d --build
docker compose exec api alembic upgrade head      # appliquer les migrations
```

| Service | URL |
|---------|-----|
| Interface web | http://localhost:3010 |
| API | http://localhost:8001 |
| Documentation OpenAPI | http://localhost:8001/docs |
| Healthcheck | http://localhost:8001/api/v1/health |
| Console MinIO | http://localhost:9003 |
| Qdrant | http://localhost:6333 |

En dev, l'API et le worker montent `./backend` : le code est rechargé à chaud.

### Profils optionnels

```bash
# Prometheus (9090), Loki (3100), Grafana (3002)
docker compose --profile observability up -d

# Langfuse (3001) : créez d'abord sa base
docker compose exec postgres createdb -U agentis langfuse
docker compose --profile langfuse up -d langfuse
```

### Frontend hors Docker

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8001 npm run dev
```

---

## Configuration

Toutes les variables backend ont le préfixe `AGENTIS_`. Elles sont documentées dans [`.env.example`](.env.example), et la référence complète se trouve dans la [spec §19](docs/agentis_spec.md). Les principales :

| Variable | Rôle | Défaut |
|----------|------|--------|
| `AGENTIS_LLM_PROVIDER` | `anthropic` \| `openai` \| `mistral` \| `groq` \| `deepseek` \| `ollama` | `anthropic` |
| `AGENTIS_LLM_MODEL` | Identifiant du modèle | `claude-sonnet-4-5-20251022` |
| `AGENTIS_LLM_API_KEY` | Clé du fournisseur | — |
| `AGENTIS_LLM_BASE_URL` | Endpoint personnalisé (Ollama, auto-hébergé) | — |
| `AGENTIS_SANDBOX_RUNTIME` | `kata` \| `gvisor` \| `docker` | `docker` |
| `AGENTIS_SANDBOX_MAX_CONCURRENT` | Nombre maximal de sandboxes simultanés | `10` |
| `AGENTIS_SANDBOX_WARM_POOL_SIZE` | Conteneurs préchauffés | `2` |
| `AGENTIS_SEARCH_BACKEND` | `brave` \| `searxng` \| `tavily` | `brave` |
| `AGENTIS_VOYAGE_API_KEY` | Embeddings pour la mémoire long terme | — |
| `AGENTIS_TOKEN_BUDGET_PER_TASK` | Budget de tokens par tâche | `100000` |
| `AGENTIS_HITL_CONFIDENCE_THRESHOLD` | Seuil de confiance qui déclenche le HITL | `0.3` |
| `AGENTIS_DEFAULT_LANGUAGE` | Langue par défaut (`fr` / `en`) | `fr` |
| `AGENTIS_FERNET_KEY` | Clé de chiffrement des secrets stockés en base | — |

Changer de fournisseur LLM ne demande qu'une modification de configuration. Les administrateurs peuvent aussi le faire depuis `/admin/config`, et chaque organisation peut avoir son propre fournisseur.

---

## Tests

**Backend** : il faut Postgres sur le port `5436` (base `agentis_test`) et Redis sur `6379`.

```bash
docker compose up -d postgres redis
cd backend
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -m "not slow"     # suite rapide
.venv/bin/python -m pytest -m slow           # intégration, nécessite le sandbox Docker
```

**Frontend**

```bash
cd frontend
npx vitest run
npx tsc --noEmit
npm run lint
```

---

## Déploiement en production

La cible de production est **Docker Compose** sur un VPS Debian 11/12, derrière **Caddy** (TLS automatique). Aucun service interne n'expose de port.

```bash
# 1. Installation initiale : dépendances, utilisateur agentis, clés JWT, template Caddyfile
sudo bash infra/deploy/install.sh

# 2. Éditer .env (valeurs CHANGE_ME) et infra/Caddyfile (domaine)

# 3. Déployer : build, migrations Alembic, redémarrage de api/worker, healthcheck
bash infra/deploy/deploy.sh

# Mises à jour suivantes : git pull + deploy
bash infra/deploy/update.sh [branche]
```

Les scripts utilisent `docker compose -f docker-compose.yml -f docker-compose.prod.yml`. En production, utilisez `AGENTIS_SANDBOX_RUNTIME=kata` (ou `gvisor`) si l'hôte le permet.

---

## Observabilité

- **Langfuse** : traces de chaque appel LLM et de chaque étape d'agent.
- **Prometheus** : `/metrics` sur l'API, agrégé en mode multiprocess entre l'API, les workers et beat.
- **Grafana** : dashboard `Agentis` provisionné automatiquement (`infra/grafana/`).
- **Loki** : logs JSON structurés (structlog).
- **Trace épisodique** : chaque étape est persistée dans `task_steps` pour le replay et l'audit.

---

## Sécurité

- Un sandbox par session, en micro-VM Kata en production, sans pod privilégié.
- Sorties réseau filtrées par Squid, avec des ACL par session.
- Secrets d'intégration chiffrés (Fernet), jamais exposés au LLM.
- JWT RS256 (clés RSA 4096), clés API, rate limiting, RBAC à trois niveaux.
- Journal d'audit en ajout seul, webhooks signés HMAC, scan ClamAV optionnel.

Détails dans la [spec §16](docs/agentis_spec.md).

---

## Documentation

| Document | Contenu |
|----------|---------|
| [`docs/agentis_spec.md`](docs/agentis_spec.md) | Spécification complète v2.0 : epics, modèle de données, API, sécurité, infra |
| [`docs/NEXT_STEPS.md`](docs/NEXT_STEPS.md) | Priorités en cours |

---

## Roadmap

- [x] **Phase 1** : boucle d'agent, 4 outils de base, sandbox, UI + SSE, auth, EN/FR
- [x] **Phase 2** : mémoire long terme, HITL, audit, admin, observabilité, organisations, webhooks, OIDC
- [x] **Phase 3** : MCP, OpenAPI, e-mail/calendrier, LLM par organisation, modèles de tâches, ClamAV
- [x] **Phase 4** : multi-agent, voix, marketplace
- [ ] Facturation de l'usage par organisation (budgets et plafonds déjà en place)
- [ ] Vue multi-agent à N traces parallèles (partielle)
- [ ] LLM open source fine-tuné
- [ ] CI GitHub Actions
