interface TokenUsageBarProps {
  used: number
  limit: number
  label?: string
}

export function TokenUsageBar({ used, limit, label = 'Tokens ce mois' }: TokenUsageBarProps) {
  const pct = Math.min(100, Math.round((used / (limit || 1)) * 100))
  const color = pct > 85 ? 'bg-destructive' : pct > 60 ? 'bg-yellow-500' : 'bg-primary'

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium">
          {(used / 1_000_000).toFixed(1)}M / {(limit / 1_000_000).toFixed(0)}M
        </span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <p className="text-xs text-muted-foreground text-right">{pct}% utilisé</p>
    </div>
  )
}
