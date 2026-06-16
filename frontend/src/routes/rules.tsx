import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { useI18n } from '../lib/i18n'
import { Button } from '../components/ui'
import { RuleConfigForm } from '../components/RuleConfigForm'
import { getRules, putRules, type RulesConfig } from '../api'

const FALLBACK: RulesConfig = {
  salary_min_k: 0,
  salary_max_k: 0,
  allowed_cities: [],
  blocked_areas: [],
  include_keywords: [],
  exclude_keywords: [],
  company_scales: [],
  my_degree: '',
  my_experience_years: 0,
  hr_active_within_days: 0,
  dedup_contacted: true,
  daily_limit: 100,
  interval_min_sec: 20,
  interval_max_sec: 90,
  night_stop_start: '23:00',
  night_stop_end: '07:00',
}

function RulesPage() {
  const { t } = useI18n()
  const [config, setConfig] = useState<RulesConfig>(FALLBACK)
  const [loading, setLoading] = useState(true)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')

  useEffect(() => {
    let cancelled = false
    getRules()
      .then(data => { if (!cancelled) setConfig(data) })
      .catch(() => { /* keep fallback */ })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const handleChange = <K extends keyof RulesConfig>(key: K, value: RulesConfig[K]) =>
    setConfig(prev => ({ ...prev, [key]: value }))

  const handleSave = async () => {
    setSaveState('saving')
    try {
      await putRules(config)
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
    t.rules.save

  return (
    <div className="p-6 space-y-4 max-w-2xl">
      <h1 className="text-2xl font-serif font-semibold text-foreground">{t.rules.title}</h1>

      {loading && (
        <p className="text-sm text-muted-foreground">加载配置中…</p>
      )}

      <RuleConfigForm
        config={config}
        loading={loading}
        onChange={handleChange}
      />

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

export const Route = createFileRoute('/rules')({
  component: RulesPage,
})
