import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Spin, Tabs, Typography, message } from 'antd';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getProfile } from '../api/profile';
import { generatePlan } from '../api/plan';
import { ApiError } from '../api/client';
import PlanTable from '../components/PlanTable';
import MealTable from '../components/MealTable';
import type { Plan as PlanType } from '../types/plan';

export default function Plan() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [plan, setPlan] = useState<PlanType | null>(null);
  const [validation, setValidation] = useState<{ valid: boolean; violations?: string[] } | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [generating, setGenerating] = useState(false);

  const { data, isLoading } = useQuery({ queryKey: ['profile'], queryFn: getProfile, retry: false });

  const generate = async () => {
    setGenerating(true);
    setErrors([]);
    try {
      const r = await generatePlan(data?.profile ?? null);
      setPlan(r.plan);
      setValidation(r.validation);
      setErrors(r.errors);
      queryClient.setQueryData(['plan'], r.plan);
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        message.error('请先到「用户画像」填写并保存画像');
      } else if (err instanceof ApiError && err.status === 422) {
        message.error('画像信息不全，请补全后重试');
      } else {
        message.error(err instanceof Error ? err.message : '生成失败，请确认 MCP 桥接已启动（make mcp-up）');
      }
    } finally {
      setGenerating(false);
    }
  };

  if (isLoading) return <Spin style={{ display: 'block', margin: '80px auto' }} />;
  if (!data) {
    return (
      <Alert
        type="info"
        style={{ margin: 40 }}
        message="请先填写画像"
        description="生成计划需要先保存用户画像。"
        action={<Button onClick={() => navigate('/profile')}>去填写画像</Button>}
      />
    );
  }

  return (
    <div style={{ maxWidth: 1000, margin: '40px auto' }}>
      <Typography.Title level={3}>📅 生成计划</Typography.Title>
      <Button type="primary" size="large" loading={generating} onClick={generate}>
        🚀 生成一周训练 + 一日三餐
      </Button>
      {generating && (
        <Alert type="info" message="正在检索动作/食物并由模型编排，约需 1–3 分钟…" style={{ marginTop: 16 }} />
      )}

      {errors.length > 0 && (
        <Alert type="warning" message={`过程中有 ${errors.length} 条提示`} description={errors.join('；')} style={{ marginTop: 16 }} />
      )}
      {plan && validation && !validation.valid && (
        <Alert type="warning" message={'计划未通过校验：' + (validation.violations ?? []).join('；')} style={{ marginTop: 16 }} />
      )}
      {plan?.translation_warning && <Alert type="warning" message={plan.translation_warning} style={{ marginTop: 16 }} />}

      {plan && (
        <>
          <Tabs
            style={{ marginTop: 16 }}
            items={[
              {
                key: 'weekly',
                label: '🏋️ 一周训练计划',
                children: (
                  <>
                    {plan.weight_guidance && <Alert type="info" message={plan.weight_guidance} style={{ marginBottom: 12 }} />}
                    {plan.progression_guide && <Alert type="info" message={plan.progression_guide} style={{ marginBottom: 12 }} />}
                    <PlanTable plan={plan} />
                  </>
                ),
              },
              { key: 'meals', label: '🍱 一日三餐', children: <MealTable plan={plan} /> },
            ]}
          />
          <Typography.Title level={5} style={{ marginTop: 24 }}>💡 为什么这样安排</Typography.Title>
          <Typography.Paragraph>{plan.rationale ?? ''}</Typography.Paragraph>
          <Button style={{ marginTop: 8 }} onClick={() => navigate('/chat')}>💬 对话调整计划</Button>
        </>
      )}
    </div>
  );
}
