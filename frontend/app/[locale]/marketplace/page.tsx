'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { useAuthStore } from '@/lib/auth'
import { useMarketplacePlugins, useInstallPlugin, MarketplacePlugin } from '@/hooks/useMarketplace'

type Tab = 'available' | 'installed'

function SourceBadge({ sourceType }: { sourceType: string }) {
  if (sourceType === 'mcp') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs border bg-blue-500/15 text-blue-400 border-blue-500/30">
        MCP
      </span>
    )
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs border bg-purple-500/15 text-purple-400 border-purple-500/30">
      OpenAPI
    </span>
  )
}

function PluginCard({
  plugin,
  isAdmin,
  t,
}: {
  plugin: MarketplacePlugin
  isAdmin: boolean
  t: ReturnType<typeof useTranslations<'marketplace'>>
}) {
  const install = useInstallPlugin()
  const isPendingThis = install.isPending && install.variables === plugin.slug

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <SourceBadge sourceType={plugin.source_type} />
            <span className="font-semibold text-sm">{plugin.name}</span>
          </div>
          {plugin.installed && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs border bg-green-500/15 text-green-400 border-green-500/30">
              {t('installed')} ✓
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          {t('by')} {plugin.author}
        </p>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="flex items-end justify-between gap-4">
          <p className="text-sm text-muted-foreground">{plugin.description}</p>
          {isAdmin && !plugin.installed && (
            <Button
              size="sm"
              variant="default"
              disabled={isPendingThis}
              onClick={() => install.mutate(plugin.slug)}
              className="shrink-0"
            >
              {isPendingThis ? t('installing') : t('install')}
            </Button>
          )}
        </div>
        {install.error && install.variables === plugin.slug && (
          <p className="text-xs text-destructive mt-2">{t('installError')}</p>
        )}
      </CardContent>
    </Card>
  )
}

export default function MarketplacePage() {
  const t = useTranslations('marketplace')
  const [tab, setTab] = useState<Tab>('available')
  const role = useAuthStore((s) => s.role)
  const isAdmin = ['admin', 'operator'].includes(role ?? '')

  const { data: plugins, isLoading, error } = useMarketplacePlugins(
    tab === 'available' ? false : true
  )

  const tabClass = (active: boolean) =>
    `px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
      active
        ? 'border-primary text-foreground'
        : 'border-transparent text-muted-foreground hover:text-foreground'
    }`

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t('title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border">
        <button
          className={tabClass(tab === 'available')}
          onClick={() => setTab('available')}
        >
          {t('tabAvailable')}
        </button>
        <button
          className={tabClass(tab === 'installed')}
          onClick={() => setTab('installed')}
        >
          {t('tabInstalled')}
        </button>
      </div>

      {/* Content */}
      {isLoading && (
        <div className="text-muted-foreground text-sm">{t('loading')}</div>
      )}

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}

      {!isLoading && !error && (
        <>
          {(!plugins || plugins.length === 0) ? (
            <p className="text-sm text-muted-foreground py-8 text-center">{t('empty')}</p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {plugins.map((plugin) => (
                <PluginCard
                  key={plugin.id}
                  plugin={plugin}
                  isAdmin={isAdmin}
                  t={t}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
