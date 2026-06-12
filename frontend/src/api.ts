import redaxios from 'redaxios'

// Token is fetched from the backend via /api/token after initial page load.
// It is NOT stored in localStorage or any persistent browser storage.
let _token = ''

export function setToken(t: string) {
  _token = t
}

export function getToken() {
  return _token
}

const api = redaxios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Inject auth token on every request
api.defaults.headers = api.defaults.headers ?? {}

// Interceptor-style wrapper: use typed helper functions instead of raw api
export async function apiGet<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const res = await api.get<T>(path, {
    params,
    headers: { Authorization: `Bearer ${_token}` },
  })
  return res.data
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await api.post<T>(path, body, {
    headers: { Authorization: `Bearer ${_token}` },
  })
  return res.data
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  const res = await api.put<T>(path, body, {
    headers: { Authorization: `Bearer ${_token}` },
  })
  return res.data
}

export async function apiDelete<T>(path: string): Promise<T> {
  const res = await api.delete<T>(path, {
    headers: { Authorization: `Bearer ${_token}` },
  })
  return res.data
}

export default api

// ── RulesConfig — single source of truth matching backend pydantic RulesConfig ──
export interface RulesConfig {
  salary_min_k: number
  salary_max_k: number
  allowed_cities: string[]
  blocked_areas: string[]
  include_keywords: string[]
  exclude_keywords: string[]
  company_scales: string[]
  my_degree: string
  my_experience_years: number
  hr_active_within_days: number
  dedup_contacted: boolean
  llm_enabled: boolean
  llm_threshold: number
  profile: string
  greeting_prompt: string
  daily_limit: number
  interval_min_sec: number
  interval_max_sec: number
  night_stop_start: string
  night_stop_end: string
}

export function getRules(): Promise<RulesConfig> {
  return apiGet<RulesConfig>('/config/rules')
}

export function putRules(cfg: RulesConfig): Promise<RulesConfig> {
  return apiPut<RulesConfig>('/config/rules', cfg)
}

// ── Pipeline runner 控制面 ──
export interface PipelineStatus {
  state: 'IDLE' | 'RUNNING' | 'PAUSED_GEETEST' | 'STOPPED'
  sub_state: string
  paused_reason: string
  serial: string
  started_at: string | null
  last_error: string
  active: boolean
  stats: Record<string, number>
  today_applied: number
  daily_limit: number
  // M5 VLM 预算（后端 /pipeline/status 经 rate_limiter.get_vlm_quota 返回）
  today_vlm_calls?: number
  vlm_daily_budget?: number
  vlm_circuit_open?: boolean
  date?: string
}

export const getPipelineStatus = () => apiGet<PipelineStatus>('/pipeline/status')
export const startPipeline = (serial?: string) =>
  apiPost<{ ok: boolean; serial: string }>('/pipeline/run', serial ? { serial } : {})
export const stopPipeline = () =>
  apiPost<{ ok: boolean; state: string }>('/pipeline/stop')

// ── 投递历史记录（join Job 全字段） ──
export interface JobInfo {
  title: string
  company: string
  salary: string
  salary_min_k: number | null
  salary_max_k: number | null
  area: string
  jd: string
  score: number | null
  reasons: string
  degree: string
  experience: string
  company_scale: string
  finance_stage: string
  hr_name: string
  hr_active: string
}

export interface ApplicationRecord {
  id: number
  job_id: number
  status: 'PENDING' | 'CLAIMED' | 'SENDING' | 'SENT' | 'FAILED' | 'DUP'
  greeting: string
  taken_over: boolean
  fail_reason: string
  sent_at: string | null
  created_at: string | null
  updated_at: string | null
  job?: JobInfo
}

export const getApplications = (status?: string) =>
  apiGet<ApplicationRecord[]>('/applications', status ? { status } : undefined)
export const confirmApplication = (id: number, sent: boolean) =>
  apiPost(`/applications/${id}/confirm`, { sent })
export const clearHistory = () =>
  apiDelete<{ cleared: Record<string, number> }>('/applications/clear')
