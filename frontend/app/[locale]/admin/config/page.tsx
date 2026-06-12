'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { useAuthStore } from '@/lib/auth'
import { useAdminConfig, useUpdateAdminConfig } from '@/hooks/useAdminConfig'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const PROVIDERS = ['anthropic', 'openai', 'mistral', 'groq', 'deepseek', 'ollama'] as const

export default function AdminConfigPage() {
  const t = useTranslations('admin.config')
  const role = useAuthStore((s) => s.role)
  const router = useRouter()

  // Operator-only: redirect non-operators
  useEffect(() => {
    if (role !== null && role !== 'operator') {
      router.replace('/admin')
    }
  }, [role, router])

  const { data, isLoading, error } = useAdminConfig(role)
  const update = useUpdateAdminConfig()

  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [saved, setSaved] = useState(false)

  // Populate form once data loads
  useEffect(() => {
    if (data) {
      setProvider(data.provider)
      setModel(data.model)
      setBaseUrl(data.base_url)
      // Don't pre-fill the api_key field — show masked placeholder only
    }
  }, [data])

  if (role !== null && role !== 'operator') {
    return null
  }

  if (isLoading) {
    return <div className="text-muted-foreground text-sm">Loading…</div>
  }

  if (error) {
    return (
      <div className="text-destructive text-sm">
        {(error as Error).message}
      </div>
    )
  }

  const showBaseUrl = provider === 'ollama' || (data?.base_url && data.base_url.length > 0) || baseUrl.length > 0

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaved(false)

    const patch: Record<string, string> = { provider, model, base_url: baseUrl }
    if (apiKey.trim()) {
      patch.api_key = apiKey.trim()
    }

    try {
      await update.mutateAsync(patch)
      setApiKey('')
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch {
      // update.error already set by TanStack Query
    }
  }

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-bold">{t('title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
      </div>

      {update.error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {(update.error as Error).message}
        </div>
      )}

      {saved && (
        <div className="rounded-md border border-green-500/40 bg-green-500/10 px-4 py-2 text-sm text-green-400">
          {t('saved')}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Provider */}
        <div className="space-y-1.5">
          <Label htmlFor="provider">{t('provider')}</Label>
          <select
            id="provider"
            value={provider}
            onChange={(e) => {
              setProvider(e.target.value)
              if (e.target.value !== 'ollama') setBaseUrl('')
            }}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>

        {/* Model */}
        <div className="space-y-1.5">
          <Label htmlFor="model">{t('model')}</Label>
          <Input
            id="model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="claude-sonnet-4-5-20251022"
          />
        </div>

        {/* API Key */}
        <div className="space-y-1.5">
          <Label htmlFor="apiKey">{t('apiKey')}</Label>
          <Input
            id="apiKey"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={
              data?.api_key_masked && data.api_key_masked.length > 0
                ? data.api_key_masked
                : t('apiKeyPlaceholder')
            }
            autoComplete="new-password"
          />
          <p className="text-xs text-muted-foreground">{t('apiKeyPlaceholder')}</p>
        </div>

        {/* Base URL — shown for ollama or when a value exists */}
        {showBaseUrl && (
          <div className="space-y-1.5">
            <Label htmlFor="baseUrl">{t('baseUrl')}</Label>
            <Input
              id="baseUrl"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http://ollama:11434"
            />
            <p className="text-xs text-muted-foreground">{t('baseUrlHint')}</p>
          </div>
        )}

        <Button type="submit" disabled={update.isPending}>
          {update.isPending ? '…' : t('save')}
        </Button>
      </form>
    </div>
  )
}
