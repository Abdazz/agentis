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
      body: JSON.stringify({ label: newKeyName }),
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
