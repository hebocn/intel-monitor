/**
 * 从 localStorage JWT token 中解析 payload。
 * 返回解析后的对象，失败返回 null。
 */
export function parseToken(): Record<string, any> | null {
  try {
    const token = localStorage.getItem('token')
    if (!token) return null
    const payload = token.split('.')[1]
    return JSON.parse(atob(payload))
  } catch {
    return null
  }
}

/**
 * 从 JWT token 中提取用户名。
 * 优先取 payload.sub，回退到 "管理员"。
 */
export function getUsername(): string {
  const payload = parseToken()
  return payload?.sub || '管理员'
}

/**
 * 验证 token 是否存在且未过期。
 */
export function isTokenValid(): boolean {
  const payload = parseToken()
  if (!payload) return false
  // exp 是秒级时间戳
  if (payload.exp && Date.now() >= payload.exp * 1000) return false
  return true
}
