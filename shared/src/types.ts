// ══════════════════════════════════════════════════
// AI Provider
// ══════════════════════════════════════════════════

export type AIProvider = 'minimax' | 'deepseek' | 'mimo'

export const AI_PROVIDER_LABELS: Record<string, string> = {
  minimax: 'MiniMax',
  deepseek: 'DeepSeek',
  mimo: 'MiMo',
}

// ══════════════════════════════════════════════════
// Dashboard / Platform
// ══════════════════════════════════════════════════

export interface PlatformConfig {
  label: string
  color: string
}

export const PLATFORM_CONFIG: Record<string, PlatformConfig> = {
  x: { label: 'X', color: '#1DA1F2' },
  youtube: { label: 'YouTube', color: '#FF0000' },
  xiaohongshu: { label: '小红书', color: '#FE2C55' },
  douyin: { label: '抖音', color: '#FFFFFF' },
  weibo: { label: '微博', color: '#E6162D' },
  bilibili: { label: 'B站', color: '#00A1D6' },
  reddit: { label: 'Reddit', color: '#FF4500' },
  toutiao: { label: '头条', color: '#E53333' },
  website: { label: '网站', color: '#6495ED' },
}

// ══════════════════════════════════════════════════
// Hot Topic Rank Colors
// ══════════════════════════════════════════════════

export const RANK_COLORS: Record<number, string> = {
  1: '#FFD700',
  2: '#C0C0C0',
  3: '#CD7F32',
}

// ══════════════════════════════════════════════════
// Category Colors
// ══════════════════════════════════════════════════

export const CATEGORY_COLORS: Record<string, string> = {
  Politics: '#F59E0B',
  Economy: '#3B82F6',
  Tech: '#A78BFA',
  Security: '#EF4444',
  Society: '#22C55E',
  Culture: '#EC4899',
  General: '#6B7280',
}
