import { type HTMLAttributes, forwardRef } from 'react'
import { cn } from '../../lib/utils'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'glass' | 'elevated' | 'interactive' | 'subtle'
}

const cardVariant: Record<NonNullable<CardProps['variant']>, string> = {
  default: 'border-border shadow-sm',
  glass: 'border-border bg-card/50 shadow-sm backdrop-blur-sm',
  elevated: 'border-border shadow-lg',
  interactive:
    'border-border shadow-sm transition-all duration-200 hover:shadow-md hover:border-primary/30 hover:-translate-y-0.5',
  subtle: 'border-border/50',
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant = 'default', ...props }, ref) => (
    <div
      ref={ref}
      className={cn('rounded-2xl border bg-card text-card-foreground', cardVariant[variant], className)}
      {...props}
    />
  ),
)
Card.displayName = 'Card'

export const CardHeader = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('flex flex-col gap-1.5 p-5', className)} {...props} />
  ),
)
CardHeader.displayName = 'CardHeader'

export const CardTitle = forwardRef<HTMLHeadingElement, HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3 ref={ref} className={cn('font-serif text-lg font-semibold leading-tight', className)} {...props} />
  ),
)
CardTitle.displayName = 'CardTitle'

export const CardContent = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => <div ref={ref} className={cn('p-5 pt-0', className)} {...props} />,
)
CardContent.displayName = 'CardContent'
