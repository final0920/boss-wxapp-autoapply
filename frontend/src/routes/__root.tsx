import { useState, useEffect } from 'react'
import { createRootRoute, Outlet, Link } from '@tanstack/react-router'
import { useI18n } from '../lib/i18n'
import { cn } from '../lib/utils'
import { ThemeToggle } from '../components/ThemeToggle'
import {
  Monitor, Smartphone, Send, Mail, Filter,
  BarChart2, Settings, ChevronLeft, ChevronRight,
} from 'lucide-react'

const SIDEBAR_COLLAPSED_KEY = 'sidebar-collapsed'

function RootLayout() {
  const { t } = useI18n()

  // 从 localStorage 恢复折叠状态
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'
    } catch {
      return false
    }
  })

  // 同步折叠状态到 localStorage
  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed))
    } catch { /* 忽略隐私模式下的错误 */ }
  }, [collapsed])

  const navItems = [
    { to: '/', label: t.nav.devices, icon: Smartphone },
    { to: '/screen', label: t.nav.screen, icon: Monitor },
    { to: '/applications', label: t.nav.applications, icon: Send },
    { to: '/inbox', label: t.nav.inbox, icon: Mail },
    { to: '/rules', label: t.nav.rules, icon: Filter },
    { to: '/logs', label: t.nav.logs, icon: BarChart2 },
    { to: '/settings', label: t.nav.settings, icon: Settings },
  ] as const

  return (
    <div className="relative flex h-screen overflow-hidden bg-background">
      {/* 装饰渐变光斑（书卷气暖色） */}
      <div
        aria-hidden
        className="pointer-events-none absolute -left-24 -top-32 h-96 w-96 rounded-full opacity-50 blur-3xl"
        style={{ background: 'radial-gradient(circle, rgba(201,100,66,0.18), transparent 70%)' }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-24 right-0 h-96 w-96 rounded-full opacity-40 blur-3xl"
        style={{ background: 'radial-gradient(circle, rgba(228,178,160,0.20), transparent 70%)' }}
      />

      {/* 侧栏（玻璃卡 + 图标+文字展开式 + 染色长投影） */}
      <aside
        className={cn(
          'sidebar-card relative z-10 m-3 flex flex-col gap-1 px-3 py-4 shadow-shell-sidebar',
          'transition-[width] duration-300 ease-in-out overflow-hidden',
          collapsed ? 'w-16' : 'w-56',
        )}
      >
        {/* 品牌区 */}
        <div className={cn('mb-4 flex items-center px-1', collapsed ? 'justify-center gap-0' : 'gap-2.5')}>
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            <span className="font-serif text-sm font-bold">B</span>
          </div>
          {/* 展开时显示品牌文字 */}
          <div
            className={cn(
              'leading-tight overflow-hidden transition-all duration-300',
              collapsed ? 'w-0 opacity-0' : 'w-auto opacity-100',
            )}
          >
            <div className="font-serif text-sm font-semibold text-foreground whitespace-nowrap">Boss AutoApply</div>
            <div className="text-[11px] text-muted-foreground whitespace-nowrap">自动求职控制台</div>
          </div>
        </div>

        {/* 导航（折叠仅图标，展开图标+文字） */}
        <nav className="flex flex-1 flex-col gap-0.5">
          {navItems.map(({ to, label, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              title={collapsed ? label : undefined}
              className={cn(
                'flex items-center rounded-xl px-3 py-2 text-sm font-medium text-muted-foreground transition-all',
                'hover:bg-muted hover:text-foreground active:scale-[0.98]',
                '[&.active]:bg-primary/10 [&.active]:font-semibold [&.active]:text-primary',
                collapsed ? 'justify-center gap-0' : 'gap-3',
              )}
            >
              <Icon size={18} className="shrink-0" />
              {/* 展开时显示文字 */}
              <span
                className={cn(
                  'overflow-hidden whitespace-nowrap transition-all duration-300',
                  collapsed ? 'w-0 opacity-0' : 'w-auto opacity-100',
                )}
              >
                {label}
              </span>
            </Link>
          ))}
        </nav>

        {/* 底部：折叠按钮 + 主题切换 */}
        <div className="mt-2 border-t border-border/50 px-1 pt-3">
          {collapsed ? (
            /* 折叠状态：仅显示折叠切换按钮 */
            <div className="flex flex-col items-center gap-2">
              <ThemeToggle />
              <button
                onClick={() => setCollapsed(false)}
                title="展开侧栏"
                className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          ) : (
            /* 展开状态：主题切换 + 折叠按钮 */
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">主题</span>
              <div className="flex items-center gap-1">
                <ThemeToggle />
                <button
                  onClick={() => setCollapsed(true)}
                  title="折叠侧栏"
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                >
                  <ChevronLeft size={16} />
                </button>
              </div>
            </div>
          )}
        </div>
      </aside>

      {/* 主内容区 */}
      <main className="relative z-10 flex-1 overflow-auto p-3">
        <Outlet />
      </main>
    </div>
  )
}

export const Route = createRootRoute({
  component: RootLayout,
})
