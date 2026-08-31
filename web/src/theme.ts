import type { ThemeConfig } from 'antd'

import type { ThemeMode } from './stores/themeStore'

// 参考 MemoryBear 设计语言：近黑主色 + 蓝色强调 + 柔和阴影 + 中性灰
export const theme: ThemeConfig = {
  token: {
    colorPrimary: '#155EEF',
    colorInfo: '#155EEF',
    colorSuccess: '#369F21',
    colorError: '#FF5D34',
    colorTextBase: '#171719',
    colorBgLayout: '#FAFAFA',
    borderRadius: 8,
    fontSize: 14,
    fontSizeLG: 16,
    fontSizeSM: 12,
    lineHeight: 1.5715,
    controlHeight: 36,
    fontFamily:
      "'PingFang SC', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Microsoft YaHei', sans-serif",
    boxShadowSecondary:
      '0px 4px 6px -2px rgba(16, 24, 40, 0.03), 0px 12px 16px -4px rgba(16, 24, 40, 0.08)',
  },
  components: {
    Layout: {
      siderBg: '#ffffff',
      headerBg: '#ffffff',
      headerHeight: 64,
      bodyBg: '#FAFAFA',
    },
    Menu: {
      itemBg: '#ffffff',
      itemSelectedBg: '#EEF4FF',
      itemSelectedColor: '#155EEF',
      itemHoverBg: '#F7F7F7',
      itemColor: '#475467',
      itemHeight: 40,
      itemMarginInline: 10,
      itemMarginBlock: 4,
      fontSize: 14,
      groupTitleColor: '#98A2B3',
      groupTitleFontSize: 12,
    },
    Card: {
      borderRadiusLG: 12,
    },
    Button: {
      controlHeight: 36,
      fontWeight: 500,
    },
    Input: {
      fontSize: 14,
    },
    Modal: {
      borderRadiusLG: 16,
      titleFontSize: 17,
      headerBg: '#ffffff',
      paddingMD: 24,
      paddingContentHorizontalLG: 24,
    },
  },
}

const themeColors: Record<ThemeMode, { primary: string; success: string; error: string; layout: string; surface: string }> = {
  paper: {
    primary: '#3956A4',
    success: '#3E7C59',
    error: '#B84A3A',
    layout: '#F4EFE7',
    surface: '#FFFCF6',
  },
}

export function getThemeConfig(mode: ThemeMode): ThemeConfig {
  const colors = themeColors[mode]
  return {
    ...theme,
    token: {
      ...theme.token,
      colorPrimary: colors.primary,
      colorInfo: colors.primary,
      colorSuccess: colors.success,
      colorError: colors.error,
      colorBgLayout: colors.layout,
    },
    components: {
      ...theme.components,
      Layout: {
        ...theme.components?.Layout,
        siderBg: colors.surface,
        headerBg: colors.surface,
        bodyBg: colors.layout,
      },
      Menu: {
        ...theme.components?.Menu,
        itemBg: colors.surface,
        itemSelectedColor: colors.primary,
      },
    },
  }
}
