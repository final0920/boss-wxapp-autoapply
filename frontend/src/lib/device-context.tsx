import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { apiGet } from '../api'

// Session status as reported by GET /api/session
export interface SessionStatus {
  ready: boolean
  hwnd?: number
  title?: string
  reason?: string
  rect?: { x: number; y: number; w: number; h: number }
}

interface SessionContextValue {
  session: SessionStatus | null
  refreshSession: () => Promise<void>
}

const SessionContext = createContext<SessionContextValue | null>(null)

const POLL_INTERVAL_MS = 5000

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionStatus | null>(null)

  const refreshSession = useCallback(async () => {
    try {
      const data = await apiGet<SessionStatus>('/session')
      setSession(data)
    } catch {
      setSession({ ready: false, reason: '无法连接后端' })
    }
  }, [])

  useEffect(() => {
    refreshSession()
    const id = setInterval(refreshSession, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [refreshSession])

  return (
    <SessionContext.Provider value={{ session, refreshSession }}>
      {children}
    </SessionContext.Provider>
  )
}

export function useSession() {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error('useSession must be used within SessionProvider')
  return ctx
}

// Backward-compat alias so routes that import useDevice still compile during migration
// (they should be updated to useSession, but this avoids cascade errors)
export { useSession as useDevice }
