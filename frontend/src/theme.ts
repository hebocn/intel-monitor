import type { ThemeConfig } from 'antd'

const theme: ThemeConfig = {
  token: {
    colorPrimary: '#2d6a4f',
    colorBgContainer: '#ffffff',
    colorBgElevated: '#f8faf9',
    colorBgLayout: '#f4f7f5',
    colorText: '#1a2e26',
    colorTextSecondary: '#5f7a6e',
    colorBorder: 'rgba(45,106,79,0.1)',
    colorSuccess: '#52b788',
    colorError: '#c75050',
    colorWarning: '#d4a042',
    borderRadius: 12,
    fontSize: 15,
    fontFamily: "'Inter', 'Noto Sans SC', sans-serif",
  },
  components: {
    Layout: {
      siderBg: '#1a2e26',
      headerBg: '#ffffff',
      bodyBg: '#f4f7f5',
    },
    Menu: {
      darkSubMenuItemBg: '#1a2e26',
      darkItemColor: 'rgba(255,255,255,0.45)',
      darkItemSelectedBg: 'rgba(255,255,255,0.1)',
      darkItemSelectedColor: '#ffffff',
      darkItemHoverColor: '#ffffff',
      darkItemHoverBg: 'rgba(255,255,255,0.06)',
      itemBorderRadius: 10,
      itemHeight: 46,
      itemMarginInline: 8,
      fontSize: 15,
    },
    Card: {
      colorBgContainer: '#ffffff',
      colorBorderSecondary: 'rgba(45,106,79,0.08)',
      borderRadiusLG: 14,
    },
    Table: {
      colorBgContainer: '#ffffff',
      headerBg: '#f8faf9',
      headerColor: '#8fa69a',
      rowHoverBg: 'rgba(45,106,79,0.04)',
      borderColor: 'rgba(45,106,79,0.08)',
      headerBorderRadius: 0,
      fontSize: 15,
    },
    Input: {
      colorBgContainer: '#ffffff',
      colorBorder: 'rgba(45,106,79,0.12)',
      activeBorderColor: '#2d6a4f',
      hoverBorderColor: 'rgba(45,106,79,0.4)',
      addonBg: '#f8faf9',
      fontSize: 15,
    },
    Select: {
      colorBgContainer: '#ffffff',
      colorBorder: 'rgba(45,106,79,0.12)',
      optionSelectedBg: 'rgba(45,106,79,0.08)',
      fontSize: 15,
    },
    Modal: {
      contentBg: '#ffffff',
      headerBg: '#ffffff',
      titleColor: '#1a2e26',
    },
    Button: {
      defaultBg: '#ffffff',
      defaultBorderColor: 'rgba(45,106,79,0.15)',
      defaultColor: '#1a2e26',
      primaryShadow: '0 2px 12px rgba(45,106,79,0.2)',
      borderRadius: 10,
      fontSize: 15,
      controlHeight: 44,
    },
    Tag: {
      defaultBg: '#eef4f0',
      defaultColor: '#5f7a6e',
      borderRadiusSM: 8,
      fontSize: 13,
    },
    Statistic: {
      titleFontSize: 14,
      contentFontSize: 32,
    },
    Tooltip: {
      colorBgSpotlight: '#1a2e26',
      colorTextLightSolid: '#ffffff',
    },
    Popconfirm: {
      colorBgElevated: '#ffffff',
    },
    Message: {
      contentBg: '#ffffff',
    },
  },
}

export default theme
