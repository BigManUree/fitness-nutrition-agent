import { ReactNode } from 'react';
import { Typography } from 'antd';
import { palette } from '../theme/tokens';

/**
 * 认证页左右分栏外壳：左侧品牌叙事区（深色），右侧表单区。
 * 小屏下自动隐藏左侧，仅保留表单。
 */
export default function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <div
        style={{
          flex: '1 1 46%',
          background: `linear-gradient(150deg, ${palette.siderBg} 0%, ${palette.authGradientMid} 60%, ${palette.primary} 130%)`,
          color: palette.white,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          padding: 48,
        }}
        className="auth-hero"
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 9,
              background: 'rgba(255,255,255,0.16)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 700,
            }}
          >
            健
          </div>
          <span style={{ fontWeight: 600, fontSize: 17 }}>健身营养 Agent</span>
        </div>

        <div>
          <Typography.Title style={{ color: palette.white, fontSize: 34, lineHeight: 1.3, marginBottom: 16 }}>
            数据驱动的
            <br />
            每周训练与三餐方案
          </Typography.Title>
          <Typography.Paragraph style={{ color: 'rgba(255,255,255,0.72)', fontSize: 15, maxWidth: 380 }}>
            动作与食物全部来自专业数据库，由模型按你的身体条件编排，真实可执行，不编造、不盲从。
          </Typography.Paragraph>
        </div>

        <Typography.Text style={{ color: 'rgba(255,255,255,0.5)' }}>
          © {new Date().getFullYear()} Fitness Nutrition Agent
        </Typography.Text>
      </div>

      <div
        style={{
          flex: '1 1 54%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 24,
          background: palette.bgContainer,
        }}
      >
        <div style={{ width: '100%', maxWidth: 380 }}>{children}</div>
      </div>

      {/* 响应式：窄屏隐藏品牌区 */}
      <style>{`
        @media (max-width: 820px) { .auth-hero { display: none !important; } }
      `}</style>
    </div>
  );
}
