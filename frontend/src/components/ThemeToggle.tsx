import { useEffect, useState } from 'react'
import { Sun, Moon } from 'lucide-react'
import { cn } from '../lib/utils'

function applyTheme(dark: boolean) {
  document.documentElement.classList.toggle('dark', dark)
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
  localStorage.setItem('theme', dark ? 'dark' : 'light')
}

/** 默认浅色（Claude 纸张）；持久化到 localStorage；切换 .dark 类 */
export function ThemeToggle({ className }: { className?: string }) {
  const [dark, setDark] = useState(false)

  useEffect(() => {
    const isDark = localStorage.getItem('theme') === 'dark'
    setDark(isDark)
    applyTheme(isDark)
  }, [])

  return (
    <button
      type="button"
      title="切换主题"
      onClick={() => {
        const next = !dark
        setDark(next)
        applyTheme(next)
      }}
      className={cn(
        'w-10 h-10 flex items-center justify-center rounded-xl text-muted-foreground',
        'hover:text-foreground hover:bg-muted transition-colors active:scale-[0.96]',
        className,
      )}
    >
      {dark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  )
}
