import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { useI18n, type Locale } from '../lib/i18n'
import { Button, Card, CardHeader, CardTitle, CardContent } from '../components/ui'
import { apiPut } from '../api'

type BackendOverride = 'auto' | 'uia' | 'vision'

interface SettingsState {
  backendOverride: BackendOverride
  backendLocked: boolean
  language: Locale
  theme: 'light' | 'dark'
}

// 后端未连通时的合理默认值
const FALLBACK: SettingsState = {
  backendOverride: 'auto',
  backendLocked: false,
  language: 'zh',
  theme: 'light',
}

function SettingsPage() {
  const { t, setLocale } = useI18n()
  const [cfg, setCfg] = useState<SettingsState>(FALLBACK)
  const [loading] = useState(false)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')

  const update = <K extends keyof SettingsState>(key: K, value: SettingsState[K]) =>
    setCfg(prev => ({ ...prev, [key]: value }))

  const handleSave = async () => {
    setSaveState('saving')
    // 语言切换立即生效
    setLocale(cfg.language)
    try {
      await apiPut('/config/settings', {
        backendOverride: cfg.backendOverride,
        backendLocked: cfg.backendLocked,
        language: cfg.language,
        theme: cfg.theme,
      })
      setSaveState('saved')
      setTimeout(() => setSaveState('idle'), 2000)
    } catch {
      setSaveState('error')
      setTimeout(() => setSaveState('idle'), 3000)
    }
  }

  const saveLabel =
    saveState === 'saving' ? '保存中…' :
    saveState === 'saved'  ? '已保存' :
    saveState === 'error'  ? '保存失败，重试' :
    t.settings.save

  return (
    <div className="p-6 space-y-4 max-w-lg">
      <h1 className="text-2xl font-serif font-semibold text-foreground">{t.settings.title}</h1>

      {/* 后端覆盖 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.settings.backendOverride}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            {(['auto', 'uia', 'vision'] as BackendOverride[]).map(opt => (
              <Button
                key={opt}
                variant={cfg.backendOverride === opt ? 'default' : 'outline'}
                size="sm"
                disabled={loading}
                onClick={() => update('backendOverride', opt)}
              >
                {opt === 'auto' ? '自动' : opt === 'uia' ? '控件树' : '视觉'}
              </Button>
            ))}
          </div>
          {cfg.backendOverride !== 'auto' && (
            <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
              <input
                type="checkbox"
                id="lock-backend"
                checked={cfg.backendLocked}
                disabled={loading}
                onChange={e => update('backendLocked', e.target.checked)}
                className="rounded accent-primary"
              />
              锁定（禁止自动切换）
            </label>
          )}
          <p className="text-xs text-muted-foreground">{t.settings.backendOverrideNote}</p>
        </CardContent>
      </Card>

      {/* 语言 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.settings.language}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            {(['zh', 'en'] as Locale[]).map(lang => (
              <Button
                key={lang}
                variant={cfg.language === lang ? 'default' : 'outline'}
                size="sm"
                disabled={loading}
                onClick={() => update('language', lang)}
              >
                {lang === 'zh' ? '中文' : 'English'}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* 主题 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.settings.theme}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            {(['light', 'dark'] as const).map(th => (
              <Button
                key={th}
                variant={cfg.theme === th ? 'default' : 'outline'}
                size="sm"
                disabled={loading}
                onClick={() => update('theme', th)}
              >
                {th === 'light' ? '浅色' : '深色'}
              </Button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            主题切换也可通过侧栏底部的切换按钮快速操作，设置在此保存后同步。
          </p>
        </CardContent>
      </Card>

      <Button
        onClick={handleSave}
        disabled={loading || saveState === 'saving'}
        variant={saveState === 'error' ? 'outline' : 'default'}
      >
        {saveLabel}
      </Button>
    </div>
  )
}

export const Route = createFileRoute('/settings')({
  component: SettingsPage,
})
