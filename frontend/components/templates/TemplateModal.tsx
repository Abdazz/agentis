'use client'

import { useState, useMemo } from 'react'
import { useTranslations } from 'next-intl'
import { LayoutTemplate } from 'lucide-react'

import { useTemplates, type TaskTemplate } from '@/hooks/useTemplates'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface TemplateModalProps {
  onSelect: (goalTemplate: string) => void
}

export function TemplateModal({ onSelect }: TemplateModalProps) {
  const t = useTranslations('home')
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')

  const { data: templates = [], isLoading, isError } = useTemplates()

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return templates
    return templates.filter(
      (tpl) =>
        tpl.name.toLowerCase().includes(q) ||
        (tpl.description?.toLowerCase().includes(q) ?? false)
    )
  }, [templates, search])

  const grouped = useMemo(() => {
    const map = new Map<string, TaskTemplate[]>()
    for (const tpl of filtered) {
      const cat = tpl.category ?? t('templateModal.general')
      if (!map.has(cat)) map.set(cat, [])
      map.get(cat)!.push(tpl)
    }
    return map
  }, [filtered, t])

  function handleSelect(tpl: TaskTemplate) {
    onSelect(tpl.goal_template)
    setOpen(false)
    setSearch('')
  }

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        aria-label={t('useTemplate')}
      >
        <LayoutTemplate className="h-4 w-4" />
        {t('useTemplate')}
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[80vh] overflow-hidden flex flex-col sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('templateModal.title')}</DialogTitle>
          </DialogHeader>

          <div className="mt-3">
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('templateModal.search')}
              className="w-full"
            />
          </div>

          <div className="mt-4 flex-1 overflow-y-auto pr-1 space-y-6">
            {isLoading && (
              <p className="text-sm text-muted-foreground text-center py-8">
                {t('templateModal.loading')}
              </p>
            )}

            {isError && (
              <p className="text-sm text-destructive text-center py-8">
                {t('templateModal.error')}
              </p>
            )}

            {!isLoading && !isError && grouped.size === 0 && (
              <p className="text-sm text-muted-foreground text-center py-8">
                {t('templateModal.empty')}
              </p>
            )}

            {Array.from(grouped.entries()).map(([category, items]) => (
              <div key={category}>
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                  {category}
                </p>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {items.map((tpl) => (
                    <button
                      key={tpl.id}
                      type="button"
                      onClick={() => handleSelect(tpl)}
                      className="text-left rounded-lg border border-border bg-card p-3 hover:bg-secondary hover:border-primary/30 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    >
                      <p className="text-sm font-medium text-foreground leading-snug">
                        {tpl.name}
                      </p>
                      {tpl.description && (
                        <p className="mt-0.5 text-xs text-muted-foreground line-clamp-1">
                          {tpl.description}
                        </p>
                      )}
                      <p className="mt-1.5 text-xs text-muted-foreground/70 line-clamp-2 font-mono">
                        {tpl.goal_template}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
