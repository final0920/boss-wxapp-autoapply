import { useI18n } from '../lib/i18n'
import { cn } from '../lib/utils'
import { Badge, Button, Card, CardContent } from './ui'

export interface HrMessage {
  id: string
  company: string
  hrName: string
  content: string
  receivedAt: string
  read: boolean
  takenOver: boolean
  applicationId: string
}

interface TakeoverButtonProps {
  onTakeover: () => void
  disabled?: boolean
}

export function TakeoverButton({ onTakeover, disabled }: TakeoverButtonProps) {
  const { t } = useI18n()
  return (
    <Button
      variant={disabled ? 'outline' : 'default'}
      size="sm"
      disabled={disabled}
      onClick={onTakeover}
      title={t.inbox.takeoverDesc}
      className="shrink-0 h-8 px-3 text-xs"
    >
      {t.inbox.takeover}
    </Button>
  )
}

interface InboxPanelProps {
  messages: HrMessage[]
  onMarkRead: (id: string) => void
  onTakeover: (msg: HrMessage) => void
}

export function InboxPanel({ messages, onMarkRead, onTakeover }: InboxPanelProps) {
  const { t } = useI18n()
  const unreadCount = messages.filter(m => !m.read).length

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h2 className="font-serif text-base font-semibold">{t.inbox.title}</h2>
        {unreadCount > 0 && (
          <Badge variant="destructive" className="rounded-full px-2 py-0.5 text-xs">
            {unreadCount}
          </Badge>
        )}
      </div>

      <div className="space-y-3">
        {messages.map(msg => (
          <Card
            key={msg.id}
            variant="interactive"
            onClick={() => onMarkRead(msg.id)}
            className={cn(
              'cursor-pointer',
              !msg.read && 'border-primary/50 bg-primary/5',
              msg.takenOver && 'opacity-60',
            )}
          >
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    {!msg.read && (
                      <span className="w-2 h-2 rounded-full bg-primary shrink-0" />
                    )}
                    <span className="font-serif font-semibold text-sm">{msg.company}</span>
                    <span className="text-xs text-muted-foreground">{msg.hrName}</span>
                  </div>
                  <p className="text-sm leading-relaxed">{msg.content}</p>
                  <p className="text-xs text-muted-foreground">{msg.receivedAt}</p>
                </div>

                {msg.takenOver ? (
                  <span className="text-xs text-muted-foreground shrink-0">已接管</span>
                ) : (
                  <div onClick={e => e.stopPropagation()}>
                    <TakeoverButton onTakeover={() => onTakeover(msg)} />
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ))}

        {messages.length === 0 && (
          /* 空态：无消息时的占位提示 */
          <div className="flex flex-col items-center gap-2 py-10 text-center">
            <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center text-muted-foreground/50">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M4 4h16v12H4z" rx="2" />
                <path d="M4 4l8 8 8-8" />
              </svg>
            </div>
            <p className="text-sm text-muted-foreground">{t.inbox.title} — 暂无消息</p>
          </div>
        )}
      </div>
    </div>
  )
}
