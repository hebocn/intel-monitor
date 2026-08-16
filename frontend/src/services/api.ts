import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

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
  }
)

// Auth
export const authAPI = {
  checkStatus: () => api.get('/auth/status'),
  setup: (username: string, password: string) => api.post('/auth/setup', { username, password }),
  login: (username: string, password: string) => api.post('/auth/login', { username, password }),
  register: (username: string, password: string) => api.post('/auth/register', { username, password }),
  resetPassword: (newPassword: string) => api.post('/auth/reset-password', { new_password: newPassword }),
}

// Targets
export const targetsAPI = {
  list: (platform?: string) => api.get('/targets', { params: { platform } }),
  create: (data: any) => api.post('/targets', data),
  update: (id: number, data: any) => api.put(`/targets/${id}`, data),
  delete: (id: number) => api.delete(`/targets/${id}`),
  runNow: (id: number) => api.post(`/schedule/run/${id}`, null, { params: { target_type: 'social_media' } }),
  batchUpdate: (data: { target_ids: number[]; is_active?: boolean; push_enabled?: boolean }) =>
    api.post('/targets/batch-update', data),
  importTemplate: () => api.get('/targets/import/template', { responseType: 'blob' }),
  importBatch: (formData: FormData) => api.post('/targets/import', formData, { timeout: 120000 }),
}

// Facebook (账号反查候选)
export const facebookAPI = {
  searchAccounts: (nickname: string, limit = 8) =>
    api.post('/facebook/search', { nickname, limit }, { timeout: 60000 }),
}

// Websites
export const websitesAPI = {
  list: () => api.get('/websites'),
  create: (data: any) => api.post('/websites', data),
  update: (id: number, data: any) => api.put(`/websites/${id}`, data),
  delete: (id: number) => api.delete(`/websites/${id}`),
  importTemplate: () => api.get('/websites/import/template', { responseType: 'blob' }),
  importBatch: (formData: FormData) => api.post('/websites/import', formData, { timeout: 120000 }),
  batchUpdate: (data: { website_ids: number[]; is_active?: boolean; push_enabled?: boolean }) =>
    api.post('/websites/batch-update', data),
}

// Results
export const resultsAPI = {
  list: (params: any) => api.get('/results', { params }),
  detail: (id: number) => api.get(`/results/${id}`),
  delete: (id: number) => api.delete(`/results/${id}`),
  fetchComments: (id: number, postUrl: string) => api.post(`/results/${id}/comments/fetch`, { post_url: postUrl }),
}

// Dashboard
export const dashboardAPI = {
  get: () => api.get('/dashboard'),
  overview: () => api.get('/dashboard/overview'),
  health: () => api.get('/dashboard/health'),
  geoSignals: () => api.get('/dashboard/geo-signals'),
}

// Schedule
export const scheduleAPI = {
  status: () => api.get('/schedule/status'),
  refresh: () => api.post('/schedule/refresh'),
  runNow: (targetId: number, targetType: string) =>
    api.post(`/schedule/run/${targetId}`, null, { params: { target_type: targetType } }),
  sync: (targetId: number, limit: number) =>
    api.post(`/schedule/sync/${targetId}`, null, { params: { limit }, timeout: 600000 }),
}

// Feishu
export const feishuAPI = {
  status: () => api.get('/feishu/status'),
  saveConfig: (data: { app_secret: string; app_id?: string; enabled?: boolean }) => api.put('/feishu/config', data),
  bindCode: () => api.post('/feishu/bind-code'),
  unbind: () => api.post('/feishu/unbind'),
}

// Settings — multi-provider
export const settingsAPI = {
  getProvider: (provider: string) => api.get(`/settings/${provider}`),
  saveProvider: (provider: string, apiKey: string) => api.post(`/settings/${provider}`, { api_key: apiKey }),
  testSaved: (provider: string) => api.post(`/settings/${provider}/test-saved`),
  getActiveProvider: () => api.get('/settings/active/provider'),
  setActiveProvider: (provider: string) => api.post('/settings/active/provider', { provider }),
  setProviderModel: (provider: string, model: string) => api.put(`/settings/${provider}/model`, { model }),
  getPrompts: () => api.get('/settings/prompts'),
  setPrompts: (data: { summarize_posts?: string; summarize_website?: string; intelligence_report?: string }) =>
    api.put('/settings/prompts', data),
}

// Hot Topics
export const hotTopicsAPI = {
  // Platforms
  listPlatforms: () => api.get('/hot-topic-sources/platforms'),
  // Sources
  listSources: () => api.get('/hot-topic-sources'),
  createSource: (data: any) => api.post('/hot-topic-sources', data),
  updateSource: (id: number, data: any) => api.put(`/hot-topic-sources/${id}`, data),
  deleteSource: (id: number) => api.delete(`/hot-topic-sources/${id}`),
  // Topics
  listTopics: (params?: any) => api.get('/hot-topics', { params }),
  triggerFetch: (data: any) => api.post('/hot-topics/fetch', data, { timeout: 600000 }),
  deleteTopic: (id: number) => api.delete(`/hot-topics/${id}`),
  clearTopics: (params?: any) => api.delete('/hot-topics/clear', { params }),
}

// Sentiment
export const sentimentAPI = {
  listPlatforms: () => api.get('/sentiment/platforms'),
  search: (data: { keyword: string; platforms: string[]; post_limit?: number }) =>
    api.post('/sentiment/search', data),
  listTasks: (params?: { status?: string; page?: number; page_size?: number }) =>
    api.get('/sentiment/tasks', { params }),
  getTask: (id: number) => api.get(`/sentiment/tasks/${id}`),
  deleteTask: (id: number) => api.delete(`/sentiment/tasks/${id}`),
  triggerDeepAnalysis: (postId: number) => api.post(`/sentiment/posts/${postId}/deep-analyze`),
  getDeepAnalysisStatus: (postId: number) => api.get(`/sentiment/posts/${postId}/deep-analyze`),
  checkCDPStatus: () => api.get('/tools/cdp-status'),
  repairCDP: () => api.post('/tools/cdp-repair'),
}

// Intelligence Reports
export const intelligenceAPI = {
  // Categories
  listCategories: () => api.get('/intelligence/categories'),
  createCategory: (data: { name: string; level: number; parent_id?: number; sort_order?: number }) =>
    api.post('/intelligence/categories', data),
  updateCategory: (id: number, data: { name?: string; sort_order?: number; is_active?: boolean }) =>
    api.put(`/intelligence/categories/${id}`, data),
  deleteCategory: (id: number) => api.delete(`/intelligence/categories/${id}`),
  // Reports
  generate: (data: {
    topic: string; category_id?: number; title?: string;
    search_engines?: string[]; crawl_platforms?: string[];
    max_search_results?: number; max_sources?: number;
  }) => api.post('/intelligence/reports/generate', data),
  listReports: (params?: { status?: string; category_id?: number; page?: number; page_size?: number }) =>
    api.get('/intelligence/reports', { params }),
  getReport: (id: number) => api.get(`/intelligence/reports/${id}`),
  regenerate: (id: number) => api.post(`/intelligence/reports/${id}/regenerate`),
  deleteReport: (id: number) => api.delete(`/intelligence/reports/${id}`),
  exportDocx: (id: number) =>
    api.post(`/intelligence/reports/${id}/export`, { format: 'docx' }, { responseType: 'blob' }),
  exportPdf: (id: number) =>
    api.post(`/intelligence/reports/${id}/export`, { format: 'pdf' }, { responseType: 'blob' }),
}

export default api

// Account Match
export const accountMatchAPI = {
  search: (data: { target_name: string; platforms: string[]; match_mode?: string; anchor_platform?: string }) =>
    api.post('/account-match/search', data),
  listTasks: () => api.get('/account-match/tasks'),
  getTask: (id: number) => api.get(`/account-match/tasks/${id}`),
  deleteTask: (id: number) => api.delete(`/account-match/tasks/${id}`),
}
