import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { api, jsonBody } from '../lib/api'
import type { Role, UserProfile } from '../types'

interface AuthContextValue {
  user: UserProfile | null
  activeRole: Role | null
  loading: boolean
  login: (collegeId: string, email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  selectRole: (role: Role) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null)
  const [activeRole, setActiveRole] = useState<Role | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let mounted = true
    api<UserProfile>('/auth/me')
      .then((profile) => {
        if (!mounted) return
        setUser(profile)
        if (profile.roles.length === 1) setActiveRole(profile.roles[0])
      })
      .catch(() => {
        if (mounted) setUser(null)
      })
      .finally(() => {
        if (mounted) setLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [])

  const login = useCallback(
    async (collegeId: string, email: string, password: string) => {
      const response = await api<{ user: UserProfile }>('/auth/login', {
        method: 'POST',
        body: jsonBody({ college_id: collegeId, email, password }),
      })
      setUser(response.user)
      setActiveRole(response.user.roles.length === 1 ? response.user.roles[0] : null)
    },
    [],
  )

  const logout = useCallback(async () => {
    await api<void>('/auth/logout', { method: 'POST', body: '{}' })
    setUser(null)
    setActiveRole(null)
  }, [])

  const selectRole = useCallback(
    (role: Role) => {
      if (user?.roles.includes(role)) setActiveRole(role)
    },
    [user],
  )

  const value = useMemo(
    () => ({ user, activeRole, loading, login, logout, selectRole }),
    [user, activeRole, loading, login, logout, selectRole],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used within AuthProvider')
  return value
}
