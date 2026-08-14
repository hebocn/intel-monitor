import axios from 'axios'

/**
 * 创建已配置认证拦截器的 axios 实例。
 * 与后端 FastAPI 通信的基础 API 客户端。
 */
export function createApi(baseURL = '/api', timeout = 30000) {
  const api = axios.create({ baseURL, timeout })

  api.interceptors.request.use((config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  api.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error.response?.status === 401) {
        localStorage.removeItem('token')
        window.location.href = '/login'
      }
      return Promise.reject(error)
    },
  )

  return api
}

/** 预配置的默认 API 实例，可直接使用 */
export const api = createApi()
export default api
