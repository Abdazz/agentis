'use client'

import { useTranslations } from 'next-intl'
import { Link, useRouter, usePathname } from '@/i18n/navigation'
import { ThemeSwitcher } from './theme-switcher'
import { Button } from './ui/button'
import { useAuthStore } from '@/lib/auth'
import { apiFetch } from '@/lib/api'

export function Nav() {
  const t = useTranslations('nav')
  const token = useAuthStore((s) => s.accessToken)
  const role = useAuthStore((s) => s.role)
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
            <Link href="/marketplace" className="text-sm text-muted-foreground hover:text-foreground">
              {t('marketplace')}
            </Link>
            <Link href="/settings" className="text-sm text-muted-foreground hover:text-foreground">
              {t('settings')}
            </Link>
            {['admin', 'operator'].includes(role ?? '') && (
              <Link href="/admin" className="text-sm text-muted-foreground hover:text-foreground">
                Admin
              </Link>
            )}
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
