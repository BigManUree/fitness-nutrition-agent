import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Card, Grid, Input, Select, Spin, message } from 'antd';
import { CheckCircleOutlined, SendOutlined } from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import { useChatStream } from '../hooks/useChatStream';
import type { Plan } from '../types/plan';
import PageContainer from '../components/PageContainer';
import { palette, spacing } from '../theme/tokens';
import { useLatestPlan } from '../hooks/useLatestPlan';

export default function Chat() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [plan, setPlan] = useState<Plan | null>(() => qc.getQueryData<Plan>(['plan']) ?? null);
  const [input, setInput] = useState('');
  const [chosen, setChosen] = useState<string | null>(null);
  const { messages, streaming, pending, error, send } = useChatStream(plan ?? {});
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

  const applySubstitution = (newName: string) => {
    if (!pending) return;
    const target = pending.original_exercise.trim().toLowerCase();
    const next: Plan = structuredClone(plan);
    let changed = false;
    for (const day of next.weekly_plan ?? []) {
      for (const ex of day.exercises ?? []) {
        if (typeof ex.name === 'string' && ex.name.trim().toLowerCase() === target) {
          ex.name = newName;
          changed = true;
        }
      }
    }
    if (changed) {
      setPlan(next);
      qc.setQueryData(['plan'], next);
      message.success(`已替换为 ${newName}`);
    } else {
      message.warning('当前计划中未找到该原动作');
    }
    setChosen(null);
  };

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
          {messages.length === 0 && (
            <Alert type="info" showIcon message="开始对话" description="告诉我你想调整哪里，我会基于真实动作库给出候选。" />
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

        {/* 替代动作区：窄屏纵向排列，保证 Select 与按钮不溢出 */}
        {pending?.alternatives?.length ? (
          <div style={{ padding: `${spacing.md} ${spacing.lg}`, borderTop: `1px solid ${palette.border}` }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: spacing.sm }}>
              <Select
                style={{ flex: '1 1 220px', minWidth: 0, maxWidth: 320 }}
                placeholder="选择替代动作"
                value={chosen ?? undefined}
                onChange={setChosen}
                options={pending.alternatives.map((a) => ({ value: a.name, label: a.name }))}
              />
              <Button
                type="primary"
                icon={<CheckCircleOutlined />}
                disabled={!chosen}
                onClick={() => chosen && applySubstitution(chosen)}
              >
                应用到当前计划
              </Button>
            </div>
          </div>
        ) : null}

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
