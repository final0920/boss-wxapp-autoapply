import { createFileRoute } from '@tanstack/react-router'
import { DecisionLog } from '../components/DecisionLog'

// 决策日志已直接嵌在首页（会话下方）；此路由保留以便直接访问，不在侧栏菜单中。
function LogsPage() {
  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-serif font-semibold text-foreground">运行日志</h1>
      <DecisionLog height="h-[34rem]" />
    </div>
  )
}

export const Route = createFileRoute('/logs')({
  component: LogsPage,
})
