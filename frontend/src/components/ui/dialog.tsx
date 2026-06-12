import { type ReactNode } from 'react'
import { cn } from '../../lib/utils'

interface DialogProps {
  open: boolean
  onClose: () => void
  title?: string
  children: ReactNode
  className?: string
}

export function Dialog({ open, onClose, title, children, className }: DialogProps) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop（模糊） */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      {/* Panel（玻璃 + 大圆角 + 染色投影） */}
      <div
        className={cn(
          'relative z-10 w-full max-w-lg rounded-2xl border border-border bg-card/95 backdrop-blur shadow-shell',
          className,
        )}
      >
        {title && (
          <div className="flex items-center justify-between border-b border-border/60 px-5 py-3">
            <span className="font-serif text-base font-semibold">{title}</span>
            <button
              onClick={onClose}
              className="text-xl leading-none text-muted-foreground transition-colors hover:text-foreground"
            >
              &times;
            </button>
          </div>
        )}
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}
