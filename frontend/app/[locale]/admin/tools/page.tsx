'use client'

import { useTranslations } from 'next-intl'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useAdminTools, useToggleTool } from '@/hooks/useAdminTools'

const sourceBadgeVariant: Record<string, 'default' | 'secondary' | 'outline'> = {
  builtin: 'default',
  mcp: 'secondary',
  openapi: 'outline',
}

export default function AdminToolsPage() {
  const t = useTranslations('admin.tools')
  const { data: tools, isLoading, error } = useAdminTools()
  const toggle = useToggleTool()

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

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">{t('title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
      </div>

      {toggle.error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {(toggle.error as Error).message}
        </div>
      )}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t('name')}</TableHead>
            <TableHead>{t('source')}</TableHead>
            <TableHead>{t('status')}</TableHead>
            <TableHead>{t('restrictions')}</TableHead>
            <TableHead className="text-right">{t('actions')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {(!tools || tools.length === 0) && (
            <TableRow>
              <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                {t('empty')}
              </TableCell>
            </TableRow>
          )}
          {(tools ?? []).map((tool) => (
            <TableRow key={tool.name}>
              <TableCell className="font-mono text-sm">{tool.name}</TableCell>
              <TableCell>
                <Badge variant={sourceBadgeVariant[tool.source] ?? 'outline'}>
                  {tool.source}
                </Badge>
              </TableCell>
              <TableCell>
                <span
                  className={
                    tool.enabled_globally
                      ? 'inline-flex items-center px-2 py-0.5 rounded text-xs border bg-green-500/15 text-green-400 border-green-500/30'
                      : 'inline-flex items-center px-2 py-0.5 rounded text-xs border bg-red-500/15 text-red-400 border-red-500/30'
                  }
                >
                  {tool.enabled_globally ? t('enabled') : t('disabled')}
                </span>
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {tool.allowed_orgs && tool.allowed_orgs.length > 0
                  ? tool.allowed_orgs.join(', ')
                  : t('noRestrictions')}
              </TableCell>
              <TableCell className="text-right">
                <Button
                  size="sm"
                  variant={tool.enabled_globally ? 'destructive' : 'default'}
                  disabled={toggle.isPending && toggle.variables?.name === tool.name}
                  onClick={() =>
                    toggle.mutate({ name: tool.name, enabled: !tool.enabled_globally })
                  }
                >
                  {tool.enabled_globally ? t('disable') : t('enable')}
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
