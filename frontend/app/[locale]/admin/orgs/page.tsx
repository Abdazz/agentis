'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useAdminOrgs, useCreateOrg, useDeleteOrg } from '@/hooks/useAdminOrgs'

export default function AdminOrgsPage() {
  const t = useTranslations('admin.orgs')
  const { data, isLoading, error } = useAdminOrgs()
  const createOrg = useCreateOrg()
  const deleteOrg = useDeleteOrg()

  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')

  if (isLoading) return <div className="text-muted-foreground text-sm">Loading…</div>
  if (error) return <div className="text-destructive text-sm">{(error as Error).message}</div>

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !slug.trim()) return
    createOrg.mutate(
      { name: name.trim(), slug: slug.trim() },
      { onSuccess: () => { setName(''); setSlug('') } }
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t('title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
      </div>

      <form onSubmit={handleCreate} className="flex items-end gap-3">
        <div className="space-y-1">
          <label className="text-sm font-medium">{t('nameLabel')}</label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('namePlaceholder')}
            className="w-48"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">{t('slugLabel')}</label>
          <Input
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder={t('slugPlaceholder')}
            className="w-40"
          />
        </div>
        <Button type="submit" disabled={createOrg.isPending}>
          {t('create')}
        </Button>
      </form>

      {createOrg.error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {(createOrg.error as Error).message}
        </div>
      )}
      {deleteOrg.error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {(deleteOrg.error as Error).message}
        </div>
      )}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t('name')}</TableHead>
            <TableHead>{t('slug')}</TableHead>
            <TableHead>{t('members')}</TableHead>
            <TableHead>{t('tokenBudget')}</TableHead>
            <TableHead className="text-right">{t('actions')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {(!data?.items || data.items.length === 0) && (
            <TableRow>
              <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                {t('empty')}
              </TableCell>
            </TableRow>
          )}
          {(data?.items ?? []).map((org) => (
            <TableRow key={org.id}>
              <TableCell className="font-medium">{org.name}</TableCell>
              <TableCell className="font-mono text-sm">{org.slug}</TableCell>
              <TableCell>{org.member_count}</TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {org.token_budget_monthly != null
                  ? org.token_budget_monthly.toLocaleString()
                  : t('noLimit')}
              </TableCell>
              <TableCell className="text-right">
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={deleteOrg.isPending && deleteOrg.variables === org.id}
                  onClick={() => deleteOrg.mutate(org.id)}
                >
                  {t('delete')}
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
