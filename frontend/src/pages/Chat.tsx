import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Card, Input, Select, Space, Spin, message } from 'antd';
import { CheckCircleOutlined, SendOutlined } from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import { useChatStream } from '../hooks/useChatStream';
import type { Plan } from '../types/plan';
import PageContainer from '../components/PageContainer';

export default function Chat() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [plan, setPlan] = useState<Plan | null>(() => qc.getQueryData<Plan>(['plan']) ?? null);
  const [input, setInput] = useState('');
  const [chosen, setChosen] = useState<string | null>(null);
  const { messages, streaming, pending, error, send } = useChatStream(plan ?? {});
  const bottomRef = useRef<HTMLDivElement>(null);

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
    const next: Plan = JSON.parse(JSON.stringify(plan));
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
      <Card variant="borderless" styles={{ body: { padding: 0 } }}>
        {/* 消息区：固定高度滚动 */}
        <div style={{ height: 'calc(100vh - 300px)', minHeight: 320, overflowY: 'auto', padding: 20, background: '#F7F9FC' }}>
          {messages.length === 0 && (
            <Alert type="info" showIcon message="开始对话" description="告诉我你想调整哪里，我会基于真实动作库给出候选。" />
          )}
          {messages.map((m, i) => {
            const isUser = m.role === 'user';
            return (
              <div key={i} style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start', marginBottom: 12 }}>
                <div
                  style={{
                    background: isUser ? '#3A5BDE' : '#FFFFFF',
                    color: isUser ? '#fff' : '#1D2433',
                    padding: '10px 14px',
                    borderRadius: 12,
                    maxWidth: '78%',
                    whiteSpace: 'pre-wrap',
                    boxShadow: isUser ? 'none' : '0 1px 2px rgba(16,24,40,0.06)',
                    border: isUser ? 'none' : '1px solid #E6E9F0',
                  }}
                >
                  {m.content || (streaming ? <Spin size="small" /> : '')}
                </div>
              </div>
            );
          })}
          <div ref={bottomRef} />
        </div>

        {/* 替代动作区 */}
        {pending?.alternatives?.length ? (
          <div style={{ padding: '12px 20px', borderTop: '1px solid #E6E9F0' }}>
            <Space>
              <Select
                style={{ width: 260 }}
                placeholder="选择替代动作"
                value={chosen ?? undefined}
                onChange={setChosen}
                options={pending.alternatives.map((a) => ({ value: a.name, label: a.name }))}
              />
              <Button type="primary" icon={<CheckCircleOutlined />} disabled={!chosen} onClick={() => chosen && applySubstitution(chosen)}>
                应用到当前计划
              </Button>
            </Space>
          </div>
        ) : null}

        {error && (
          <div style={{ padding: '12px 20px 0' }}>
            <Alert type="error" message={error} />
          </div>
        )}

        {/* 输入区 */}
        <div style={{ padding: 16, borderTop: '1px solid #E6E9F0' }}>
          <Space.Compact style={{ width: '100%' }}>
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onPressEnter={trySend}
              placeholder="输入你的调整需求…"
              disabled={streaming}
              size="large"
            />
            <Button type="primary" icon={<SendOutlined />} disabled={!input.trim() || streaming} onClick={trySend} size="large">
              发送
            </Button>
          </Space.Compact>
        </div>
      </Card>
    </PageContainer>
  );
}
