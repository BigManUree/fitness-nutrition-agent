import { lazy, Suspense, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Card, Spin, Tabs, Typography, message } from 'antd';
import { ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getProfile } from '../api/profile';
import { generatePlan } from '../api/plan';
import { ApiError } from '../api/client';
import type { Plan as PlanType } from '../types/plan';
import PageContainer from '../components/PageContainer';

// 进入页面时尚无计划、表格不渲染（生成需 1–3 分钟）。两个表格都懒加载，
// 把 antd Table 实现推迟到真正出现计划时，缩小 Plan 页进入时的初始体积。
const PlanTable = lazy(() => import('../components/PlanTable'));
const MealTable = lazy(() => import('../components/MealTable'));
const tabFallback = <Spin style={{ display: 'block', margin: '40px auto' }} />;

/** 从结构化错误 detail 中取出可读原因（含后端透传的模型/服务错误数组）。 */
function extractErrorDetail(err: unknown): { title: string; description?: string } {
  if (!(err instanceof ApiError)) {
    return { title: err instanceof Error ? err.message : '生成失败' };
  }
  if (err.status === 400) return { title: '请先到「用户画像」填写并保存画像' };
  if (err.status === 422) {
    const d = err.detail as { message?: unknown } | null;
    return { title: typeof d?.message === 'string' ? d.message : '画像信息不全，请补全后重试' };
  }
  // 502：后端可能返回 {message, errors} 或字符串
  const d = err.detail as { message?: unknown; errors?: unknown } | string | null;
  if (typeof d === 'object' && d !== null) {
    const errors = Array.isArray(d.errors) ? (d.errors as unknown[]).filter((e): e is string => typeof e === 'string') : [];
    const title = typeof d.message === 'string' ? d.message : err.message;
    if (errors.length) {
      const isBalance = errors.some((e) => /Insufficient Balance|402|余额/i.test(e));
      return {
        title: isBalance ? '模型服务商账户余额不足（402），请充值后重试' : title,
        description: errors.join('；'),
      };
    }
    return { title };
  }
  return { title: err.message || '生成失败，请确认 MCP 桥接与模型服务可用' };
}

export default function Plan() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // 初始化优先读缓存：从 Chat 应用替换后返回本页时，编辑随缓存保留（与 Chat.tsx 一致）
  const [plan, setPlan] = useState<PlanType | null>(
    () => queryClient.getQueryData<PlanType>(['plan']) ?? null,
  );
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
      message.success('计划已生成');
    } catch (err) {
      const { title, description } = extractErrorDetail(err);
      message.open({ type: 'error', content: title, duration: 5 });
      if (description) setErrors([description]);
    } finally {
      setGenerating(false);
    }
  };

  if (isLoading) return <Spin style={{ display: 'block', margin: '80px auto' }} />;
  if (!data) {
    return (
      <PageContainer title="计划生成" subtitle="先完成画像，再生成一周训练与三餐">
        <Alert
          type="info"
          showIcon
          message="请先填写画像"
          description="生成计划需要先保存用户画像。"
          action={<Button onClick={() => navigate('/profile')}>去填写画像</Button>}
        />
      </PageContainer>
    );
  }

  return (
    <PageContainer
      title="计划生成"
      subtitle="检索真实动作与食物数据，由模型按你的条件编排，约需 1–3 分钟"
      extra={
        plan ? (
          <Button icon={<ReloadOutlined />} onClick={generate} loading={generating}>
            重新生成
          </Button>
        ) : null
      }
    >
      <Card variant="borderless">
        {!plan && (
          <Button type="primary" size="large" icon={<ThunderboltOutlined />} loading={generating} onClick={generate}>
            生成一周训练 + 一日三餐
          </Button>
        )}

        {generating && (
          <Alert
            type="info"
            showIcon
            style={{ marginTop: 16 }}
            message="正在检索动作/食物并由模型编排…"
            description="此过程包含多次数据检索与校验，请保持页面打开，约 1–3 分钟。"
          />
        )}

        {errors.length > 0 && !generating && (
          <Alert type="warning" message={`过程中有 ${errors.length} 条提示`} description={errors.join('；')} style={{ marginTop: 16 }} />
        )}
        {plan && validation && !validation.valid && (
          <Alert type="warning" message={'计划未通过校验：' + (validation.violations ?? []).join('；')} style={{ marginTop: 16 }} />
        )}
        {plan?.translation_warning && <Alert type="warning" message={plan.translation_warning} style={{ marginTop: 16 }} />}

        {plan && (
          <>
            <Tabs
              style={{ marginTop: plan ? 16 : 0 }}
              items={[
                {
                  key: 'weekly',
                  label: '一周训练计划',
                  children: (
                    <>
                      {plan.weight_guidance && <Alert type="info" message={plan.weight_guidance} style={{ marginBottom: 12 }} />}
                      {plan.progression_guide && <Alert type="info" message={plan.progression_guide} style={{ marginBottom: 12 }} />}
                      <Suspense fallback={tabFallback}>
                        <PlanTable plan={plan} />
                      </Suspense>
                    </>
                  ),
                },
                {
                  key: 'meals',
                  label: '一日三餐',
                  children: (
                    <Suspense fallback={tabFallback}>
                      <MealTable plan={plan} />
                    </Suspense>
                  ),
                },
              ]}
            />
            <Typography.Title level={5} style={{ marginTop: 16 }}>
              为什么这样安排
            </Typography.Title>
            <Typography.Paragraph style={{ color: '#5A6478' }}>{plan.rationale ?? ''}</Typography.Paragraph>
            <Button type="primary" ghost style={{ marginTop: 8 }} onClick={() => navigate('/chat')}>
              对话调整计划
            </Button>
          </>
        )}
      </Card>
    </PageContainer>
  );
}
