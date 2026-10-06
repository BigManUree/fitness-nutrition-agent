import { ReactNode } from 'react';
import { Space, Typography } from 'antd';
import { fontSize, spacing } from '../theme/tokens';

interface Props {
  title: ReactNode;
  subtitle?: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  /** 内容区最大宽度，默认适配表单/表格阅读宽度 */
  maxWidth?: number;
}

/**
 * 统一页面骨架：页面标题 + 说明 + 右侧操作区 + 内容。
 * 让所有内页拥有一致的留白与层级；窄屏下操作区自动换到标题下方。
 */
export default function PageContainer({ title, subtitle, extra, children, maxWidth = 1080 }: Props) {
  return (
    <div style={{ maxWidth, margin: '0 auto' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: spacing.md,
          marginBottom: spacing.lg,
        }}
      >
        <div style={{ minWidth: 0 }}>
          <Typography.Title level={4} style={{ margin: 0, fontSize: fontSize.pageTitle }}>
            {title}
          </Typography.Title>
          {subtitle && (
            <Typography.Paragraph type="secondary" style={{ margin: `${spacing.sm}px 0 0`, fontSize: fontSize.secondary }}>
              {subtitle}
            </Typography.Paragraph>
          )}
        </div>
        {extra && <Space style={{ marginLeft: 'auto' }}>{extra}</Space>}
      </div>
      {children}
    </div>
  );
}
