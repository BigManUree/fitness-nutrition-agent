import type { ThemeConfig } from 'antd';

/**
 * 企业级设计令牌。
 * 所有颜色 / 圆角 / 间距在此集中定义，经 ConfigProvider 下发给 antd，
 * 业务组件只引用语义化令牌，不散落硬编码色值。
 */
export const palette = {
  // 品牌主色：沉稳的性能蓝（iris blue），专业、可信赖
  primary: '#3A5BDE',
  primaryHover: '#5571E8',
  primaryActive: '#2D47B8',

  // 语义色
  success: '#18A058',
  warning: '#E8A13A',
  error: '#E04F4F',
  info: '#3A5BDE',

  // 中性色
  text: '#1D2433',
  textSecondary: '#5A6478',
  border: '#E6E9F0',
  bgLayout: '#F4F6FA',
  bgContainer: '#FFFFFF',
  bgSubtle: '#F7F9FC',

  // 侧边导航（深色）
  siderBg: '#141A2E',
  siderItem: '#9AA4C0',
  siderItemActiveBg: '#3A5BDE',
} as const;

/** 不依赖外网 CDN 的跨平台字体栈（含中文回退）。 */
export const fontFamily =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", ' +
  '"Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif';

export const antTheme: ThemeConfig = {
  token: {
    colorPrimary: palette.primary,
    colorSuccess: palette.success,
    colorWarning: palette.warning,
    colorError: palette.error,
    colorInfo: palette.info,
    colorTextBase: palette.text,
    colorBorder: palette.border,
    colorBgLayout: palette.bgLayout,
    fontFamily,
    borderRadius: 8,
    fontSize: 14,
    controlHeight: 36,
    wireframe: false,
  },
  components: {
    Layout: {
      headerBg: palette.bgContainer,
      headerHeight: 60,
      headerPadding: '0 24px',
      bodyBg: palette.bgLayout,
      siderBg: palette.siderBg,
    },
    Menu: {
      darkItemBg: 'transparent',
      darkSubMenuItemBg: 'transparent',
      darkItemColor: palette.siderItem,
      darkItemSelectedBg: palette.siderItemActiveBg,
      darkItemHoverColor: '#FFFFFF',
      itemBorderRadius: 8,
      itemMarginInline: 12,
    },
    Card: {
      borderRadiusLG: 12,
      paddingLG: 20,
    },
    Table: {
      headerBg: palette.bgSubtle,
      headerColor: palette.textSecondary,
      borderColor: palette.border,
    },
    Button: {
      controlHeight: 36,
      fontWeight: 500,
    },
  },
};
