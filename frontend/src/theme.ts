import type { ThemeConfig } from 'antd'

const theme: ThemeConfig = {
  token: {
    colorPrimary: '#22C55E',
    colorBgContainer: '#1A2332',
    colorBgElevated: '#111827',
    colorBgLayout: '#050B14',
    colorText: '#F8FAFC',
    colorTextSecondary: '#CBD5E1',
    colorTextTertiary: '#94A3B8',
    colorBorder: 'rgba(248,250,252,0.08)',
    colorBorderSecondary: 'rgba(248,250,252,0.06)',
    colorSuccess: '#22C55E',
    colorError: '#EF4444',
    colorWarning: '#F59E0B',
    colorInfo: '#60A5FA',
    borderRadius: 12,
    fontSize: 15,
    fontFamily: "'Inter', 'Noto Sans SC', sans-serif",
  },
  components: {
    Layout: {
      siderBg: '#0B1120',
      headerBg: '#0B1120',
      bodyBg: '#050B14',
    },
    Menu: {
      darkSubMenuItemBg: '#0B1120',
      darkItemColor: 'rgba(248,250,252,0.55)',
      darkItemSelectedBg: 'rgba(34,197,94,0.12)',
      darkItemSelectedColor: '#F8FAFC',
      darkItemHoverColor: '#F8FAFC',
      darkItemHoverBg: 'rgba(248,250,252,0.06)',
      itemBorderRadius: 10,
      itemHeight: 46,
      itemMarginInline: 8,
      fontSize: 15,
    },
    Card: {
      colorBgContainer: '#1A2332',
      colorBorderSecondary: 'rgba(248,250,252,0.08)',
      borderRadiusLG: 14,
    },
    Table: {
      colorBgContainer: '#1A2332',
      headerBg: '#111827',
      headerColor: '#CBD5E1',
      rowHoverBg: 'rgba(34,197,94,0.06)',
      borderColor: 'rgba(248,250,252,0.08)',
      headerBorderRadius: 0,
      fontSize: 15,
    },
    Input: {
      colorBgContainer: '#1A2332',
      colorBorder: 'rgba(248,250,252,0.1)',
      activeBorderColor: '#22C55E',
      hoverBorderColor: 'rgba(34,197,94,0.5)',
      addonBg: '#111827',
      colorTextPlaceholder: 'rgba(248,250,252,0.3)',
      fontSize: 15,
    },
    Select: {
      colorBgContainer: '#1A2332',
      colorBorder: 'rgba(248,250,252,0.1)',
      optionSelectedBg: 'rgba(34,197,94,0.12)',
      fontSize: 15,
    },
    Modal: {
      contentBg: '#1A2332',
      headerBg: '#1A2332',
      titleColor: '#F8FAFC',
    },
    Button: {
      defaultBg: '#1A2332',
      defaultBorderColor: 'rgba(248,250,252,0.12)',
      defaultColor: '#F8FAFC',
      defaultHoverBorderColor: 'rgba(34,197,94,0.4)',
      defaultHoverColor: '#22C55E',
      primaryShadow: '0 2px 14px rgba(34,197,94,0.25)',
      borderRadius: 10,
      fontSize: 15,
      controlHeight: 44,
    },
    Tag: {
      defaultBg: '#111827',
      defaultColor: '#CBD5E1',
      borderRadiusSM: 8,
      fontSize: 13,
    },
    Statistic: {
      titleFontSize: 14,
      contentFontSize: 32,
    },
    Tooltip: {
      colorBgSpotlight: '#111827',
      colorTextLightSolid: '#F8FAFC',
    },
    Popconfirm: {
      colorBgElevated: '#1A2332',
    },
    Message: {
      contentBg: '#1A2332',
    },
  },
}

export default theme
