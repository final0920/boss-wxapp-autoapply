import { type HTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning' | 'dark'
}

const badgeVariant: Record<NonNullable<BadgeProps['variant']>, string> = {
  default: 'border-transparent bg-primary text-primary-foreground',
  secondary: 'border-transparent bg-secondary text-secondary-foreground',
  destructive: 'border-transparent bg-destructive text-destructive-foreground',
  success: 'border-transparent bg-success text-success-foreground',
  warning: 'border-transparent bg-warning text-warning-foreground',
  outline: 'text-foreground border-border bg-card/50',
  dark: 'border-transparent bg-foreground text-background',
}

export function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors',
        badgeVariant[variant],
        className,
      )}
      {...props}
    />
  )
}
