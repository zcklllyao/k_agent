import { useEffect, useState } from 'react'
import { Spin } from 'antd'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

// 路由守卫：未登录跳登录页；已登录但还没拉到用户信息时先拉一次
export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const user = useAuthStore((s) => s.user)
  const fetchUser = useAuthStore((s) => s.fetchUser)
  const [checking, setChecking] = useState(!user)

  useEffect(() => {
    if (isAuthenticated() && !user) {
      fetchUser().finally(() => setChecking(false))
    } else {
      setChecking(false)
    }
  }, [isAuthenticated, user, fetchUser])

  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }

  if (checking) {
    return (
      <div
        style={{
          height: '100%',
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Spin size="large" />
      </div>
    )
  }

  return <>{children}</>
}
