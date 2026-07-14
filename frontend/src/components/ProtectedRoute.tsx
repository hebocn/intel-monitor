import { Navigate } from 'react-router-dom'
import { ReactNode } from 'react'

interface Props {
  children: ReactNode
}

export default function ProtectedRoute({ children }: Props) {
  const token = localStorage.getItem('token')
  if (!token) return <Navigate to="/login" />
  return <>{children}</>
}
