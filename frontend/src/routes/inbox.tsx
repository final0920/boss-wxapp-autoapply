import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { useI18n } from '../lib/i18n'
import { Badge, Card, CardContent } from '../components/ui'
import { InboxPanel } from '../components/InboxPanel'
import type { HrMessage } from '../components/InboxPanel'
import { apiGet, apiPost } from '../api'

// 后端 /messages/inbox 返回的会话+最新消息结构
interface InboxThread {
  application_id: string
  job_id: string
  taken_over: boolean
  last_message: {
    id: string
    application_id: string
    role: string
    text: string
    ts: string
  } | null
}

// 将后端 InboxThread 转换为 InboxPanel 期望的 HrMessage 形状
function threadToMessage(thread: InboxThread): HrMessage {
  return {
    id: thread.last_message?.id ?? thread.application_id,
    company: thread.job_id,
    hrName: '',
    content: thread.last_message?.text ?? '',
    receivedAt: thread.last_message?.ts ?? '',
    // 未读判断：最新消息来自 hr 则视为未读
    read: thread.last_message ? thread.last_message.role !== 'hr' : true,
    takenOver: thread.taken_over,
    applicationId: thread.application_id,
  }
}

function InboxPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const [messages, setMessages] = useState<HrMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 初始加载收件箱，接口改为 /messages/inbox
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    apiGet<InboxThread[]>('/messages/inbox')
      .then(data => {
        if (!cancelled) setMessages(data.map(threadToMessage))
      })
      .catch(() => {
        if (!cancelled) setError('加载消息失败，请稍后重试')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [])

  // 轮询刷新收件箱（后端暂无 SSE /events/inbox，改为每 5s 拉取 /messages/inbox）
  useEffect(() => {
    const timer = setInterval(() => {
      apiGet<InboxThread[]>('/messages/inbox')
        .then(data => setMessages(data.map(threadToMessage)))
        .catch(() => { /* 非致命：轮询失败忽略 */ })
    }, 5000)
    return () => clearInterval(timer)
  }, [])

  const unreadCount = messages.filter(m => !m.read).length

  // 接管对话：切换设备为手动模式，跳转镜像页
  const handleTakeover = async (msg: HrMessage) => {
    setMessages(prev =>
      prev.map(m => m.applicationId === msg.applicationId ? { ...m, takenOver: true, read: true } : m),
    )
    try {
      await apiPost(`/applications/${msg.applicationId}/takeover`)
    } catch {
      // 非致命错误：接管请求失败时仍允许用户进入手动模式
    }
    navigate({ to: '/screen' })
  }

  // 标记已读：id 用 last_message.id（即 HrMessage.id）
  const markRead = async (id: string) => {
    setMessages(prev => prev.map(m => m.id === id ? { ...m, read: true } : m))
    try {
      // 路径改为 /messages/{id}/read
      await apiPost(`/messages/${id}/read`)
    } catch {
      // 非致命：已读状态只影响 badge 计数
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="font-serif text-2xl font-semibold">{t.inbox.title}</h1>
        {unreadCount > 0 && (
          <Badge variant="destructive" className="rounded-full px-2 py-0.5 text-xs">
            {unreadCount}
          </Badge>
        )}
      </div>

      {loading && (
        <Card variant="subtle">
          <CardContent className="py-10 text-center">
            <p className="text-muted-foreground text-sm">加载中…</p>
          </CardContent>
        </Card>
      )}

      {!loading && error && (
        <Card variant="subtle" className="border-destructive/40 bg-destructive/5">
          <CardContent className="py-8 text-center">
            <p className="text-destructive text-sm">{error}</p>
          </CardContent>
        </Card>
      )}

      {!loading && !error && messages.length === 0 && (
        <Card variant="subtle">
          <CardContent className="py-10 text-center">
            <p className="text-muted-foreground text-sm">暂无消息</p>
          </CardContent>
        </Card>
      )}

      {!loading && !error && messages.length > 0 && (
        <InboxPanel
          messages={messages}
          onMarkRead={markRead}
          onTakeover={handleTakeover}
        />
      )}
    </div>
  )
}

export const Route = createFileRoute('/inbox')({
  component: InboxPage,
})
