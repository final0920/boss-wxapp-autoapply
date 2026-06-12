import { useSession } from '../lib/device-context'
import { useI18n } from '../lib/i18n'
import { Badge } from './ui'

export function DeviceSidebar() {
  const { t } = useI18n()
  const { session } = useSession()

  const ready = session?.ready ?? false

  return (
    <div className="w-52 border-r border-border/60 bg-sidebar flex flex-col shadow-shell-sidebar shrink-0">
      <div className="px-4 py-3 border-b border-border/40 flex items-center gap-2">
        <span className="font-serif text-sm font-semibold text-primary flex-1">
          {t.device.title}
        </span>
        <Badge variant={ready ? 'success' : 'default'}>
          {ready ? t.device.status.online : t.device.status.offline}
        </Badge>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {session === null ? (
          <div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
            <span className="text-xs text-muted-foreground animate-pulse">{t.common.loading}</span>
          </div>
        ) : ready ? (
          <div className="space-y-2">
            <div className="rounded-xl border border-border/60 bg-card p-3 space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="inline-block w-2 h-2 rounded-full bg-success shrink-0" />
                <span className="text-sm font-semibold truncate flex-1">{t.device.sessionReady}</span>
              </div>
              {session.title && (
                <p className="text-xs text-muted-foreground truncate pl-4" title={session.title}>
                  {session.title}
                </p>
              )}
              {session.rect && (
                <p className="text-xs text-muted-foreground font-mono pl-4">
                  {session.rect.w} x {session.rect.h}
                </p>
              )}
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center gap-3 py-8 text-center">
            <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center text-muted-foreground/50">
              {/* miniprogram icon */}
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="5" y="2" width="14" height="20" rx="2" />
                <line x1="12" y1="18" x2="12" y2="18.01" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </div>
            <p className="text-xs text-muted-foreground leading-snug px-2">
              {session.reason ?? t.device.noDevice}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
