import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Card, Grid, Input, Spin, message } from 'antd';
import { SendOutlined } from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import { useChatStream } from '../hooks/useChatStream';
import type { Plan } from '../types/plan';
import PageContainer from '../components/PageContainer';
import { palette, spacing } from '../theme/tokens';
import { LATEST_PLAN_KEY, useLatestPlan } from '../hooks/useLatestPlan';

export default function Chat() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [plan, setPlan] = useState<Plan | null>(() => qc.getQueryData<Plan>(['plan']) ?? null);
  const [input, setInput] = useState('');
  // 计划表只能在“AI 建议 → 用户同意”后由后端更换，done 时回传更新后的计划
  const handleAppliedPlan = (next: Plan) => {
    setPlan(next);
    qc.setQueryData(['plan'], next);
    qc.setQueryData(LATEST_PLAN_KEY, qc.getQueryData(LATEST_PLAN_KEY)
      ? { ...qc.getQueryData<{ plan: Plan }>(LATEST_PLAN_KEY)!, plan: next }
      : { plan: next });
    message.success('已按你的确认更换计划表中的动作');
  };
  const { messages, streaming, historyLoading, error, send } = useChatStream(
    plan ?? {},
    handleAppliedPlan,
  );
  const bottomRef = useRef<HTMLDivElement>(null);
  const isMobile = !Grid.useBreakpoint().sm;
  // 刷新后从服务器恢复最近计划，避免误报「请先生成计划」
  const { data: latestPlanData } = useLatestPlan();
  useEffect(() => {
    if (latestPlanData && !qc.getQueryData<Plan>(['plan'])) {
      setPlan(latestPlanData.plan);
      qc.setQueryData(['plan'], latestPlanData.plan);
    }
  }, [latestPlanData, qc]);

  // 新消息到达时滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streaming]);

  if (!plan) {
    return (
      <PageContainer title="对话调整">
        <Alert
          type="info"
          showIcon
          message="请先生成计划"
          description="对话调整需要基于一份已生成的计划。"
          action={<Button onClick={() => navigate('/plan')}>去生成</Button>}
        />
      </PageContainer>
    );
  }

  const trySend = () => {
    const text = input.trim();
    if (!text || streaming) return;
    send(text);
    setInput('');
  };

  return (
    <PageContainer title="对话调整" subtitle="用自然语言调整计划，例如「把卧推换成哑铃能做的」" maxWidth={880}>
      <Card styles={{ body: { padding: 0 } }}>
        {/* 消息区：高度自适应视口，内部滚动 */}
        <div
          style={{
            height: 'calc(100vh - 280px)',
            minHeight: 320,
            overflowY: 'auto',
            padding: spacing.lg,
            background: palette.bgSubtle,
          }}
        >
          {historyLoading && (
            <div style={{ textAlign: 'center', padding: spacing.lg }}>
              <Spin />
            </div>
          )}
          {!historyLoading && messages.length === 0 && (
            <Alert
              type="info"
              showIcon
              message="开始对话"
              description="告诉我你想调整哪里，我会基于真实动作库给出更换建议；你确认同意后，我才会修改计划表。"
            />
          )}
          {messages.map((m) => {
            const isUser = m.role === 'user';
            return (
              <div
                key={m.id}
                style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start', marginBottom: spacing.md }}
              >
                <div
                  style={{
                    background: isUser ? palette.primary : palette.bgContainer,
                    color: isUser ? palette.white : palette.text,
                    padding: '10px 14px',
                    borderRadius: 10,
                    maxWidth: '78%',
                    whiteSpace: 'pre-wrap',
                    border: isUser ? 'none' : `1px solid ${palette.border}`,
                    lineHeight: 1.6,
                  }}
                >
                  {m.content || (streaming ? <Spin size="small" /> : '')}
                </div>
              </div>
            );
          })}
          <div ref={bottomRef} />
        </div>

        {error && (
          <div style={{ padding: `${spacing.md} ${spacing.lg} 0` }}>
            <Alert type="error" message={error} />
          </div>
        )}

        {/* 输入区：桌面同一行，移动端纵向堆叠 */}
        <div
          style={{
            padding: spacing.base,
            borderTop: `1px solid ${palette.border}`,
            display: 'flex',
            flexDirection: isMobile ? 'column' : 'row',
            gap: spacing.sm,
          }}
        >
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={trySend}
            placeholder="输入你的调整需求…"
            disabled={streaming}
            size="large"
            style={{ flex: 1, minWidth: 0 }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            disabled={!input.trim() || streaming}
            onClick={trySend}
            size="large"
            block={isMobile}
          >
            发送
          </Button>
        </div>
      </Card>
    </PageContainer>
  );
}
