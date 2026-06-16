import { useI18n } from '../lib/i18n'
import { Card, CardHeader, CardTitle, CardContent, Input, TagInput } from './ui'
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
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">{t.rules.salaryFloor}</label>
            <Input
              type="number"
              min={0}
              value={config.salary_floor_k}
              disabled={loading}
              onChange={e => onChange('salary_floor_k', Number(e.target.value))}
            />
            <p className="text-xs text-muted-foreground">{t.rules.salaryFloorHint}</p>
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
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={config.exclude_agency}
              disabled={loading}
              onChange={e => onChange('exclude_agency', e.target.checked)}
              className="accent-primary"
            />
            {t.rules.excludeAgency}
          </label>
        </CardContent>
      </Card>

      {/* ⑤ 投递节奏 */}
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
