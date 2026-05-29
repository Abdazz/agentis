# Phase 1D — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Next.js 15 App Router frontend for Agentis — task submission, SSE live trace, task history, auth pages, settings, and EN/FR i18n — as an independent git repo at `agentis/frontend/`.

**Architecture:** Browser Client Components call FastAPI directly via a `fetch`-based HTTP client that handles 401→refresh transparently. SSE uses `fetch + ReadableStream` (not `EventSource`) so it can send `Authorization` and `Last-Event-ID` headers simultaneously. Three Tailwind CSS-variable themes (Light Clean default, Dark Pro, Dark Accent) managed by `next-themes`.

**Tech Stack:** Next.js 15 (App Router), shadcn/ui, Tailwind CSS, next-themes, TanStack Query v5, Zustand, next-intl, React Hook Form + Zod, Vitest + React Testing Library.

---

## File Map

### New repo: `agentis/frontend/`
```
app/[locale]/
  layout.tsx              — root layout: providers + AuthInitializer
  page.tsx                — / Centered Hero
  login/page.tsx
  register/page.tsx
  tasks/page.tsx          — Server Component initial fetch
  tasks/[id]/page.tsx     — live trace shell
  settings/page.tsx
components/
  auth-initializer.tsx    — calls /auth/refresh on mount
  nav.tsx                 — navbar: links, locale switcher, theme switcher
  task-form.tsx           — goal textarea + file upload
  task-feed.tsx           — Terminal Feed SSE display
  task-list.tsx           — paginated task rows
  theme-switcher.tsx      — 3-theme selector
  providers.tsx           — QueryClientProvider + ThemeProvider (client boundary)
lib/
  api.ts                  — fetch wrapper + 401 interceptor
  auth.ts                 — Zustand: accessToken in memory
  sse.ts                  — fetch+ReadableStream SSE client + backoff
i18n/
  routing.ts              — defineRouting (locales, defaultLocale)
  request.ts              — getRequestConfig (server-side)
  navigation.ts           — createNavigation (type-safe Link/useRouter)
messages/
  fr.json / en.json
middleware.ts
next.config.ts
tailwind.config.ts
vitest.config.ts
vitest.setup.ts
Dockerfile
```

### Modified: parent repo
- `.gitignore` — add `frontend/` (and `backend/` if not present)
- `docker-compose.yml` — add `ui` service

### Modified: `agentis/backend/`
- `app/routers/auth.py` — add GET/PATCH `/users/me`, GET `/users/me/usage`
- `tests/test_auth/test_users_me.py` — new

---

## Task 1: Parent repo gitignore + frontend git init

**Files:**
- Modify: `agentis/.gitignore`

- [ ] **Step 1: Update parent .gitignore**

Open `agentis/.gitignore`. If `backend/` is not already present, add it. Add `frontend/`:

```
# sub-repos (independent git repos nested inside parent)
backend/
frontend/
```

- [ ] **Step 2: Commit the gitignore change**

```bash
cd /path/to/agentis
git add .gitignore
git commit -m "chore: gitignore backend/ and frontend/ sub-repos"
```

- [ ] **Step 3: Initialize the frontend git repo**

```bash
mkdir -p agentis/frontend
cd agentis/frontend
git init
git commit --allow-empty -m "chore: initial commit"
```

---

## Task 2: Next.js 15 scaffold

**Files:**
- Create: `frontend/package.json`, `frontend/next.config.ts`, `frontend/tailwind.config.ts`, `frontend/tsconfig.json`, `frontend/vitest.config.ts`, `frontend/vitest.setup.ts`

- [ ] **Step 1: Scaffold Next.js project**

Run inside `agentis/frontend/`:

```bash
npx create-next-app@latest . \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --no-src-dir \
  --import-alias "@/*"
```

Answer: **No** to "Would you like to use Turbopack?" (Vitest compatibility)

- [ ] **Step 2: Install additional dependencies**

```bash
npm install \
  @tanstack/react-query@^5 \
  zustand \
  next-intl \
  next-themes \
  react-hook-form \
  zod \
  @hookform/resolvers

npm install --save-dev \
  vitest \
  @vitejs/plugin-react \
  @testing-library/react \
  @testing-library/jest-dom \
  @testing-library/user-event \
  jsdom \
  @types/node
```

- [ ] **Step 3: Create `vitest.config.ts`**

```typescript
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    globals: true,
  },
  resolve: {
    alias: { '@': path.resolve(__dirname, '.') },
  },
})
```

- [ ] **Step 4: Create `vitest.setup.ts`**

```typescript
import '@testing-library/jest-dom'
```

- [ ] **Step 5: Add test script to `package.json`**

In `package.json`, add to `"scripts"`:
```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 6: Update `next.config.ts`** (will be extended in Task 5 for next-intl)

```typescript
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  // next-intl plugin added in Task 5
}

export default nextConfig
```

- [ ] **Step 7: Verify tests run**

```bash
npx vitest run
```

Expected: "No test files found" (exit 0 — no tests yet, but setup is valid)

- [ ] **Step 8: Commit**

```bash
git add .
git commit -m "chore: Next.js 15 scaffold + Vitest setup"
```

---

## Task 3: Tailwind theme system (3 CSS-variable themes)

**Files:**
- Modify: `frontend/app/globals.css`
- Modify: `frontend/tailwind.config.ts`

- [ ] **Step 1: Define CSS variables for 3 themes in `app/globals.css`**

Replace the existing Tailwind CSS variable block with:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  /* ── Light Clean (default) ── */
  :root,
  [data-theme='light'] {
    --background: 248 250 252;        /* slate-50 */
    --foreground: 15 23 42;           /* slate-900 */
    --card: 255 255 255;
    --card-foreground: 15 23 42;
    --border: 226 232 240;            /* slate-200 */
    --input: 226 232 240;
    --primary: 37 99 235;             /* blue-600 */
    --primary-foreground: 255 255 255;
    --secondary: 241 245 249;         /* slate-100 */
    --secondary-foreground: 15 23 42;
    --muted: 100 116 139;             /* slate-500 */
    --muted-foreground: 100 116 139;
    --accent: 241 245 249;
    --accent-foreground: 15 23 42;
    --success: 22 163 74;             /* green-600 */
    --destructive: 220 38 38;         /* red-600 */
    --ring: 37 99 235;
    --radius: 0.5rem;
  }

  /* ── Dark Professional (indigo) ── */
  [data-theme='dark-pro'] {
    --background: 15 17 23;
    --foreground: 226 232 240;
    --card: 30 33 48;
    --card-foreground: 226 232 240;
    --border: 45 50 70;
    --input: 45 50 70;
    --primary: 99 102 241;            /* indigo-500 */
    --primary-foreground: 255 255 255;
    --secondary: 37 41 60;
    --secondary-foreground: 226 232 240;
    --muted: 148 163 184;
    --muted-foreground: 148 163 184;
    --accent: 37 41 60;
    --accent-foreground: 226 232 240;
    --success: 34 197 94;
    --destructive: 248 113 113;
    --ring: 99 102 241;
    --radius: 0.5rem;
  }

  /* ── Dark Accent Orange ── */
  [data-theme='dark-accent'] {
    --background: 9 9 11;             /* zinc-950 */
    --foreground: 250 250 250;
    --card: 24 24 27;                 /* zinc-900 */
    --card-foreground: 250 250 250;
    --border: 39 39 42;              /* zinc-800 */
    --input: 39 39 42;
    --primary: 249 115 22;           /* orange-500 */
    --primary-foreground: 255 255 255;
    --secondary: 39 39 42;
    --secondary-foreground: 250 250 250;
    --muted: 113 113 122;            /* zinc-500 */
    --muted-foreground: 113 113 122;
    --accent: 39 39 42;
    --accent-foreground: 250 250 250;
    --success: 34 197 94;
    --destructive: 248 113 113;
    --ring: 249 115 22;
    --radius: 0.5rem;
  }
}
```

- [ ] **Step 2: Update `tailwind.config.ts`** to map CSS variables to Tailwind colors

```typescript
import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: ['selector', '[data-theme="dark-pro"]', '[data-theme="dark-accent"]'],
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: 'rgb(var(--background) / <alpha-value>)',
        foreground: 'rgb(var(--foreground) / <alpha-value>)',
        card: {
          DEFAULT: 'rgb(var(--card) / <alpha-value>)',
          foreground: 'rgb(var(--card-foreground) / <alpha-value>)',
        },
        border: 'rgb(var(--border) / <alpha-value>)',
        input: 'rgb(var(--input) / <alpha-value>)',
        primary: {
          DEFAULT: 'rgb(var(--primary) / <alpha-value>)',
          foreground: 'rgb(var(--primary-foreground) / <alpha-value>)',
        },
        secondary: {
          DEFAULT: 'rgb(var(--secondary) / <alpha-value>)',
          foreground: 'rgb(var(--secondary-foreground) / <alpha-value>)',
        },
        muted: {
          DEFAULT: 'rgb(var(--muted) / <alpha-value>)',
          foreground: 'rgb(var(--muted-foreground) / <alpha-value>)',
        },
        success: 'rgb(var(--success) / <alpha-value>)',
        destructive: 'rgb(var(--destructive) / <alpha-value>)',
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
    },
  },
  plugins: [],
}

export default config
```

- [ ] **Step 3: Commit**

```bash
git add app/globals.css tailwind.config.ts
git commit -m "feat: 3-theme CSS variable system (light/dark-pro/dark-accent)"
```

---

## Task 4: next-intl i18n setup

**Files:**
- Create: `frontend/i18n/routing.ts`, `frontend/i18n/request.ts`, `frontend/i18n/navigation.ts`
- Create: `frontend/messages/fr.json`, `frontend/messages/en.json`
- Create: `frontend/middleware.ts`
- Modify: `frontend/next.config.ts`

- [ ] **Step 1: Create `i18n/routing.ts`**

```typescript
import { defineRouting } from 'next-intl/routing'

export const routing = defineRouting({
  locales: ['fr', 'en'],
  defaultLocale: 'fr',
})
```

- [ ] **Step 2: Create `i18n/request.ts`**

```typescript
import { getRequestConfig } from 'next-intl/server'
import { routing } from './routing'

export default getRequestConfig(async ({ requestLocale }) => {
  let locale = await requestLocale
  if (!locale || !routing.locales.includes(locale as 'fr' | 'en')) {
    locale = routing.defaultLocale
  }
  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  }
})
```

- [ ] **Step 3: Create `i18n/navigation.ts`**

```typescript
import { createNavigation } from 'next-intl/navigation'
import { routing } from './routing'

export const { Link, redirect, usePathname, useRouter } = createNavigation(routing)
```

- [ ] **Step 4: Create `middleware.ts`**

```typescript
import createMiddleware from 'next-intl/middleware'
import { routing } from './i18n/routing'

export default createMiddleware(routing)

export const config = {
  matcher: ['/((?!api|_next|_vercel|.*\\..*).*)'],
}
```

- [ ] **Step 5: Update `next.config.ts`**

```typescript
import type { NextConfig } from 'next'
import createNextIntlPlugin from 'next-intl/plugin'

const withNextIntl = createNextIntlPlugin('./i18n/request.ts')

const nextConfig: NextConfig = {}

export default withNextIntl(nextConfig)
```

- [ ] **Step 6: Create `messages/fr.json`**

```json
{
  "nav": {
    "title": "Agentis",
    "tasks": "Tâches",
    "settings": "Paramètres",
    "logout": "Déconnexion",
    "login": "Connexion",
    "register": "Inscription"
  },
  "home": {
    "title": "Que souhaitez-vous accomplir ?",
    "subtitle": "Décrivez votre objectif, l'agent s'en occupe.",
    "placeholder": "Recherche les concurrents de notre produit et synthétise les résultats…",
    "submit": "Lancer",
    "attach": "Joindre un fichier",
    "recent": "Récents"
  },
  "tasks": {
    "title": "Tâches",
    "empty": "Aucune tâche pour l'instant.",
    "status": {
      "pending": "En attente",
      "running": "En cours",
      "completed": "Terminé",
      "failed": "Échoué",
      "cancelled": "Annulé",
      "waiting_for_input": "En attente d'entrée"
    },
    "cancel": "Annuler",
    "cancelConfirm": "Annuler cette tâche ?",
    "confidence": "Confiance"
  },
  "events": {
    "plan": "PLAN",
    "think": "THINK",
    "tool": "TOOL",
    "result": "RESULT",
    "summary": "SUMMARY",
    "done": "TERMINÉ",
    "error": "ERREUR"
  },
  "settings": {
    "title": "Paramètres",
    "language": "Langue",
    "theme": "Thème",
    "themeLight": "Clair",
    "themeDarkPro": "Sombre Pro",
    "themeDarkAccent": "Sombre Orange",
    "apiKeys": "Clés API",
    "apiKeysNew": "Créer une clé",
    "apiKeysNewLabel": "Nom de la clé",
    "apiKeysRevoke": "Révoquer",
    "usage": "Utilisation des tokens",
    "usageThisMonth": "Ce mois-ci",
    "save": "Enregistrer"
  },
  "auth": {
    "loginTitle": "Connexion",
    "registerTitle": "Créer un compte",
    "email": "Email",
    "password": "Mot de passe",
    "name": "Nom",
    "loginSubmit": "Se connecter",
    "registerSubmit": "Créer le compte",
    "noAccount": "Pas encore de compte ?",
    "hasAccount": "Déjà un compte ?",
    "errors": {
      "invalid_credentials": "Email ou mot de passe incorrect.",
      "email_taken": "Cet email est déjà utilisé.",
      "generic": "Une erreur est survenue. Veuillez réessayer."
    }
  },
  "errors": {
    "notFound": "Page introuvable.",
    "unauthorized": "Vous devez être connecté."
  }
}
```

- [ ] **Step 7: Create `messages/en.json`**

```json
{
  "nav": {
    "title": "Agentis",
    "tasks": "Tasks",
    "settings": "Settings",
    "logout": "Log out",
    "login": "Log in",
    "register": "Sign up"
  },
  "home": {
    "title": "What would you like to accomplish?",
    "subtitle": "Describe your goal, the agent handles the rest.",
    "placeholder": "Research our product's competitors and summarize the findings…",
    "submit": "Run",
    "attach": "Attach file",
    "recent": "Recent"
  },
  "tasks": {
    "title": "Tasks",
    "empty": "No tasks yet.",
    "status": {
      "pending": "Pending",
      "running": "Running",
      "completed": "Completed",
      "failed": "Failed",
      "cancelled": "Cancelled",
      "waiting_for_input": "Waiting for input"
    },
    "cancel": "Cancel",
    "cancelConfirm": "Cancel this task?",
    "confidence": "Confidence"
  },
  "events": {
    "plan": "PLAN",
    "think": "THINK",
    "tool": "TOOL",
    "result": "RESULT",
    "summary": "SUMMARY",
    "done": "DONE",
    "error": "ERROR"
  },
  "settings": {
    "title": "Settings",
    "language": "Language",
    "theme": "Theme",
    "themeLight": "Light",
    "themeDarkPro": "Dark Pro",
    "themeDarkAccent": "Dark Orange",
    "apiKeys": "API Keys",
    "apiKeysNew": "Create key",
    "apiKeysNewLabel": "Key name",
    "apiKeysRevoke": "Revoke",
    "usage": "Token usage",
    "usageThisMonth": "This month",
    "save": "Save"
  },
  "auth": {
    "loginTitle": "Log in",
    "registerTitle": "Create an account",
    "email": "Email",
    "password": "Password",
    "name": "Name",
    "loginSubmit": "Log in",
    "registerSubmit": "Create account",
    "noAccount": "Don't have an account?",
    "hasAccount": "Already have an account?",
    "errors": {
      "invalid_credentials": "Invalid email or password.",
      "email_taken": "This email is already in use.",
      "generic": "Something went wrong. Please try again."
    }
  },
  "errors": {
    "notFound": "Page not found.",
    "unauthorized": "You must be logged in."
  }
}
```

- [ ] **Step 8: Restructure `app/` for `[locale]` routing**

Move `app/page.tsx`, `app/layout.tsx` into `app/[locale]/`. Delete `app/page.tsx` at the root. Create `app/[locale]/layout.tsx` (content in Task 9).

- [ ] **Step 9: Verify Next.js starts**

```bash
npm run dev
```

Navigate to `http://localhost:3000` — should redirect to `http://localhost:3000/fr`.

- [ ] **Step 10: Commit**

```bash
git add .
git commit -m "feat: next-intl setup (EN/FR, /[locale] routing, fr default)"
```

---

## Task 5: `lib/auth.ts` — Zustand store (TDD)

**Files:**
- Create: `frontend/lib/auth.ts`
- Create: `frontend/lib/__tests__/auth.test.ts`

- [ ] **Step 1: Write the failing test**

Create `lib/__tests__/auth.test.ts`:

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from '../auth'

describe('useAuthStore', () => {
  beforeEach(() => {
    useAuthStore.setState({ accessToken: null })
  })

  it('starts with null token', () => {
    expect(useAuthStore.getState().accessToken).toBeNull()
  })

  it('setAccessToken stores a token', () => {
    useAuthStore.getState().setAccessToken('tok_abc')
    expect(useAuthStore.getState().accessToken).toBe('tok_abc')
  })

  it('clearAuth resets token to null', () => {
    useAuthStore.getState().setAccessToken('tok_abc')
    useAuthStore.getState().clearAuth()
    expect(useAuthStore.getState().accessToken).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npx vitest run lib/__tests__/auth.test.ts
```

Expected: FAIL — "Cannot find module '../auth'"

- [ ] **Step 3: Implement `lib/auth.ts`**

```typescript
import { create } from 'zustand'

interface AuthState {
  accessToken: string | null
  setAccessToken: (token: string | null) => void
  clearAuth: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  setAccessToken: (token) => set({ accessToken: token }),
  clearAuth: () => set({ accessToken: null }),
}))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npx vitest run lib/__tests__/auth.test.ts
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/auth.ts lib/__tests__/auth.test.ts
git commit -m "feat: Zustand auth store (access token in memory)"
```

---

## Task 6: `lib/api.ts` — HTTP client with 401 interceptor (TDD)

**Files:**
- Create: `frontend/lib/api.ts`
- Create: `frontend/lib/__tests__/api.test.ts`

- [ ] **Step 1: Write failing tests**

Create `lib/__tests__/api.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAuthStore } from '../auth'

// We import apiFetch after setting up the mock
let apiFetch: typeof import('../api').apiFetch

const mockFetch = vi.fn()

beforeEach(async () => {
  vi.resetAllMocks()
  vi.stubGlobal('fetch', mockFetch)
  useAuthStore.setState({ accessToken: null })
  // Re-import to pick up fresh module state
  vi.resetModules()
  apiFetch = (await import('../api')).apiFetch
})

describe('apiFetch', () => {
  it('attaches Authorization header when token is set', async () => {
    useAuthStore.setState({ accessToken: 'tok_abc' })
    mockFetch.mockResolvedValueOnce(new Response('{}', { status: 200 }))

    await apiFetch('/api/v1/tasks')

    const [, init] = mockFetch.mock.calls[0]
    expect((init.headers as Headers).get('Authorization')).toBe('Bearer tok_abc')
  })

  it('does not attach Authorization header when no token', async () => {
    mockFetch.mockResolvedValueOnce(new Response('{}', { status: 200 }))

    await apiFetch('/api/v1/tasks')

    const [, init] = mockFetch.mock.calls[0]
    expect((init.headers as Headers).get('Authorization')).toBeNull()
  })

  it('retries with new token after 401 + successful refresh', async () => {
    useAuthStore.setState({ accessToken: 'expired_tok' })
    // First call returns 401
    mockFetch.mockResolvedValueOnce(new Response('', { status: 401 }))
    // Refresh call returns new token
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ access_token: 'new_tok' }), { status: 200 })
    )
    // Retry call succeeds
    mockFetch.mockResolvedValueOnce(new Response('{"ok":true}', { status: 200 }))

    const res = await apiFetch('/api/v1/tasks')

    expect(mockFetch).toHaveBeenCalledTimes(3)
    expect(res.status).toBe(200)
    expect(useAuthStore.getState().accessToken).toBe('new_tok')
  })

  it('clears auth and returns 401 response when refresh fails', async () => {
    useAuthStore.setState({ accessToken: 'expired_tok' })
    mockFetch.mockResolvedValueOnce(new Response('', { status: 401 }))
    mockFetch.mockResolvedValueOnce(new Response('', { status: 401 }))

    const res = await apiFetch('/api/v1/tasks')

    expect(res.status).toBe(401)
    expect(useAuthStore.getState().accessToken).toBeNull()
  })
})
```

- [ ] **Step 2: Run to verify they fail**

```bash
npx vitest run lib/__tests__/api.test.ts
```

Expected: FAIL — "Cannot find module '../api'"

- [ ] **Step 3: Implement `lib/api.ts`**

```typescript
import { useAuthStore } from './auth'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

let refreshing: Promise<string | null> | null = null

async function doRefresh(): Promise<string | null> {
  const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!res.ok) return null
  const { access_token } = await res.json()
  useAuthStore.getState().setAccessToken(access_token as string)
  return access_token as string
}

async function refreshToken(): Promise<string | null> {
  if (!refreshing) refreshing = doRefresh().finally(() => { refreshing = null })
  return refreshing
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = useAuthStore.getState().accessToken
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers,
  })

  if (res.status !== 401) return res

  const newToken = await refreshToken()
  if (!newToken) {
    useAuthStore.getState().clearAuth()
    return res
  }

  headers.set('Authorization', `Bearer ${newToken}`)
  return fetch(`${API_BASE}${path}`, { ...init, credentials: 'include', headers })
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npx vitest run lib/__tests__/api.test.ts
```

Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/api.ts lib/__tests__/api.test.ts
git commit -m "feat: HTTP client with 401→refresh interceptor"
```

---

## Task 7: `lib/sse.ts` — SSE client with backoff + Last-Event-ID (TDD)

**Files:**
- Create: `frontend/lib/sse.ts`
- Create: `frontend/lib/__tests__/sse.test.ts`

**Note:** We use `fetch + ReadableStream` instead of `EventSource` because the backend's `get_current_user` dependency requires `Authorization: Bearer` (not cookie auth), and `EventSource` cannot set custom headers.

- [ ] **Step 1: Write failing tests**

Create `lib/__tests__/sse.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../api', () => ({
  apiFetch: vi.fn(),
}))

import { apiFetch } from '../api'
import { connectSSE, parseSSEBlock } from '../sse'

const mockApiFetch = vi.mocked(apiFetch)

function makeStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
}

describe('parseSSEBlock', () => {
  it('parses id, event, data fields', () => {
    const result = parseSSEBlock('id: 5\nevent: think\ndata: {"content":"hello"}')
    expect(result).toEqual({ id: '5', type: 'think', data: { content: 'hello' } })
  })

  it('defaults type to message when event line absent', () => {
    const result = parseSSEBlock('id: 1\ndata: hello')
    expect(result).toEqual({ id: '1', type: 'message', data: 'hello' })
  })

  it('returns null for empty block', () => {
    expect(parseSSEBlock('')).toBeNull()
    expect(parseSSEBlock('   ')).toBeNull()
  })
})

describe('connectSSE', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('calls onEvent for each SSE block', async () => {
    const body = makeStream([
      'id: 1\nevent: think\ndata: {"content":"step 1"}\n\n',
      'id: 2\nevent: task_completed\ndata: {"summary":"done"}\n\n',
    ])
    mockApiFetch.mockResolvedValueOnce(new Response(body, { status: 200 }))

    const events: unknown[] = []
    await new Promise<void>((resolve) => {
      connectSSE('/api/v1/tasks/abc/stream', {
        onEvent: (e) => events.push(e),
        onDone: resolve,
      })
    })

    expect(events).toHaveLength(2)
    expect((events[0] as { type: string }).type).toBe('think')
    expect((events[1] as { type: string }).type).toBe('task_completed')
  })

  it('sends Last-Event-ID header on reconnect after error', async () => {
    vi.useFakeTimers()
    const body1 = makeStream(['id: 3\nevent: think\ndata: {}\n\n'])
    const body2 = makeStream(['id: 4\nevent: task_completed\ndata: {}\n\n'])
    mockApiFetch
      .mockRejectedValueOnce(new Error('network error'))
      .mockResolvedValueOnce(new Response(body1, { status: 200 }))
      .mockResolvedValueOnce(new Response(body2, { status: 200 }))

    const events: unknown[] = []
    await new Promise<void>((resolve) => {
      connectSSE('/api/v1/tasks/abc/stream', {
        onEvent: (e) => events.push(e),
        onDone: resolve,
        onError: () => vi.runAllTimersAsync(),
      })
    })

    // Second call should include Last-Event-ID: 3
    const [, secondInit] = mockApiFetch.mock.calls[1]
    expect((secondInit?.headers as Record<string, string>)?.['Last-Event-ID']).toBe('3')

    vi.useRealTimers()
  })

  it('returns a cleanup function that aborts the stream', () => {
    const controller = new AbortController()
    vi.spyOn(window, 'AbortController').mockReturnValue(controller)
    const abortSpy = vi.spyOn(controller, 'abort')

    const body = makeStream([])
    mockApiFetch.mockResolvedValueOnce(new Response(body, { status: 200 }))

    const disconnect = connectSSE('/api/v1/tasks/abc/stream', { onEvent: vi.fn() })
    disconnect()

    expect(abortSpy).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run to verify they fail**

```bash
npx vitest run lib/__tests__/sse.test.ts
```

Expected: FAIL — "Cannot find module '../sse'"

- [ ] **Step 3: Implement `lib/sse.ts`**

```typescript
import { apiFetch } from './api'

const BACKOFF_DELAYS = [1000, 2000, 4000, 8000, 30000]
const TERMINAL_EVENTS = new Set(['task_completed', 'task_failed'])

export type SSEEvent = {
  id: string
  type: string
  data: unknown
}

export type SSECallbacks = {
  onEvent: (event: SSEEvent) => void
  onError?: (attempt: number) => void
  onDone?: () => void
}

export function parseSSEBlock(block: string): SSEEvent | null {
  if (!block.trim()) return null
  let id = ''
  let type = 'message'
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('id: ')) id = line.slice(4).trim()
    else if (line.startsWith('event: ')) type = line.slice(7).trim()
    else if (line.startsWith('data: ')) data += (data ? '\n' : '') + line.slice(6)
  }
  if (!data) return null
  let parsed: unknown = data
  try { parsed = JSON.parse(data) } catch { /* keep as string */ }
  return { id, type, data: parsed }
}

async function readStream(
  url: string,
  lastId: string | null,
  callbacks: SSECallbacks,
  signal: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = { Accept: 'text/event-stream' }
  if (lastId) headers['Last-Event-ID'] = lastId

  const res = await apiFetch(url, { headers, signal })
  if (!res.ok) throw new Error(`SSE ${res.status}`)
  if (!res.body) throw new Error('No response body')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const parts = buf.split('\n\n')
    buf = parts.pop() ?? ''
    for (const block of parts) {
      const event = parseSSEBlock(block)
      if (!event) continue
      if (event.id) callbacks.onEvent({ ...event })
      else callbacks.onEvent(event)
      if (TERMINAL_EVENTS.has(event.type)) {
        callbacks.onDone?.()
        return
      }
    }
  }
}

export function connectSSE(url: string, callbacks: SSECallbacks): () => void {
  let closed = false
  let attempt = 0
  let lastId: string | null = null
  let controller = new AbortController()

  const wrappedCallbacks: SSECallbacks = {
    ...callbacks,
    onEvent: (event) => {
      attempt = 0
      if (event.id) lastId = event.id
      callbacks.onEvent(event)
    },
  }

  async function connect() {
    try {
      await readStream(url, lastId, wrappedCallbacks, controller.signal)
    } catch (err) {
      if (closed) return
      const delay = BACKOFF_DELAYS[Math.min(attempt, BACKOFF_DELAYS.length - 1)]
      callbacks.onError?.(attempt)
      attempt++
      setTimeout(() => {
        if (!closed) {
          controller = new AbortController()
          connect()
        }
      }, delay)
    }
  }

  connect()

  return () => {
    closed = true
    controller.abort()
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npx vitest run lib/__tests__/sse.test.ts
```

Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/sse.ts lib/__tests__/sse.test.ts
git commit -m "feat: fetch-based SSE client with backoff and Last-Event-ID"
```

---

## Task 8: shadcn/ui init + Providers + Root Layout

**Files:**
- Create: `frontend/components/providers.tsx`
- Create: `frontend/components/theme-switcher.tsx`
- Create: `frontend/app/[locale]/layout.tsx`

- [ ] **Step 1: Initialize shadcn/ui**

```bash
npx shadcn@latest init
```

When prompted:
- Style: **Default**
- Base color: **Slate**
- CSS variables: **Yes**

This creates `components/ui/` and updates `tailwind.config.ts`.

- [ ] **Step 2: Add needed shadcn components**

```bash
npx shadcn@latest add button input label textarea card badge
```

- [ ] **Step 3: Create `components/providers.tsx`**

This is a client-boundary component that wraps all providers (QueryClient, ThemeProvider):

```typescript
'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from 'next-themes'
import { useState } from 'react'

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, retry: 1 },
        },
      })
  )

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider
        attribute="data-theme"
        defaultTheme="light"
        themes={['light', 'dark-pro', 'dark-accent']}
        enableSystem={false}
      >
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  )
}
```

- [ ] **Step 4: Create `components/theme-switcher.tsx`**

```typescript
'use client'

import { useTheme } from 'next-themes'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'

const THEMES = [
  { value: 'light', labelKey: 'themeLight' },
  { value: 'dark-pro', labelKey: 'themeDarkPro' },
  { value: 'dark-accent', labelKey: 'themeDarkAccent' },
] as const

export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme()
  const t = useTranslations('settings')

  return (
    <div className="flex gap-2">
      {THEMES.map(({ value, labelKey }) => (
        <Button
          key={value}
          variant={theme === value ? 'default' : 'outline'}
          size="sm"
          onClick={() => setTheme(value)}
        >
          {t(labelKey)}
        </Button>
      ))}
    </div>
  )
}
```

- [ ] **Step 5: Create `components/auth-initializer.tsx`**

```typescript
'use client'

import { useEffect } from 'react'
import { useAuthStore } from '@/lib/auth'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export function AuthInitializer() {
  const setAccessToken = useAuthStore((s) => s.setAccessToken)

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.access_token) setAccessToken(data.access_token as string)
      })
      .catch(() => { /* unauthenticated — no token set */ })
  }, [setAccessToken])

  return null
}
```

- [ ] **Step 6: Create `app/[locale]/layout.tsx`**

```typescript
import { NextIntlClientProvider } from 'next-intl'
import { getMessages } from 'next-intl/server'
import { notFound } from 'next/navigation'
import { routing } from '@/i18n/routing'
import { Providers } from '@/components/providers'
import { AuthInitializer } from '@/components/auth-initializer'
import '@/app/globals.css'

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  if (!routing.locales.includes(locale as 'fr' | 'en')) notFound()

  const messages = await getMessages()

  return (
    <html lang={locale} suppressHydrationWarning>
      <body className="bg-background text-foreground min-h-screen">
        <NextIntlClientProvider messages={messages}>
          <Providers>
            <AuthInitializer />
            {children}
          </Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  )
}
```

- [ ] **Step 7: Verify dev server starts**

```bash
npm run dev
```

Open `http://localhost:3000/fr` — should show a blank page (no content yet) with no console errors.

- [ ] **Step 8: Commit**

```bash
git add .
git commit -m "feat: Providers, ThemeSwitcher, AuthInitializer, root layout"
```

---

## Task 9: Navbar

**Files:**
- Create: `frontend/components/nav.tsx`

- [ ] **Step 1: Create `components/nav.tsx`**

```typescript
'use client'

import { useTranslations } from 'next-intl'
import { Link, useRouter } from '@/i18n/navigation'
import { usePathname } from 'next-intl/client'
import { ThemeSwitcher } from './theme-switcher'
import { Button } from './ui/button'
import { useAuthStore } from '@/lib/auth'
import { apiFetch } from '@/lib/api'

export function Nav() {
  const t = useTranslations('nav')
  const token = useAuthStore((s) => s.accessToken)
  const clearAuth = useAuthStore((s) => s.clearAuth)
  const router = useRouter()

  async function handleLogout() {
    await apiFetch('/api/v1/auth/logout', { method: 'POST' })
    clearAuth()
    router.push('/login')
  }

  return (
    <header className="border-b border-border bg-card">
      <div className="max-w-5xl mx-auto px-4 h-14 flex items-center gap-6">
        <Link href="/" className="font-bold text-foreground">
          {t('title')}
        </Link>
        {token && (
          <>
            <Link href="/tasks" className="text-sm text-muted-foreground hover:text-foreground">
              {t('tasks')}
            </Link>
            <Link href="/settings" className="text-sm text-muted-foreground hover:text-foreground">
              {t('settings')}
            </Link>
          </>
        )}
        <div className="ml-auto flex items-center gap-3">
          <ThemeSwitcher />
          <LocaleSwitcher />
          {token ? (
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              {t('logout')}
            </Button>
          ) : (
            <Link href="/login">
              <Button variant="ghost" size="sm">{t('login')}</Button>
            </Link>
          )}
        </div>
      </div>
    </header>
  )
}

function LocaleSwitcher() {
  const router = useRouter()
  const pathname = usePathname()

  return (
    <div className="flex gap-1 text-xs">
      {(['fr', 'en'] as const).map((locale) => (
        <button
          key={locale}
          onClick={() => router.replace(pathname, { locale })}
          className="uppercase px-2 py-1 rounded hover:bg-secondary text-muted-foreground hover:text-foreground"
        >
          {locale}
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: Add Nav to the root layout**

In `app/[locale]/layout.tsx`, import `Nav` and add it before `{children}`:

```typescript
import { Nav } from '@/components/nav'
// ...
<Providers>
  <AuthInitializer />
  <Nav />
  <main className="max-w-5xl mx-auto px-4 py-8">
    {children}
  </main>
</Providers>
```

- [ ] **Step 3: Commit**

```bash
git add components/nav.tsx app/[locale]/layout.tsx
git commit -m "feat: navbar with locale switcher and theme switcher"
```

---

## Task 10: Login + Register pages

**Files:**
- Create: `frontend/app/[locale]/login/page.tsx`
- Create: `frontend/app/[locale]/register/page.tsx`

- [ ] **Step 1: Create `app/[locale]/login/page.tsx`**

```typescript
'use client'

import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useTranslations } from 'next-intl'
import { Link, useRouter } from '@/i18n/navigation'
import { apiFetch } from '@/lib/api'
import { useAuthStore } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useState } from 'react'

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
})

type FormData = z.infer<typeof schema>

export default function LoginPage() {
  const t = useTranslations('auth')
  const router = useRouter()
  const setAccessToken = useAuthStore((s) => s.setAccessToken)
  const [serverError, setServerError] = useState<string | null>(null)

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormData>({
    resolver: zodResolver(schema),
  })

  async function onSubmit(data: FormData) {
    setServerError(null)
    const res = await apiFetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      const code = body?.error?.code ?? 'generic'
      setServerError(t(`errors.${code}` as Parameters<typeof t>[0]) ?? t('errors.generic'))
      return
    }
    const { access_token } = await res.json()
    setAccessToken(access_token as string)
    router.push('/')
  }

  return (
    <div className="max-w-sm mx-auto mt-16">
      <h1 className="text-2xl font-bold mb-6">{t('loginTitle')}</h1>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div>
          <Label htmlFor="email">{t('email')}</Label>
          <Input id="email" type="email" {...register('email')} />
          {errors.email && <p className="text-destructive text-sm mt-1">{errors.email.message}</p>}
        </div>
        <div>
          <Label htmlFor="password">{t('password')}</Label>
          <Input id="password" type="password" {...register('password')} />
          {errors.password && <p className="text-destructive text-sm mt-1">{errors.password.message}</p>}
        </div>
        {serverError && <p className="text-destructive text-sm">{serverError}</p>}
        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {t('loginSubmit')}
        </Button>
      </form>
      <p className="mt-4 text-sm text-muted-foreground">
        {t('noAccount')}{' '}
        <Link href="/register" className="text-primary underline">{t('register')}</Link>
      </p>
    </div>
  )
}
```

- [ ] **Step 2: Create `app/[locale]/register/page.tsx`**

```typescript
'use client'

import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useTranslations } from 'next-intl'
import { Link, useRouter } from '@/i18n/navigation'
import { apiFetch } from '@/lib/api'
import { useAuthStore } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useState } from 'react'

const schema = z.object({
  name: z.string().min(1).max(255),
  email: z.string().email(),
  password: z.string().min(8, 'Minimum 8 characters'),
})

type FormData = z.infer<typeof schema>

export default function RegisterPage() {
  const t = useTranslations('auth')
  const router = useRouter()
  const setAccessToken = useAuthStore((s) => s.setAccessToken)
  const [serverError, setServerError] = useState<string | null>(null)

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormData>({
    resolver: zodResolver(schema),
  })

  async function onSubmit(data: FormData) {
    setServerError(null)
    const res = await apiFetch('/api/v1/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      const code = body?.error?.code ?? 'generic'
      setServerError(t(`errors.${code}` as Parameters<typeof t>[0]) ?? t('errors.generic'))
      return
    }
    // After registration, log in automatically
    const loginRes = await apiFetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: data.email, password: data.password }),
    })
    if (loginRes.ok) {
      const { access_token } = await loginRes.json()
      setAccessToken(access_token as string)
    }
    router.push('/')
  }

  return (
    <div className="max-w-sm mx-auto mt-16">
      <h1 className="text-2xl font-bold mb-6">{t('registerTitle')}</h1>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div>
          <Label htmlFor="name">{t('name')}</Label>
          <Input id="name" type="text" {...register('name')} />
          {errors.name && <p className="text-destructive text-sm mt-1">{errors.name.message}</p>}
        </div>
        <div>
          <Label htmlFor="email">{t('email')}</Label>
          <Input id="email" type="email" {...register('email')} />
          {errors.email && <p className="text-destructive text-sm mt-1">{errors.email.message}</p>}
        </div>
        <div>
          <Label htmlFor="password">{t('password')}</Label>
          <Input id="password" type="password" {...register('password')} />
          {errors.password && <p className="text-destructive text-sm mt-1">{errors.password.message}</p>}
        </div>
        {serverError && <p className="text-destructive text-sm">{serverError}</p>}
        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {t('registerSubmit')}
        </Button>
      </form>
      <p className="mt-4 text-sm text-muted-foreground">
        {t('hasAccount')}{' '}
        <Link href="/login" className="text-primary underline">{t('loginSubmit')}</Link>
      </p>
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add app/[locale]/login app/[locale]/register
git commit -m "feat: login and register pages"
```

---

## Task 11: Task submission page `/` — TaskForm (TDD)

**Files:**
- Create: `frontend/components/task-form.tsx`
- Create: `frontend/components/__tests__/task-form.test.tsx`
- Create: `frontend/app/[locale]/page.tsx`

- [ ] **Step 1: Write failing tests for TaskForm**

Create `components/__tests__/task-form.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TaskForm } from '../task-form'

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }))
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
vi.mock('@/i18n/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

import { apiFetch } from '@/lib/api'
const mockFetch = vi.mocked(apiFetch)

describe('TaskForm', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders goal textarea and submit button', () => {
    render(<TaskForm />)
    expect(screen.getByRole('textbox')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /submit/i })).toBeInTheDocument()
  })

  it('disables submit when goal is empty', () => {
    render(<TaskForm />)
    expect(screen.getByRole('button', { name: /submit/i })).toBeDisabled()
  })

  it('enables submit when goal has text', async () => {
    render(<TaskForm />)
    await userEvent.type(screen.getByRole('textbox'), 'Research competitors')
    expect(screen.getByRole('button', { name: /submit/i })).toBeEnabled()
  })

  it('rejects files larger than 50 MB', async () => {
    render(<TaskForm />)
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const bigFile = new File(['x'.repeat(51 * 1024 * 1024)], 'big.pdf', { type: 'application/pdf' })
    Object.defineProperty(input, 'files', { value: [bigFile] })
    fireEvent.change(input)
    expect(screen.getByText(/50/)).toBeInTheDocument()
  })

  it('rejects more than 5 files', async () => {
    render(<TaskForm />)
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const files = Array.from({ length: 6 }, (_, i) =>
      new File(['x'], `file${i}.txt`, { type: 'text/plain' })
    )
    Object.defineProperty(input, 'files', { value: files })
    fireEvent.change(input)
    expect(screen.getByText(/5/)).toBeInTheDocument()
  })

  it('submits JSON when no files attached', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ id: 'task-123' }), { status: 201 })
    )
    render(<TaskForm />)
    await userEvent.type(screen.getByRole('textbox'), 'Research competitors')
    await userEvent.click(screen.getByRole('button', { name: /submit/i }))

    const [path, init] = mockFetch.mock.calls[0]
    expect(path).toBe('/api/v1/tasks')
    expect(init?.method).toBe('POST')
    expect(init?.headers).toMatchObject({ 'Content-Type': 'application/json' })
  })
})
```

- [ ] **Step 2: Run to verify they fail**

```bash
npx vitest run components/__tests__/task-form.test.tsx
```

Expected: FAIL — "Cannot find module '../task-form'"

- [ ] **Step 3: Implement `components/task-form.tsx`**

```typescript
'use client'

import { useState, useRef } from 'react'
import { useTranslations } from 'next-intl'
import { useRouter } from '@/i18n/navigation'
import { apiFetch } from '@/lib/api'
import { Button } from './ui/button'
import { Textarea } from './ui/textarea'

const MAX_FILE_SIZE = 50 * 1024 * 1024 // 50 MB
const MAX_FILES = 5
const ALLOWED_TYPES = [
  'application/pdf', 'text/plain', 'text/markdown',
  'application/json', 'text/csv',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
]

export function TaskForm() {
  const t = useTranslations('home')
  const router = useRouter()
  const [goal, setGoal] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [fileError, setFileError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    setFileError(null)
    const selected = Array.from(e.target.files ?? [])
    if (selected.length > MAX_FILES) {
      setFileError(`Maximum ${MAX_FILES} files allowed.`)
      return
    }
    for (const f of selected) {
      if (f.size > MAX_FILE_SIZE) {
        setFileError(`File "${f.name}" exceeds the 50 MB limit.`)
        return
      }
      if (!ALLOWED_TYPES.includes(f.type)) {
        setFileError(`File type "${f.type}" is not allowed.`)
        return
      }
    }
    setFiles(selected)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!goal.trim()) return
    setIsSubmitting(true)
    try {
      let body: BodyInit
      let headers: Record<string, string> = {}
      if (files.length > 0) {
        const fd = new FormData()
        fd.append('goal', goal)
        for (const f of files) fd.append('files[]', f)
        body = fd
      } else {
        body = JSON.stringify({ goal })
        headers['Content-Type'] = 'application/json'
      }
      const res = await apiFetch('/api/v1/tasks', { method: 'POST', headers, body })
      if (res.ok) {
        const data = await res.json()
        router.push(`/tasks/${data.id as string}`)
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-2xl space-y-3">
      <Textarea
        value={goal}
        onChange={(e) => setGoal(e.target.value)}
        placeholder={t('placeholder')}
        className="min-h-[120px] resize-none text-base"
        aria-label={t('title')}
      />
      {fileError && <p className="text-destructive text-sm">{fileError}</p>}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
          >
            {t('attach')}
          </Button>
          {files.length > 0 && (
            <span className="text-sm text-muted-foreground">{files.length} file(s)</span>
          )}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ALLOWED_TYPES.join(',')}
            className="hidden"
            onChange={handleFileChange}
          />
        </div>
        <Button type="submit" disabled={!goal.trim() || isSubmitting}>
          {t('submit')}
        </Button>
      </div>
    </form>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npx vitest run components/__tests__/task-form.test.tsx
```

Expected: PASS (5 tests)

- [ ] **Step 5: Create `app/[locale]/page.tsx`**

```typescript
import { getTranslations } from 'next-intl/server'
import { TaskForm } from '@/components/task-form'
import { apiFetch } from '@/lib/api'
import { Link } from '@/i18n/navigation'

type TaskSummary = { id: string; goal: string; status: string }

async function getRecentTasks(): Promise<TaskSummary[]> {
  try {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/api/v1/tasks?limit=4`,
      { cache: 'no-store' }
    )
    if (!res.ok) return []
    const data = await res.json()
    return (data.items ?? []) as TaskSummary[]
  } catch {
    return []
  }
}

export default async function HomePage() {
  const t = await getTranslations('home')
  const recent = await getRecentTasks()

  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-56px)] -mt-8 gap-8">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-foreground mb-2">{t('title')}</h1>
        <p className="text-muted-foreground">{t('subtitle')}</p>
      </div>
      <TaskForm />
      {recent.length > 0 && (
        <div className="w-full max-w-2xl">
          <p className="text-sm text-muted-foreground mb-2">{t('recent')}</p>
          <div className="space-y-2">
            {recent.map((task) => (
              <Link key={task.id} href={`/tasks/${task.id}`}>
                <div className="flex items-center justify-between p-3 rounded-lg border border-border bg-card hover:bg-secondary transition-colors cursor-pointer">
                  <span className="text-sm truncate text-foreground">{task.goal}</span>
                  <span className="text-xs text-muted-foreground ml-4 shrink-0">{task.status}</span>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 6: Run all tests**

```bash
npx vitest run
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add components/task-form.tsx components/__tests__/task-form.test.tsx app/[locale]/page.tsx
git commit -m "feat: task submission page (Centered Hero) + TaskForm with file validation"
```

---

## Task 12: Task history page `/tasks`

**Files:**
- Create: `frontend/components/task-list.tsx`
- Create: `frontend/app/[locale]/tasks/page.tsx`

- [ ] **Step 1: Create `components/task-list.tsx`**

```typescript
'use client'

import { useInfiniteQuery } from '@tanstack/react-query'
import { useTranslations } from 'next-intl'
import { Link } from '@/i18n/navigation'
import { apiFetch } from '@/lib/api'

type Task = {
  id: string
  goal: string
  status: string
  created_at: string
  duration_ms: number | null
}

type TaskPage = {
  items: Task[]
  next_cursor: string | null
}

async function fetchTasks(cursor?: string): Promise<TaskPage> {
  const params = new URLSearchParams({ limit: '20' })
  if (cursor) params.set('cursor', cursor)
  const res = await apiFetch(`/api/v1/tasks?${params}`)
  if (!res.ok) throw new Error('Failed to fetch tasks')
  return res.json()
}

const STATUS_COLORS: Record<string, string> = {
  running: 'text-primary',
  completed: 'text-success',
  failed: 'text-destructive',
  cancelled: 'text-muted-foreground',
  pending: 'text-muted-foreground',
  waiting_for_input: 'text-primary',
}

function formatDuration(ms: number | null): string {
  if (!ms) return '—'
  const s = Math.round(ms / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

export function TaskList({ initialItems }: { initialItems: Task[] }) {
  const t = useTranslations('tasks')

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: ['tasks'],
    queryFn: ({ pageParam }) => fetchTasks(pageParam as string | undefined),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    initialData: {
      pages: [{ items: initialItems, next_cursor: null }],
      pageParams: [undefined],
    },
  })

  const tasks = data.pages.flatMap((p) => p.items)

  if (tasks.length === 0) {
    return <p className="text-muted-foreground">{t('empty')}</p>
  }

  return (
    <div className="space-y-2">
      {tasks.map((task) => (
        <Link key={task.id} href={`/tasks/${task.id}`}>
          <div className="flex items-center justify-between p-4 rounded-lg border border-border bg-card hover:bg-secondary transition-colors cursor-pointer">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-foreground truncate">{task.goal}</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {new Date(task.created_at).toLocaleString()}
              </p>
            </div>
            <div className="ml-4 flex items-center gap-4 shrink-0">
              <span className="text-xs text-muted-foreground">{formatDuration(task.duration_ms)}</span>
              <span className={`text-xs font-medium ${STATUS_COLORS[task.status] ?? 'text-muted-foreground'}`}>
                {t(`status.${task.status}` as Parameters<typeof t>[0])}
              </span>
            </div>
          </div>
        </Link>
      ))}
      {hasNextPage && (
        <button
          onClick={() => fetchNextPage()}
          disabled={isFetchingNextPage}
          className="w-full py-2 text-sm text-muted-foreground hover:text-foreground disabled:opacity-50"
        >
          {isFetchingNextPage ? '…' : 'Load more'}
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Create `app/[locale]/tasks/page.tsx`**

```typescript
import { getTranslations } from 'next-intl/server'
import { TaskList } from '@/components/task-list'

type Task = { id: string; goal: string; status: string; created_at: string; duration_ms: number | null }

async function getFirstPage(): Promise<Task[]> {
  try {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/api/v1/tasks?limit=20`,
      { cache: 'no-store' }
    )
    if (!res.ok) return []
    const data = await res.json()
    return (data.items ?? []) as Task[]
  } catch {
    return []
  }
}

export default async function TasksPage() {
  const t = await getTranslations('tasks')
  const initial = await getFirstPage()

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">{t('title')}</h1>
      <TaskList initialItems={initial} />
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add components/task-list.tsx app/[locale]/tasks/page.tsx
git commit -m "feat: task history page with infinite scroll"
```

---

## Task 13: Live trace page `/tasks/[id]` — TaskFeed (TDD)

**Files:**
- Create: `frontend/components/task-feed.tsx`
- Create: `frontend/components/__tests__/task-feed.test.tsx`
- Create: `frontend/app/[locale]/tasks/[id]/page.tsx`

- [ ] **Step 1: Write failing tests for TaskFeed**

Create `components/__tests__/task-feed.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import type { SSECallbacks } from '@/lib/sse'

vi.mock('@/lib/sse', () => ({
  connectSSE: vi.fn(),
}))
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }))
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
vi.mock('@/i18n/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

import { connectSSE } from '@/lib/sse'
import { TaskFeed } from '../task-feed'

const mockConnectSSE = vi.mocked(connectSSE)

describe('TaskFeed', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders think event with THINK badge', async () => {
    let capturedCallbacks: SSECallbacks
    mockConnectSSE.mockImplementation((_url, callbacks) => {
      capturedCallbacks = callbacks
      return () => {}
    })

    render(<TaskFeed taskId="abc-123" status="running" goal="Research task" />)

    act(() => {
      capturedCallbacks!.onEvent({
        id: '1',
        type: 'think',
        data: { content: 'Analyzing the request', tokens: 42 },
      })
    })

    expect(screen.getByText('events.think')).toBeInTheDocument()
    expect(screen.getByText('Analyzing the request')).toBeInTheDocument()
  })

  it('renders tool_call event with TOOL badge', async () => {
    let capturedCallbacks: SSECallbacks
    mockConnectSSE.mockImplementation((_url, callbacks) => {
      capturedCallbacks = callbacks
      return () => {}
    })

    render(<TaskFeed taskId="abc-123" status="running" goal="Research task" />)

    act(() => {
      capturedCallbacks!.onEvent({
        id: '2',
        type: 'tool_call',
        data: { tool: 'web_search', params: { query: 'SaaS competitors' }, call_id: 'c1' },
      })
    })

    expect(screen.getByText('events.tool')).toBeInTheDocument()
    expect(screen.getByText(/web_search/)).toBeInTheDocument()
  })

  it('shows cancel button when status is running', () => {
    mockConnectSSE.mockReturnValue(() => {})
    render(<TaskFeed taskId="abc-123" status="running" goal="Research task" />)
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
  })

  it('does not show cancel button when task is completed', () => {
    mockConnectSSE.mockReturnValue(() => {})
    render(<TaskFeed taskId="abc-123" status="completed" goal="Research task" />)
    expect(screen.queryByRole('button', { name: /cancel/i })).toBeNull()
  })
})
```

- [ ] **Step 2: Run to verify they fail**

```bash
npx vitest run components/__tests__/task-feed.test.tsx
```

Expected: FAIL — "Cannot find module '../task-feed'"

- [ ] **Step 3: Implement `components/task-feed.tsx`**

```typescript
'use client'

import { useEffect, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { connectSSE, type SSEEvent } from '@/lib/sse'
import { apiFetch } from '@/lib/api'
import { Button } from './ui/button'

type EventLine = {
  id: string
  type: string
  content: string
  badge: string
  badgeClass: string
}

const EVENT_CONFIG: Record<string, { badge: string; badgeClass: string }> = {
  plan_created:       { badge: 'events.plan',    badgeClass: 'bg-blue-100 text-blue-700' },
  plan_updated:       { badge: 'events.plan',    badgeClass: 'bg-blue-100 text-blue-700' },
  think:              { badge: 'events.think',   badgeClass: 'bg-purple-100 text-purple-700' },
  tool_call:          { badge: 'events.tool',    badgeClass: 'bg-amber-100 text-amber-700' },
  tool_result:        { badge: 'events.result',  badgeClass: 'bg-green-100 text-green-700' },
  context_summarized: { badge: 'events.summary', badgeClass: 'bg-slate-100 text-slate-600' },
  task_completed:     { badge: 'events.done',    badgeClass: 'bg-green-100 text-green-700' },
  task_failed:        { badge: 'events.error',   badgeClass: 'bg-red-100 text-red-700' },
  task_cancelled:     { badge: 'events.error',   badgeClass: 'bg-red-100 text-red-700' },
}

function extractContent(type: string, data: unknown): string {
  if (!data || typeof data !== 'object') return String(data ?? '')
  const d = data as Record<string, unknown>
  if (type === 'think') return String(d.content ?? '')
  if (type === 'tool_call') return `${d.tool as string}(${JSON.stringify(d.params)})`
  if (type === 'tool_result') return `${d.tool as string} → ${d.duration_ms as number}ms`
  if (type === 'plan_created' || type === 'plan_updated') {
    const tasks = (d.tasks as Array<{ title: string }> | undefined) ?? []
    return `${tasks.length} sub-task(s): ${tasks.map((t) => t.title).join(', ')}`
  }
  if (type === 'task_completed') return String(d.summary ?? 'Task completed')
  if (type === 'task_failed') return String(d.error ?? 'Task failed')
  if (type === 'context_summarized') return `${d.tokens_freed as number} tokens freed`
  return JSON.stringify(data)
}

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled'])

export function TaskFeed({
  taskId,
  status: initialStatus,
  goal,
}: {
  taskId: string
  status: string
  goal: string
}) {
  const t = useTranslations()
  const [lines, setLines] = useState<EventLine[]>([])
  const [status, setStatus] = useState(initialStatus)
  const [confidence, setConfidence] = useState<number | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const userScrolled = useRef(false)
  const feedRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!userScrolled.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [lines])

  useEffect(() => {
    function handleScroll() {
      const el = feedRef.current
      if (!el) return
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50
      userScrolled.current = !atBottom
    }
    feedRef.current?.addEventListener('scroll', handleScroll)
    return () => feedRef.current?.removeEventListener('scroll', handleScroll)
  }, [])

  useEffect(() => {
    // For completed tasks, omitting Last-Event-ID causes the backend to replay from step 0,
    // then return once it detects the task is terminal — same URL works for both cases.
    const url = `/api/v1/tasks/${taskId}/stream`

    const disconnect = connectSSE(url, {
      onEvent: (event: SSEEvent) => {
        const cfg = EVENT_CONFIG[event.type]
        if (!cfg) return
        const content = extractContent(event.type, event.data)
        setLines((prev) => [
          ...prev,
          { id: event.id, type: event.type, content, badge: cfg.badge, badgeClass: cfg.badgeClass },
        ])
        if (event.type === 'plan_updated' || event.type === 'plan_created') {
          const d = event.data as Record<string, unknown>
          if (typeof d.confidence === 'number') setConfidence(d.confidence)
        }
        if (event.type === 'task_completed') setStatus('completed')
        if (event.type === 'task_failed') setStatus('failed')
      },
    })
    return disconnect
  }, [taskId, initialStatus])

  async function handleCancel() {
    setIsCancelling(true)
    await apiFetch(`/api/v1/tasks/${taskId}`, { method: 'DELETE' })
    setStatus('cancelled')
    setIsCancelling(false)
  }

  const isActive = !TERMINAL_STATUSES.has(status)

  return (
    <div className="flex flex-col h-full gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="font-medium text-foreground truncate max-w-xl">{goal}</p>
          <p className={`text-sm mt-0.5 ${isActive ? 'text-primary' : 'text-muted-foreground'}`}>
            {isActive ? '● ' : ''}{t(`tasks.status.${status}` as Parameters<typeof t>[0])}
          </p>
        </div>
        {isActive && (
          <Button
            variant="destructive"
            size="sm"
            onClick={handleCancel}
            disabled={isCancelling}
            aria-label="cancel"
          >
            {t('tasks.cancel')}
          </Button>
        )}
      </div>

      {/* Feed */}
      <div
        ref={feedRef}
        className="flex-1 overflow-y-auto rounded-lg border border-border bg-card p-4 space-y-2 min-h-[400px] max-h-[600px]"
      >
        {lines.map((line, i) => (
          <div key={`${line.id}-${i}`} className="flex gap-3 items-start text-sm">
            <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-mono font-semibold ${line.badgeClass}`}>
              {t(line.badge as Parameters<typeof t>[0])}
            </span>
            <span className="text-foreground break-words">{line.content}</span>
          </div>
        ))}
        {isActive && lines.length === 0 && (
          <p className="text-muted-foreground text-sm">Connecting…</p>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Confidence bar */}
      {confidence !== null && (
        <div className="flex items-center gap-3 text-sm">
          <span className="text-muted-foreground">{t('tasks.confidence')}</span>
          <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
            <div
              className="h-full bg-success rounded-full transition-all duration-500"
              style={{ width: `${confidence * 100}%` }}
            />
          </div>
          <span className="text-muted-foreground">{Math.round(confidence * 100)}%</span>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npx vitest run components/__tests__/task-feed.test.tsx
```

Expected: PASS (4 tests)

- [ ] **Step 5: Create `app/[locale]/tasks/[id]/page.tsx`**

```typescript
import { notFound } from 'next/navigation'
import { TaskFeed } from '@/components/task-feed'

type Task = { id: string; goal: string; status: string }

async function getTask(taskId: string): Promise<Task | null> {
  try {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/api/v1/tasks/${taskId}`,
      { cache: 'no-store' }
    )
    if (res.status === 404) return null
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

export default async function TaskPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>
}) {
  const { id } = await params
  const task = await getTask(id)
  if (!task) notFound()

  return (
    <div className="h-full">
      <TaskFeed taskId={task.id} status={task.status} goal={task.goal} />
    </div>
  )
}
```

- [ ] **Step 6: Run all tests**

```bash
npx vitest run
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add components/task-feed.tsx components/__tests__/task-feed.test.tsx app/[locale]/tasks/[id]/page.tsx
git commit -m "feat: live task trace (Terminal Feed SSE + backoff + Last-Event-ID)"
```

---

## Task 14: Settings page `/settings`

**Files:**
- Create: `frontend/app/[locale]/settings/page.tsx`

- [ ] **Step 1: Create `app/[locale]/settings/page.tsx`**

```typescript
'use client'

import { useState, useEffect } from 'react'
import { useTranslations } from 'next-intl'
import { useRouter } from '@/i18n/navigation'
import { apiFetch } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ThemeSwitcher } from '@/components/theme-switcher'

type ApiKey = { id: string; label: string | null; created_at: string; last_used_at: string | null }
type UserProfile = { name: string | null; email: string; language: string; role: string }

export default function SettingsPage() {
  const t = useTranslations('settings')
  const router = useRouter()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [tokenUsage, setTokenUsage] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [language, setLanguage] = useState<'fr' | 'en'>('fr')
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([])
  const [newKeyName, setNewKeyName] = useState('')
  const [newKeyValue, setNewKeyValue] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    apiFetch('/api/v1/auth/users/me')
      .then((r) => r.json())
      .then((p: UserProfile & { token_used_this_month?: number }) => {
        setProfile(p)
        setName(p.name ?? '')
        setLanguage(p.language as 'fr' | 'en')
      })
      .catch(() => {})

    apiFetch('/api/v1/auth/api-keys')
      .then((r) => r.json())
      .then((keys: ApiKey[]) => setApiKeys(keys))
      .catch(() => {})

    apiFetch('/api/v1/auth/users/me/usage')
      .then((r) => r.json())
      .then((u: { token_used_this_month: number }) => setTokenUsage(u.token_used_this_month))
      .catch(() => {})
  }, [])

  async function saveProfile() {
    setIsSaving(true)
    const res = await apiFetch('/api/v1/auth/users/me', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, language }),
    })
    setIsSaving(false)
    if (res.ok && language !== profile?.language) {
      router.replace('/settings', { locale: language })
    }
  }

  async function createApiKey() {
    if (!newKeyName.trim()) return
    const res = await apiFetch('/api/v1/auth/api-keys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label: newKeyName }),  // backend field is `label`, not `name`
    })
    if (res.ok) {
      const data = await res.json()
      setNewKeyValue(data.key as string)
      setNewKeyName('')
      const keysRes = await apiFetch('/api/v1/auth/api-keys')
      if (keysRes.ok) setApiKeys(await keysRes.json())
    }
  }

  async function revokeKey(id: string) {
    await apiFetch(`/api/v1/auth/api-keys/${id}`, { method: 'DELETE' })
    setApiKeys((prev) => prev.filter((k) => k.id !== id))
  }

  return (
    <div className="max-w-2xl space-y-10">
      <h1 className="text-2xl font-bold">{t('title')}</h1>

      {/* Language */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">{t('language')}</h2>
        <div className="flex gap-3">
          {(['fr', 'en'] as const).map((locale) => (
            <Button
              key={locale}
              variant={language === locale ? 'default' : 'outline'}
              size="sm"
              onClick={() => setLanguage(locale)}
            >
              {locale === 'fr' ? 'Français' : 'English'}
            </Button>
          ))}
        </div>
      </section>

      {/* Theme */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">{t('theme')}</h2>
        <ThemeSwitcher />
      </section>

      {/* Save profile */}
      <section className="space-y-3">
        <Label htmlFor="name">Nom</Label>
        <Input
          id="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="max-w-sm"
        />
        <Button onClick={saveProfile} disabled={isSaving}>
          {t('save')}
        </Button>
      </section>

      {/* API Keys */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">{t('apiKeys')}</h2>
        {newKeyValue && (
          <div className="p-3 rounded bg-secondary border border-border text-sm font-mono break-all">
            {newKeyValue}
            <p className="text-muted-foreground text-xs mt-1">Copiez cette clé maintenant — elle ne sera plus affichée.</p>
          </div>
        )}
        <div className="flex gap-2 max-w-sm">
          <Input
            placeholder={t('apiKeysNewLabel')}
            value={newKeyName}
            onChange={(e) => setNewKeyName(e.target.value)}
          />
          <Button onClick={createApiKey} variant="outline" size="sm">{t('apiKeysNew')}</Button>
        </div>
        <div className="space-y-2">
          {apiKeys.map((key) => (
            <div key={key.id} className="flex items-center justify-between p-3 rounded border border-border bg-card">
              <div>
                <p className="text-sm font-medium">{key.label ?? '—'}</p>
                <p className="text-xs text-muted-foreground">{new Date(key.created_at).toLocaleDateString()}</p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => revokeKey(key.id)} className="text-destructive">
                {t('apiKeysRevoke')}
              </Button>
            </div>
          ))}
        </div>
      </section>

      {/* Token usage */}
      {tokenUsage !== null && (
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">{t('usage')}</h2>
          <p className="text-sm text-muted-foreground">{t('usageThisMonth')}</p>
          <p className="text-3xl font-bold">{tokenUsage.toLocaleString()}</p>
        </section>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add app/[locale]/settings/page.tsx
git commit -m "feat: settings page (language, theme, API keys, token usage)"
```

---

## Task 15: Backend — `GET/PATCH /users/me` + `GET /users/me/usage`

**Files:**
- Create: `backend/tests/test_auth/test_users_me.py`
- Modify: `backend/app/routers/auth.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_auth/test_users_me.py`:

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_users_me_returns_profile(auth_client: AsyncClient):
    """Authenticated user can retrieve their profile."""
    res = await auth_client.get("/api/v1/auth/users/me")
    assert res.status_code == 200
    data = res.json()
    assert "id" in data
    assert "email" in data
    assert "name" in data
    assert "language" in data
    assert "token_used_this_month" not in data  # usage has its own endpoint


@pytest.mark.asyncio
async def test_get_users_me_unauthenticated(client: AsyncClient):
    """Unauthenticated request returns 401."""
    res = await client.get("/api/v1/auth/users/me")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_patch_users_me_updates_name(auth_client: AsyncClient):
    """User can update their name."""
    res = await auth_client.patch(
        "/api/v1/auth/users/me",
        json={"name": "Alice Updated"},
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Alice Updated"


@pytest.mark.asyncio
async def test_patch_users_me_updates_language(auth_client: AsyncClient):
    """User can update their language preference."""
    res = await auth_client.patch(
        "/api/v1/auth/users/me",
        json={"language": "en"},
    )
    assert res.status_code == 200
    assert res.json()["language"] == "en"


@pytest.mark.asyncio
async def test_patch_users_me_rejects_invalid_language(auth_client: AsyncClient):
    """Invalid language code returns 422."""
    res = await auth_client.patch(
        "/api/v1/auth/users/me",
        json={"language": "de"},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_get_users_me_usage(auth_client: AsyncClient):
    """Usage endpoint returns token count for current month."""
    res = await auth_client.get("/api/v1/auth/users/me/usage")
    assert res.status_code == 200
    data = res.json()
    assert "token_used_this_month" in data
    assert isinstance(data["token_used_this_month"], int)
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd backend && pytest tests/test_auth/test_users_me.py -v
```

Expected: FAIL — 404 Not Found for all endpoints.

- [ ] **Step 3: Add new Pydantic schemas to `backend/app/schemas/auth.py`**

`UserResponse` already exists (id, email, name, role, language) — reuse it for the profile responses. Append only the two missing schemas:

```python
from typing import Literal, Optional


class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    language: Optional[Literal["fr", "en"]] = None


class UserUsageResponse(BaseModel):
    token_used_this_month: int
```

- [ ] **Step 4: Add endpoints to `backend/app/routers/auth.py`**

Add these three routes after the existing `/api-keys` routes:

```python
from app.schemas.auth import UserResponse, UserProfileUpdate, UserUsageResponse


@router.get("/users/me", response_model=UserResponse)
async def get_current_user_profile(
    user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        language=user.language,
        role=user.role.value,
    )


@router.patch("/users/me", response_model=UserResponse)
async def update_current_user_profile(
    body: UserProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    if body.name is not None:
        user.name = body.name
    if body.language is not None:
        user.language = body.language
    await db.flush()
    await db.refresh(user)
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        language=user.language,
        role=user.role.value,
    )


@router.get("/users/me/usage", response_model=UserUsageResponse)
async def get_current_user_usage(
    user: User = Depends(get_current_user),
) -> UserUsageResponse:
    return UserUsageResponse(token_used_this_month=user.token_used_this_month or 0)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_auth/test_users_me.py -v
```

Expected: PASS (6 tests)

- [ ] **Step 6: Run full backend test suite**

```bash
pytest --tb=short -q
```

Expected: All existing tests still pass.

- [ ] **Step 7: Commit backend changes**

```bash
cd backend
git add app/routers/auth.py app/schemas/auth.py tests/test_auth/test_users_me.py
git commit -m "feat: GET/PATCH /users/me + GET /users/me/usage endpoints"
```

---

## Task 16: Dockerfile + docker-compose integration

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/.dockerignore`
- Modify: `agentis/docker-compose.yml`

- [ ] **Step 1: Create `frontend/Dockerfile`**

```dockerfile
# --- deps ---
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# --- builder ---
FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# --- runner ---
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
```

- [ ] **Step 2: Enable `output: 'standalone'` in `next.config.ts`**

```typescript
const nextConfig: NextConfig = {
  output: 'standalone',
}
```

- [ ] **Step 3: Create `frontend/.dockerignore`**

```
node_modules
.next
.git
*.md
```

- [ ] **Step 4: Add `ui` service to `agentis/docker-compose.yml`**

Find the `services:` section and add:

```yaml
  ui:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_URL: http://api:8000
      NEXT_PUBLIC_DEFAULT_LOCALE: fr
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped
```

- [ ] **Step 5: Verify Docker build**

```bash
cd agentis/frontend
docker build -t agentis-ui .
```

Expected: Build completes successfully.

- [ ] **Step 6: Commit**

```bash
# In frontend repo
git add Dockerfile .dockerignore next.config.ts
git commit -m "feat: multi-stage Dockerfile (standalone output)"

# In parent repo
git add docker-compose.yml
git commit -m "feat: add ui service to docker-compose"
```

---

## Task 17: Final verification

- [ ] **Step 1: Run full frontend test suite**

```bash
cd agentis/frontend
npx vitest run
```

Expected: All tests pass (lib/auth, lib/api, lib/sse, components/task-form, components/task-feed).

- [ ] **Step 2: Run full backend test suite**

```bash
cd agentis/backend
pytest --tb=short -q
```

Expected: All tests pass including new `/users/me` tests.

- [ ] **Step 3: Start full stack**

```bash
cd agentis
docker compose up
```

Expected: Services start — `api` healthy, `ui` reachable at `http://localhost:3000`.

- [ ] **Step 4: Smoke test golden path**

1. Navigate to `http://localhost:3000` → should redirect to `/fr`
2. Click "Connexion" → login with test credentials
3. Submit a task from the home page → redirected to `/tasks/{id}`
4. Watch SSE events stream in Terminal Feed
5. Navigate to `/tâches` → task appears in history
6. Navigate to `/paramètres` → profile, theme, API keys visible
7. Switch theme → page updates instantly
8. Switch language to EN → page re-renders in English

- [ ] **Step 5: Update Phase 1D roadmap entry**

In `agentis/docs/agentis_spec.md`, mark Phase 1D items complete:

```
- [x] Next.js 15 UI: task submission, SSE live trace, task history — phase-1d
- [x] English + French UI (next-intl) and agent prompts — phase-1d
```

- [ ] **Step 6: Commit**

```bash
cd agentis
git add docs/agentis_spec.md
git commit -m "docs: mark Phase 1D items complete in roadmap tracking"
```
