import { createContext, useContext, useState, type ReactNode } from 'react'
import { cn } from '../../lib/utils'

interface TabsContextValue {
  active: string
  setActive: (v: string) => void
}

const TabsContext = createContext<TabsContextValue>({ active: '', setActive: () => {} })

export function Tabs({
  defaultValue,
  children,
  className,
}: {
  defaultValue: string
  children: ReactNode
  className?: string
}) {
  const [active, setActive] = useState(defaultValue)
  return (
    <TabsContext.Provider value={{ active, setActive }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  )
}

export function TabsList({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('inline-flex gap-1 rounded-xl bg-muted/50 p-1', className)}>{children}</div>
}

export function TabsTrigger({ value, children }: { value: string; children: ReactNode }) {
  const { active, setActive } = useContext(TabsContext)
  const isActive = active === value
  return (
    <button
      onClick={() => setActive(value)}
      className={cn(
        'rounded-lg px-3 py-1.5 text-sm font-semibold transition-all active:scale-[0.98]',
        isActive ? 'bg-card text-primary shadow-sm' : 'text-muted-foreground hover:text-foreground',
      )}
    >
      {children}
    </button>
  )
}

export function TabsContent({
  value,
  children,
  className,
}: {
  value: string
  children: ReactNode
  className?: string
}) {
  const { active } = useContext(TabsContext)
  if (active !== value) return null
  return <div className={className}>{children}</div>
}
