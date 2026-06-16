import { useEffect, useRef, useState } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from './ui'
import { cn } from '../lib/utils'
import { apiGet } from '../api'

interface LogEntry {
  id: number
  ts: string
  level: string        // INFO | WARNING | ERROR
  event: string
  message: string
}

const levelStyle: Record<string, string> = {
  INFO: 'text-foreground',
  WARNING: 'text-yellow-500',
  ERROR: 'text-destructive',
}

// event → 中文标签
const eventLabel: Record<string, string> = {
  runner_start: '启动',
  runner_stop: '停止',
  runner_substate: '子态',
  runner_error: '错误',
  runner_anchor: '锚点',
  prefilter: '初筛淘汰',
  screen_fail: '打分淘汰',
  screen_pass: '通过',
  apply: '投递成功',
  apply_fail: '投递失败',
  dup: '已投过',
  agency_skip: '猎头/代招',
  feed_idle: '暂歇',
  source_switch: '切换源',
  geetest: '风控',
  llm_down: 'LLM不可用',
  inbox_reply: 'HR回复',
  inbox_unmatched: '未关联会话',
  scan_sending: '启动自检',
}

function fmtTs(iso: string): string {
  // "2026-06-10T15:55:39" → "15:55:39"；兼容 "2026-06-10 15:55:39"
  const t = (iso || '').split('T')[1] ?? (iso || '').split(' ')[1] ?? iso
  return t.slice(0, 8)
}

/** 决策日志面板：采集 / 淘汰原因 / 打分 / 投递 / 巡检，REST 每 3 秒轮询，最新在底部。 */
export function DecisionLog({ height = 'h-[30rem]' }: { height?: string }) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [error, setError] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    const pull = () => {
      apiGet<LogEntry[]>('/logs', { limit: 300 })
        .then(rows => {
          if (cancelled) return
          setLogs([...rows].reverse())
          setError(false)
        })
        .catch(() => { if (!cancelled) setError(true) })
    }
    pull()
    const timer = setInterval(pull, 3000)
    return () => { cancelled = true; clearInterval(timer) }
  }, [])

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [logs])

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">
          决策日志
          <span className="ml-2 text-xs font-sans font-normal text-muted-foreground">
            采集 / 淘汰原因 / 打分 / 投递 / 巡检（每 3 秒刷新）
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div
          ref={listRef}
          className={cn(
            'rounded-b-2xl bg-[#0d1117] p-4 overflow-auto font-mono text-xs leading-relaxed space-y-0.5 border-t border-border/60',
            height,
          )}
        >
          {error && logs.length === 0 && (
            <span className="text-destructive">无法连接后端，请确认服务在线</span>
          )}
          {!error && logs.length === 0 && (
            <span className="text-muted-foreground">
              暂无日志 —— 点「开始自动投递」后，这里实时显示每个岗位的采集 / 淘汰原因 / 打分 / 投递结果。
            </span>
          )}
          {logs.map(entry => (
            <div key={entry.id} className={cn('flex gap-2', levelStyle[entry.level] ?? 'text-foreground')}>
              <span className="text-muted-foreground shrink-0 tabular-nums">{fmtTs(entry.ts)}</span>
              <span className="text-sky-400 shrink-0 w-16">[{eventLabel[entry.event] ?? entry.event}]</span>
              <span className="break-all">{entry.message}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
