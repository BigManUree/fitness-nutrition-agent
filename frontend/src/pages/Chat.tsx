import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Input, List, Select, Space, Spin, Typography, message } from 'antd';
import { useQueryClient } from '@tanstack/react-query';
import { useChatStream } from '../hooks/useChatStream';
import type { Plan } from '../types/plan';

export default function Chat() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [plan, setPlan] = useState<Plan | null>(() => qc.getQueryData<Plan>(['plan']) ?? null);
  const [input, setInput] = useState('');
  const [chosen, setChosen] = useState<string | null>(null);
  const { messages, streaming, pending, error, send } = useChatStream(plan ?? {});

  if (!plan) {
    return (
      <Alert
        type="info"
        style={{ margin: 40 }}
        message="请先生成计划"
        description="对话调整需要基于一份已生成的计划。"
        action={<Button onClick={() => navigate('/plan')}>去生成</Button>}
      />
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

  return (
    <div style={{ maxWidth: 800, margin: '40px auto' }}>
      <Typography.Title level={3}>💬 对话调整</Typography.Title>

      <List
        dataSource={messages}
        renderItem={(m) => (
          <List.Item style={{ justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div
              style={{
                background: m.role === 'user' ? '#e6f4ff' : '#f5f5f5',
                padding: '8px 12px',
                borderRadius: 8,
                maxWidth: '80%',
                whiteSpace: 'pre-wrap',
              }}
            >
              {m.content || (streaming ? <Spin size="small" /> : '')}
            </div>
          </List.Item>
        )}
      />

      {pending?.alternatives?.length ? (
        <Space style={{ marginTop: 12 }}>
          <Select
            style={{ width: 240 }}
            placeholder="选择替代动作"
            value={chosen ?? undefined}
            onChange={setChosen}
            options={pending.alternatives.map((a) => ({ value: a.name, label: a.name }))}
          />
          <Button type="primary" disabled={!chosen} onClick={() => chosen && applySubstitution(chosen)}>
            ✅ 应用到当前计划
          </Button>
        </Space>
      ) : null}

      {error && <Alert type="error" message={error} style={{ marginTop: 12 }} />}

      <Space.Compact style={{ width: '100%', marginTop: 16 }}>
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={() => {
            if (input.trim() && !streaming) {
              send(input.trim());
              setInput('');
            }
          }}
          placeholder="如：把卧推换成哑铃能做的"
          disabled={streaming}
        />
        <Button
          type="primary"
          disabled={!input.trim() || streaming}
          onClick={() => {
            send(input.trim());
            setInput('');
          }}
        >
          发送
        </Button>
      </Space.Compact>
    </div>
  );
}
