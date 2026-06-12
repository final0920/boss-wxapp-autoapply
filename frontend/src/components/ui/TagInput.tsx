import { useState, type KeyboardEvent } from 'react'
import { cn } from '../../lib/utils'

interface TagInputProps {
  value: string[]
  onChange: (tags: string[]) => void
  placeholder?: string
  disabled?: boolean
  className?: string
}

export function TagInput({ value, onChange, placeholder, disabled, className }: TagInputProps) {
  const [input, setInput] = useState('')

  const add = () => {
    const trimmed = input.trim()
    if (trimmed && !value.includes(trimmed)) {
      onChange([...value, trimmed])
    }
    setInput('')
  }

  const remove = (tag: string) => onChange(value.filter(t => t !== tag))

  const handleKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      add()
    } else if (e.key === 'Backspace' && input === '' && value.length > 0) {
      remove(value[value.length - 1])
    }
  }

  return (
    <div
      className={cn(
        'flex flex-wrap gap-1.5 rounded-xl border border-border/60 bg-muted/50 px-3 py-2 min-h-[40px]',
        'focus-within:ring-2 focus-within:ring-primary/40 focus-within:border-primary/60 transition-all',
        disabled && 'opacity-50 pointer-events-none',
        className,
      )}
    >
      {value.map(tag => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 rounded-lg bg-primary/10 text-primary px-2 py-0.5 text-xs font-medium"
        >
          {tag}
          <button
            type="button"
            onClick={() => remove(tag)}
            className="hover:text-destructive transition-colors leading-none"
            aria-label={`Remove ${tag}`}
          >
            &times;
          </button>
        </span>
      ))}
      <input
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={handleKey}
        onBlur={() => input.trim() && add()}
        placeholder={value.length === 0 ? placeholder : undefined}
        disabled={disabled}
        className="flex-1 min-w-[120px] bg-transparent text-sm outline-none placeholder:text-muted-foreground"
      />
    </div>
  )
}
