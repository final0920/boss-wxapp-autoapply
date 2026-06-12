import { type ButtonHTMLAttributes, forwardRef } from 'react'
import { cn } from '../../lib/utils'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'outline' | 'ghost' | 'destructive' | 'secondary' | 'link'
  size?: 'sm' | 'md' | 'lg' | 'icon'
}

const variantCls: Record<NonNullable<ButtonProps['variant']>, string> = {
  default: 'bg-primary text-white hover:bg-primary/90',
  destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/85',
  outline:
    'border border-border/60 bg-card/60 text-foreground hover:border-primary/60 hover:text-primary hover:bg-primary/10 backdrop-blur',
  secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
  ghost: 'hover:bg-accent hover:text-accent-foreground',
  link: 'text-primary underline-offset-4 hover:underline',
}

const sizeCls: Record<NonNullable<ButtonProps['size']>, string> = {
  sm: 'h-9 rounded-lg px-3 text-sm',
  md: 'h-11 px-5 text-sm',
  lg: 'h-12 rounded-xl px-8 text-base',
  icon: 'h-11 w-11 rounded-2xl',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', size = 'md', ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        'inline-flex items-center justify-center rounded-xl font-semibold transition-all duration-200',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        'disabled:pointer-events-none disabled:opacity-50 active:scale-[0.98]',
        variantCls[variant],
        sizeCls[size],
        className,
      )}
      {...props}
    />
  ),
)
Button.displayName = 'Button'
