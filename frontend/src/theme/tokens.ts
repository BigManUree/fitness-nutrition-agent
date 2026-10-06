import type { ThemeConfig } from 'antd';

/**
 * 企业级设计令牌（单一事实来源）。
 * 颜色 / 间距 / 字号 / 圆角在此集中定义：
 * - 经 ConfigProvider 下发给 antd（antTheme）
 * - 同步注入为 CSS 变量（tokens.css），供原生元素与行内样式引用
 * 业务组件只引用语义化令牌，不散落硬编码色值。
 */
export const palette = {
  // 品牌主色：沉稳的性能蓝（iris blue），专业、可信赖
  primary: '#3A5BDE',
  primaryHover: '#5571E8',
  primaryActive: '#2D47B8',
  primaryBg: '#EEF2FF', // 主色弱底色（标签/选中行）

  // 语义色
  success: '#18A058',
  successBg: '#E8F6EF',
  warning: '#C77F1A',
  warningBg: '#FBF1E1',
  error: '#D54941',
  errorBg: '#FBECEB',
  info: '#3A5BDE',

  // 中性文本
  text: '#1D2433',
  textSecondary: '#5A6478',
  textTertiary: '#8A93A6',
  textDisabled: '#B7BECB',

  // 边框 / 分隔线
  border: '#E4E8F0',
  borderStrong: '#D2D8E4',
  divider: '#ECEDF1',

  // 背景
  bgLayout: '#F4F6FA',
  bgContainer: '#FFFFFF',
  bgSubtle: '#F7F9FC',
  bgHover: '#F2F5FA',
  bgActive: '#E9EEF8',

  // 侧边导航（深色）
  siderBg: '#141A2E',
  siderItem: '#9AA4C0',
  siderItemHoverBg: '#1F2745',
  siderItemActiveBg: '#3A5BDE',

  // 深色/品牌色之上的文字
  white: '#FFFFFF',
  // 认证页品牌渐变中间色
  authGradientMid: '#24305E',
} as const;

/**
 * 间距阶（px）。页面内 padding / margin / gap 只允许取此阶。
 */
export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  base: 16,
  lg: 20,
  xl: 24,
  xxl: 32,
  xxxl: 40,
  huge: 48,
} as const;

/**
 * 字号阶（px）。
 */
export const fontSize = {
  caption: 12, // 辅助/表格补充信息
  secondary: 13, // 次级正文
  body: 14, // 正文
  subtitle: 16, // 小标题
  sectionTitle: 18, // 区块标题
  pageTitle: 22, // 页面标题
} as const;

/** 字重 */
export const fontWeight = {
  regular: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
} as const;

/** 圆角阶 */
export const radius = {
  sm: 6,
  md: 8,
  lg: 10,
  xl: 12,
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
    colorText: palette.text,
    colorTextSecondary: palette.textSecondary,
    colorTextTertiary: palette.textTertiary,
    colorTextDisabled: palette.textDisabled,
    colorBorder: palette.border,
    colorBorderSecondary: palette.border,
    colorBgLayout: palette.bgLayout,
    colorBgContainer: palette.bgContainer,
    colorBgElevated: palette.bgContainer,
    fontFamily,
    borderRadius: radius.md,
    fontSize: fontSize.body,
    controlHeight: 36,
    wireframe: false,
    motionDurationMid: '180ms',
  },
  components: {
    Layout: {
      headerBg: palette.bgContainer,
      headerHeight: 60,
      headerPadding: '0 20px',
      bodyBg: palette.bgLayout,
      siderBg: palette.siderBg,
    },
    Menu: {
      darkItemBg: 'transparent',
      darkSubMenuItemBg: 'transparent',
      darkItemColor: palette.siderItem,
      darkItemHoverColor: '#FFFFFF',
      darkItemHoverBg: palette.siderItemHoverBg,
      darkItemSelectedBg: palette.siderItemActiveBg,
      darkItemSelectedColor: '#FFFFFF',
      itemBorderRadius: radius.sm,
      itemMarginInline: 12,
      itemHeight: 42,
    },
    Card: {
      borderRadiusLG: radius.lg,
      paddingLG: spacing.lg,
      // 克制的企业级卡片：细边框 + 极弱阴影
      colorBorderSecondary: palette.border,
      boxShadowTertiary: '0 1px 2px rgba(16, 24, 40, 0.04)',
    },
    Table: {
      headerBg: palette.bgSubtle,
      headerColor: palette.textSecondary,
      headerSplitColor: 'transparent',
      borderColor: palette.divider,
      rowHoverBg: palette.bgHover,
      cellPaddingBlock: 10,
    },
    Button: {
      controlHeight: 36,
      fontWeight: fontWeight.medium,
      primaryShadow: 'none',
      defaultShadow: 'none',
    },
    Tabs: {
      inkBarColor: palette.primary,
      itemColor: palette.textSecondary,
      itemSelectedColor: palette.primary,
      horizontalMargin: '0 20px 0 0',
    },
    Tag: {
      defaultBg: palette.bgSubtle,
      defaultColor: palette.textSecondary,
    },
    Modal: {
      borderRadiusLG: radius.lg,
    },
    Input: {
      activeShadow: `0 0 0 2px ${palette.primaryBg}`,
    },
  },
};
