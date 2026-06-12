import { useEffect, useState, useRef } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { useSession } from '../lib/device-context'
import { useI18n } from '../lib/i18n'
import { Card, CardContent } from '../components/ui'
import { apiGet } from '../api'

const SCREENSHOT_INTERVAL_MS = 1500

function ScreenPage() {
  const { t } = useI18n()
  const { session } = useSession()
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const ready = session?.ready ?? false

  useEffect(() => {
    if (!ready) {
      setScreenshotUrl(null)
      if (timerRef.current) clearInterval(timerRef.current)
      return
    }

    // Poll screenshot: append timestamp to bust cache
    const refresh = () => {
      setScreenshotUrl(`/api/media/screenshot?t=${Date.now()}`)
    }
    refresh()
    timerRef.current = setInterval(refresh, SCREENSHOT_INTERVAL_MS)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [ready])

  if (!ready) {
    return (
      <div className="p-6 flex items-center justify-center h-full">
        <Card variant="subtle">
          <CardContent className="py-12 px-16 text-center space-y-2">
            <p className="text-muted-foreground">{t.screen.notReady}</p>
            {session?.reason && (
              <p className="text-xs text-muted-foreground/70">{session.reason}</p>
            )}
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center gap-3">
        <h1 className="font-serif text-2xl font-semibold text-foreground">
          {t.screen.title}
        </h1>
        {session?.title && (
          <>
            <span className="text-muted-foreground">—</span>
            <span className="font-medium text-foreground truncate max-w-xs">{session.title}</span>
          </>
        )}
        <span className="text-xs text-muted-foreground px-2 py-1 rounded-lg bg-muted">
          {t.screen.previewMode}
        </span>
      </div>

      <p className="text-sm text-muted-foreground">{t.screen.previewDesc}</p>

      <div className="rounded-2xl border border-border/60 overflow-hidden shadow-shell">
        {screenshotUrl ? (
          <img
            src={screenshotUrl}
            alt="miniprogram preview"
            className="max-w-full block"
          />
        ) : (
          <div className="flex items-center justify-center min-h-[300px] bg-muted/40">
            <span className="text-sm text-muted-foreground animate-pulse">{t.common.loading}</span>
          </div>
        )}
      </div>
    </div>
  )
}

export const Route = createFileRoute('/screen')({
  component: ScreenPage,
})
