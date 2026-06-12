import { createFileRoute } from '@tanstack/react-router'
import { useCallback, useEffect, useState } from 'react'
import { useSession } from '../lib/device-context'
import { useI18n } from '../lib/i18n'
import { Badge, Button, Card, CardHeader, CardTitle, CardContent } from '../components/ui'
import { getPipelineStatus, startPipeline, stopPipeline } from '../api'
import type { PipelineStatus } from '../api'

// ---------------------------------------------------------------------------
// Runner control panel: status / sub-state / stats / start-stop
// ---------------------------------------------------------------------------

const RUNNER_STATE_META: Record<PipelineStatus['state'], { label: string; variant: 'success' | 'warning' | 'destructive' | 'outline' }> = {
  IDLE: { label: '未启动', variant: 'outline' },
  RUNNING: { label: '运行中', variant: 'success' },
  PAUSED_GEETEST: { label: '风控暂停', variant: 'destructive' },
  STOPPED: { label: '已停止', variant: 'outline' },
}

const STAT_LABELS: Record<string, string> = {
  collected: '采集',
  prefilter_fail: '初筛淘汰',
  screened: '已打分',
  applied: '已投递',
  dup: '已投过',
  failed: '失败',
  inbox_new: 'HR 新回复',
}

function RunnerPanel() {
  const [st, setSt] = useState<PipelineStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')

  const refresh = useCallback(() => {
    getPipelineStatus().then(setSt).catch(() => {})
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 5000)
    return () => clearInterval(id)
  }, [refresh])

  const onStart = async () => {
    setBusy(true)
    setActionError('')
    try {
      await startPipeline()
      refresh()
    } catch {
      setActionError('启动失败（可能已在运行或小程序未就绪）')
    } finally {
      setBusy(false)
    }
  }

  const onStop = async () => {
    setBusy(true)
    setActionError('')
    try {
      await stopPipeline()
      refresh()
    } catch {
      setActionError('停止请求失败')
    } finally {
      setBusy(false)
    }
  }

  const meta = st ? RUNNER_STATE_META[st.state] : RUNNER_STATE_META.IDLE
  const running = st?.active ?? false

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <CardTitle className="text-base">自动投递</CardTitle>
            <Badge variant={meta.variant}>{meta.label}</Badge>
            {st?.state === 'RUNNING' && st.sub_state === 'inbox_only' && (
              <Badge variant="warning">仅巡检（配额满/夜停）</Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            {running ? (
              <Button size="sm" variant="outline" disabled={busy} onClick={onStop}>
                {busy ? '停止中…' : '停止'}
              </Button>
            ) : (
              <Button size="sm" disabled={busy} onClick={onStart}>
                {busy ? '启动中…' : '开始自动投递'}
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {st?.paused_reason && (
          <p className="text-sm text-destructive">{st.paused_reason}</p>
        )}
        {st?.last_error && st.state !== 'RUNNING' && (
          <p className="text-xs text-muted-foreground">最近错误：{st.last_error}</p>
        )}
        {actionError && <p className="text-sm text-destructive">{actionError}</p>}

        <div className="flex flex-wrap gap-x-6 gap-y-1.5 text-sm text-muted-foreground">
          <span>
            今日投递：
            <strong className="text-foreground">{st?.today_applied ?? 0}</strong>
            <span className="opacity-70"> / {st?.daily_limit ?? '—'}</span>
          </span>
          <span>
            VLM 调用：
            <strong className="text-foreground">{st?.today_vlm_calls ?? 0}</strong>
            <span className="opacity-70"> / {st?.vlm_daily_budget ?? '—'}</span>
            {st?.vlm_circuit_open && <strong className="text-destructive"> ·熔断</strong>}
          </span>
          {st && Object.entries(st.stats).map(([k, v]) => (
            <span key={k}>
              {STAT_LABELS[k] ?? k}：<strong className="text-foreground">{v}</strong>
            </span>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------

function IndexPage() {
  const { t } = useI18n()
  const { session } = useSession()

  const ready = session?.ready ?? false

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="font-serif text-2xl font-semibold text-foreground">{t.device.title}</h1>
        <Badge variant={ready ? 'success' : 'outline'}>
          {ready ? t.device.status.online : t.device.status.offline}
        </Badge>
      </div>

      {/* Session status card */}
      {!ready && (
        <Card variant="subtle">
          <CardContent className="py-8 text-center">
            <p className="text-muted-foreground">{session?.reason ?? t.device.noDevice}</p>
          </CardContent>
        </Card>
      )}

      {ready && session?.title && (
        <Card variant="subtle">
          <CardContent className="py-4">
            <div className="flex items-center gap-3 text-sm">
              <span className="inline-block w-2 h-2 rounded-full bg-success shrink-0" />
              <span className="font-medium text-foreground">{session.title}</span>
              {session.rect && (
                <span className="text-muted-foreground font-mono text-xs">
                  {session.rect.w} x {session.rect.h}
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Runner control panel */}
      <RunnerPanel />
    </div>
  )
}

export const Route = createFileRoute('/')({
  component: IndexPage,
})
