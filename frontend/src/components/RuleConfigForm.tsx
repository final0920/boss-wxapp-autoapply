import { useI18n } from '../lib/i18n'
import { Button, Card, CardHeader, CardTitle, CardContent, Input, TagInput } from './ui'
import type { RulesConfig } from '../api'

const COMPANY_SCALES = [
  '0-20人',
  '20-99人',
  '100-499人',
  '500-999人',
  '1000-9999人',
  '10000人以上',
]

const DEGREE_OPTIONS = ['', '高中', '中专', '中技', '大专', '本科', '硕士', '博士'] as const

const HR_ACTIVE_OPTIONS = [
  { value: 0, label: '不限' },
  { value: 1, label: '1 天内' },
  { value: 3, label: '3 天内' },
  { value: 7, label: '7 天内' },
  { value: 30, label: '30 天内' },
]

interface RuleConfigFormProps {
  config: RulesConfig
  loading: boolean
  onChange: <K extends keyof RulesConfig>(key: K, value: RulesConfig[K]) => void
}

export function RuleConfigForm({ config, loading, onChange }: RuleConfigFormProps) {
  const { t } = useI18n()

  const toggleScale = (scale: string) => {
    const next = config.company_scales.includes(scale)
      ? config.company_scales.filter(s => s !== scale)
      : [...config.company_scales, scale]
    onChange('company_scales', next)
  }

  const textAreaCls =
    'w-full rounded-xl border border-border/60 bg-muted/50 px-4 py-2 text-sm ' +
    'placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 ' +
    'focus-visible:ring-primary/40 focus-visible:border-primary/60 transition-all resize-y disabled:opacity-50'

  return (
    <div className="space-y-4 max-w-2xl">

      {/* ① 薪资与地点 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.rules.groupSalaryLocation}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">{t.rules.salaryMin}</label>
              <Input
                type="number"
                min={0}
                value={config.salary_min_k}
                disabled={loading}
                onChange={e => onChange('salary_min_k', Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">{t.rules.salaryMax}</label>
              <Input
                type="number"
                min={0}
                value={config.salary_max_k}
                disabled={loading}
                onChange={e => onChange('salary_max_k', Number(e.target.value))}
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">{t.rules.salaryHint}</p>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">{t.rules.allowedCities}</label>
            <TagInput
              value={config.allowed_cities}
              onChange={v => onChange('allowed_cities', v)}
              placeholder={t.rules.tagInputPlaceholder}
              disabled={loading}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">{t.rules.blockedAreas}</label>
            <TagInput
              value={config.blocked_areas}
              onChange={v => onChange('blocked_areas', v)}
              placeholder={t.rules.tagInputPlaceholder}
              disabled={loading}
            />
          </div>
        </CardContent>
      </Card>

      {/* ② 关键词 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.rules.groupKeywords}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">{t.rules.includeKeywords}</label>
            <TagInput
              value={config.include_keywords}
              onChange={v => onChange('include_keywords', v)}
              placeholder={t.rules.tagInputPlaceholder}
              disabled={loading}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">{t.rules.excludeKeywords}</label>
            <TagInput
              value={config.exclude_keywords}
              onChange={v => onChange('exclude_keywords', v)}
              placeholder={t.rules.tagInputPlaceholder}
              disabled={loading}
            />
          </div>
        </CardContent>
      </Card>

      {/* ③ 公司与岗位要求 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.rules.groupCompanyJob}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">{t.rules.companyScales}</label>
            <div className="flex flex-wrap gap-2 pt-1">
              {COMPANY_SCALES.map(scale => (
                <label key={scale} className="flex items-center gap-1.5 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.company_scales.includes(scale)}
                    disabled={loading}
                    onChange={() => toggleScale(scale)}
                    className="accent-primary"
                  />
                  {scale}
                </label>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">不勾选 = 不限</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">{t.rules.myDegree}</label>
              <select
                value={config.my_degree}
                disabled={loading}
                onChange={e => onChange('my_degree', e.target.value)}
                className="w-full rounded-xl border border-border/60 bg-muted/50 px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-50"
              >
                {DEGREE_OPTIONS.map(d => (
                  <option key={d} value={d}>{d === '' ? '不限' : d}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">{t.rules.myExperienceYears}</label>
              <Input
                type="number"
                min={0}
                value={config.my_experience_years}
                disabled={loading}
                onChange={e => onChange('my_experience_years', Number(e.target.value))}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ④ HR 与去重 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.rules.groupHrDedup}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">{t.rules.hrActiveDays}</label>
            <select
              value={String(config.hr_active_within_days)}
              disabled={loading}
              onChange={e => onChange('hr_active_within_days', Number(e.target.value))}
              className="w-full rounded-xl border border-border/60 bg-muted/50 px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-50"
            >
              {HR_ACTIVE_OPTIONS.map(o => (
                <option key={o.value} value={String(o.value)}>{o.label}</option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={config.dedup_contacted}
              disabled={loading}
              onChange={e => onChange('dedup_contacted', e.target.checked)}
              className="accent-primary"
            />
            {t.rules.dedupContacted}
          </label>
        </CardContent>
      </Card>

      {/* ⑤ LLM */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.rules.groupLlm}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* LLM 打分开关 */}
          <label className="flex items-center justify-between gap-3 cursor-pointer">
            <span className="text-sm text-foreground">启用 LLM 打分</span>
            <input
              type="checkbox"
              checked={config.llm_enabled}
              disabled={loading}
              onChange={e => onChange('llm_enabled', e.target.checked)}
              className="h-4 w-4 accent-primary"
            />
          </label>
          <p className="text-xs text-muted-foreground -mt-1.5">
            关闭后：硬过滤通过的岗位直接投递，不调用 LLM（适合 LLM 不可用、或想纯按硬条件投递）。
          </p>
          <div className={`space-y-1 ${config.llm_enabled ? '' : 'opacity-40 pointer-events-none'}`}>
            <label className="text-xs text-muted-foreground">
              {t.rules.llmThreshold}
              <span className="ml-2 font-mono text-primary">{config.llm_threshold}</span>
            </label>
            <input
              type="range"
              min={0}
              max={100}
              value={config.llm_threshold}
              disabled={loading || !config.llm_enabled}
              onChange={e => onChange('llm_threshold', Number(e.target.value))}
              className="w-full accent-primary disabled:opacity-50"
            />
            <p className="text-xs text-muted-foreground">
              评分 &ge; {config.llm_threshold} 才会自动投递
            </p>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">{t.rules.profile}</label>
            <textarea
              value={config.profile}
              onChange={e => onChange('profile', e.target.value)}
              rows={4}
              disabled={loading}
              className={textAreaCls}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">{t.rules.greetingPrompt}</label>
            <textarea
              value={config.greeting_prompt}
              onChange={e => onChange('greeting_prompt', e.target.value)}
              rows={3}
              disabled={true}
              placeholder={t.rules.greetingPromptHint}
              className={textAreaCls}
            />
            <p className="text-xs text-muted-foreground">{t.rules.greetingPromptHint}</p>
          </div>
        </CardContent>
      </Card>

      {/* ⑥ 投递节奏 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.rules.groupPace}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">{t.rules.dailyLimit}</label>
              <Input
                type="number"
                min={1}
                value={config.daily_limit}
                disabled={loading}
                onChange={e => onChange('daily_limit', Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">{t.rules.intervalMinSec}</label>
              <Input
                type="number"
                min={0}
                value={config.interval_min_sec}
                disabled={loading}
                onChange={e => onChange('interval_min_sec', Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">{t.rules.intervalMaxSec}</label>
              <Input
                type="number"
                min={0}
                value={config.interval_max_sec}
                disabled={loading}
                onChange={e => onChange('interval_max_sec', Number(e.target.value))}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">{t.rules.nightStopStart}</label>
              <Input
                type="time"
                value={config.night_stop_start}
                disabled={loading}
                onChange={e => onChange('night_stop_start', e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">{t.rules.nightStopEnd}</label>
              <Input
                type="time"
                value={config.night_stop_end}
                disabled={loading}
                onChange={e => onChange('night_stop_end', e.target.value)}
              />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
