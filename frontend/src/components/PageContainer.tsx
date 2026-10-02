import { ReactNode } from 'react';
import { Space, Typography } from 'antd';

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
 * 让所有内页拥有一致的留白与层级。
 */
export default function PageContainer({ title, subtitle, extra, children, maxWidth = 1080 }: Props) {
  return (
    <div style={{ maxWidth, margin: '0 auto' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 16,
          marginBottom: 20,
        }}
      >
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            {title}
          </Typography.Title>
          {subtitle && (
            <Typography.Paragraph type="secondary" style={{ margin: '6px 0 0' }}>
              {subtitle}
            </Typography.Paragraph>
          )}
        </div>
        {extra && <Space>{extra}</Space>}
      </div>
      {children}
    </div>
  );
}
