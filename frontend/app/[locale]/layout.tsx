import { NextIntlClientProvider } from 'next-intl'
import { getMessages } from 'next-intl/server'
import { notFound } from 'next/navigation'
import { Geist } from 'next/font/google'
import { routing } from '@/i18n/routing'
import { Providers } from '@/components/providers'
import { AuthInitializer } from '@/components/auth-initializer'
import { Nav } from '@/components/nav'
import '@/app/globals.css'

const geist = Geist({ subsets: ['latin'], variable: '--font-sans' })

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
    <html lang={locale} suppressHydrationWarning className={geist.variable}>
      <body className="bg-background text-foreground min-h-screen">
        <NextIntlClientProvider messages={messages}>
          <Providers>
            <AuthInitializer />
            <Nav />
            <main className="max-w-5xl mx-auto px-4 py-8">
              {children}
            </main>
          </Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  )
}
