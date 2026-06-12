'use client'

import { Link, usePathname } from '@/i18n/navigation'
import { LayoutDashboard, Users, ScrollText, Wrench, Settings2, Building2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/lib/auth'
import { useTranslations } from 'next-intl'

export function AdminSidebar() {
  const pathname = usePathname()
  const role = useAuthStore((s) => s.role)
  const t = useTranslations('admin')

  const navItems = [
    { href: '/admin', label: t('nav.dashboard'), icon: LayoutDashboard, operatorOnly: false },
    { href: '/admin/users', label: t('nav.users'), icon: Users, operatorOnly: false },
    { href: '/admin/orgs', label: t('nav.orgs'), icon: Building2, operatorOnly: false },
    { href: '/admin/audit', label: t('nav.audit'), icon: ScrollText, operatorOnly: false },
    { href: '/admin/tools', label: t('nav.tools'), icon: Wrench, operatorOnly: false },
    { href: '/admin/config', label: t('config.navLabel'), icon: Settings2, operatorOnly: true },
  ]

  const visibleItems = navItems.filter(
    (item) => !item.operatorOnly || role === 'operator'
  )

  return (
    <aside className="w-52 shrink-0 border-r border-border bg-card flex flex-col min-h-screen">
      <div className="px-4 py-4 border-b border-border">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Agentis · Admin
        </span>
      </div>
      <nav className="flex-1 p-2 space-y-0.5">
        {visibleItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || (href !== '/admin' && pathname.includes(href))
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors',
                active
                  ? 'bg-primary/10 text-primary font-medium'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              )}
            >
              <Icon size={16} />
              {label}
            </Link>
          )
        })}
      </nav>
    </aside>
  )
}
