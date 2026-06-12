import { useState } from 'react'
import { cn } from '../lib/utils'
import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from './ui'
import type { ApplicationRecord } from '../api'

/** 状态徽章：含 DUP（已投过）/FAILED（含被过滤） */
const STATUS_META: Record<ApplicationRecord['status'], { label: string; variant: 'default' | 'success' | 'warning' | 'destructive' | 'outline' }> = {
  PENDING: { label: '待筛选', variant: 'outline' },
  CLAIMED: { label: '已通过筛选', variant: 'default' },
  SENDING: { label: '投递中', variant: 'warning' },
  SENT: { label: '已投递', variant: 'success' },
  FAILED: { label: '未投递', variant: 'destructive' },
  DUP: { label: '已投过', variant: 'outline' },
}

export function StatusBadge({ status }: { status: ApplicationRecord['status'] }) {
  const meta = STATUS_META[status] ?? { label: status, variant: 'outline' as const }
  return <Badge variant={meta.variant}>{meta.label}</Badge>
}

function fmtTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function parseReasons(raw: string): string[] {
  try {
    const v = JSON.parse(raw)
    return Array.isArray(v) ? v.map(String) : []
  } catch {
    return raw ? [raw] : []
  }
}

/** 行展开详情：JD 全文 / 评分理由 / 实发招呼语 / 失败原因 */
function ExpandedDetail({ app }: { app: ApplicationRecord }) {
  const job = app.job
  const reasons = parseReasons(job?.reasons ?? '')
  return (
    <div className="px-4 py-3 space-y-3 bg-muted/30 text-sm">
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
        {job?.degree && <span>学历要求：{job.degree}</span>}
        {job?.experience && <span>经验要求：{job.experience}</span>}
        {job?.company_scale && <span>规模：{job.company_scale}</span>}
        {job?.finance_stage && <span>融资：{job.finance_stage}</span>}
        {job?.hr_name && <span>HR：{job.hr_name}</span>}
        {job?.hr_active && <span>活跃：{job.hr_active}</span>}
      </div>

      {app.fail_reason && (
        <div>
          <div className="text-xs font-semibold text-destructive mb-0.5">未投递原因</div>
          <div className="text-destructive/90">{app.fail_reason}</div>
        </div>
      )}

      {reasons.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-muted-foreground mb-0.5">评分理由</div>
          <ul className="list-disc list-inside space-y-0.5">
            {reasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}

      {app.greeting && (
        <div>
          <div className="text-xs font-semibold text-muted-foreground mb-0.5">实发招呼语</div>
          <div className="whitespace-pre-wrap rounded-xl bg-card border border-border/50 p-2.5">{app.greeting}</div>
        </div>
      )}

      {job?.jd && (
        <div>
          <div className="text-xs font-semibold text-muted-foreground mb-0.5">职位描述（JD 全文）</div>
          <div className="whitespace-pre-wrap max-h-72 overflow-auto rounded-xl bg-card border border-border/50 p-2.5 leading-relaxed">
            {job.jd}
          </div>
        </div>
      )}
    </div>
  )
}

/** 投递历史记录表格（点击行展开核对详情，A6） */
export function ApplicationTable({ apps }: { apps: ApplicationRecord[] }) {
  const [expanded, setExpanded] = useState<number | null>(null)

  if (apps.length === 0) {
    return (
      <Card variant="subtle">
        <CardContent className="py-10 text-center">
          <p className="text-muted-foreground text-sm">暂无记录</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="rounded-2xl border border-border/60 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-muted/50 text-left text-xs text-muted-foreground">
            <th className="px-4 py-2.5 font-semibold">公司</th>
            <th className="px-4 py-2.5 font-semibold">岗位</th>
            <th className="px-4 py-2.5 font-semibold">薪资</th>
            <th className="px-4 py-2.5 font-semibold">城市/地点</th>
            <th className="px-4 py-2.5 font-semibold">评分</th>
            <th className="px-4 py-2.5 font-semibold">状态</th>
            <th className="px-4 py-2.5 font-semibold">时间</th>
          </tr>
        </thead>
        <tbody>
          {apps.map(a => (
            <Row
              key={a.id}
              app={a}
              expanded={expanded === a.id}
              onToggle={() => setExpanded(expanded === a.id ? null : a.id)}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Row({ app, expanded, onToggle }: {
  app: ApplicationRecord
  expanded: boolean
  onToggle: () => void
}) {
  const job = app.job
  return (
    <>
      <tr
        onClick={onToggle}
        className={cn(
          'border-t border-border/40 cursor-pointer transition-colors hover:bg-muted/40',
          expanded && 'bg-muted/30',
        )}
      >
        <td className="px-4 py-2.5 font-medium max-w-[180px] truncate">{job?.company ?? '—'}</td>
        <td className="px-4 py-2.5 max-w-[220px] truncate">{job?.title ?? '—'}</td>
        <td className="px-4 py-2.5 whitespace-nowrap">{job?.salary || '—'}</td>
        <td className="px-4 py-2.5 max-w-[140px] truncate text-muted-foreground">{job?.area || '—'}</td>
        <td className="px-4 py-2.5">
          {job?.score != null
            ? <span className={cn('font-semibold', job.score >= 80 ? 'text-success' : 'text-muted-foreground')}>{job.score}</span>
            : <span className="text-muted-foreground/60">—</span>}
        </td>
        <td className="px-4 py-2.5"><StatusBadge status={app.status} /></td>
        <td className="px-4 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
          {fmtTime(app.sent_at ?? app.updated_at)}
        </td>
      </tr>
      {expanded && (
        <tr className="border-t border-border/30">
          <td colSpan={7} className="p-0"><ExpandedDetail app={app} /></td>
        </tr>
      )}
    </>
  )
}

/** SENDING 待人工确认队列（崩溃恢复，AC8/A10） */
export function PendingConfirmQueue({ apps, onConfirm }: {
  apps: ApplicationRecord[]
  onConfirm: (id: number, sent: boolean) => void
}) {
  const sending = apps.filter(a => a.status === 'SENDING')
  if (sending.length === 0) return null

  return (
    <Card variant="default" className="border-warning/50 bg-warning/5">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">
          待人工确认（重启后残留的投递中记录，请到真机核对是否已发）
          <span className="ml-1.5 font-sans text-xs font-semibold text-muted-foreground">
            ({sending.length})
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0 space-y-2">
        {sending.map(a => (
          <div key={a.id} className="flex items-center justify-between gap-3 rounded-xl border border-border/50 bg-card px-3 py-2">
            <div className="min-w-0">
              <div className="text-sm font-medium truncate">{a.job?.title ?? `#${a.id}`}</div>
              <div className="text-xs text-muted-foreground truncate">{a.job?.company}</div>
            </div>
            <div className="flex gap-2 shrink-0">
              <Button size="sm" className="h-7 px-2 text-xs" onClick={() => onConfirm(a.id, true)}>
                已发送
              </Button>
              <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={() => onConfirm(a.id, false)}>
                未发送
              </Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
