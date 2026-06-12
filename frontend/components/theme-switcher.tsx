'use client'

import { useTheme } from 'next-themes'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'

const THEMES = [
  { value: 'light', labelKey: 'themeLight' },
  { value: 'dark-pro', labelKey: 'themeDarkPro' },
  { value: 'dark-accent', labelKey: 'themeDarkAccent' },
] as const

export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme()
  const t = useTranslations('settings')

  return (
    <div className="flex gap-2">
      {THEMES.map(({ value, labelKey }) => (
        <Button
          key={value}
          variant={theme === value ? 'default' : 'outline'}
          size="sm"
          onClick={() => setTheme(value)}
        >
          {t(labelKey)}
        </Button>
      ))}
    </div>
  )
}
