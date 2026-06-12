'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/lib/auth'
import { AdminSidebar } from '@/components/admin/AdminSidebar'

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const role = useAuthStore((s) => s.role)
  const accessToken = useAuthStore((s) => s.accessToken)
  const router = useRouter()

  useEffect(() => {
    // Only redirect once we know auth state (accessToken not null means we've checked)
    if (accessToken !== null && !['admin', 'operator'].includes(role ?? '')) {
      router.replace('/')
    }
  }, [role, accessToken, router])

  if (!accessToken || !['admin', 'operator'].includes(role ?? '')) {
    return null  // Render nothing while checking or redirecting
  }

  return (
    <div className="flex min-h-screen">
      <AdminSidebar />
      <main className="flex-1 p-6 overflow-auto">{children}</main>
    </div>
  )
}
