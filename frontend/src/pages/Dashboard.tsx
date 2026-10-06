import { useNavigate } from 'react-router-dom';
import { Alert, Button, Card, Col, Progress, Row, Skeleton, Space, Statistic, Tag, Typography } from 'antd';
import {
  ArrowRightOutlined,
  CalendarOutlined,
  FireOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getProfile } from '../api/profile';
import type { Profile } from '../types/profile';
import type { Plan } from '../types/plan';
import PageContainer from '../components/PageContainer';
import { bmiCategory, calcBmi, calcBmr, GOAL_LABEL } from '../utils/format';
import { palette } from '../theme/tokens';
import { useLatestPlan } from '../hooks/useLatestPlan';

/** 画像关键字段完成度（0–100）。 */
function profileCompletion(p: Profile): number {
  const fields: unknown[] = [
    p.sex,
    p.age,
    p.height_cm,
    p.weight_kg,
    p.goal,
    p.days_per_week,
    p.equipment?.length,
  ];
  const done = fields.filter((v) => v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && v.length === 0)).length;
  return Math.round((done / fields.length) * 100);
}

/** 计算营养目标，返回已解析的热量/蛋白质值。 */
function computeNutrition(plan: Plan | null, profile: Profile) {
  const targets = plan?.nutrition_targets ?? {};
  const calories =
    (typeof targets.target_calories === 'number' ? targets.target_calories : undefined) ??
    (typeof targets.calories === 'number' ? targets.calories : undefined) ??
    calcBmr(profile);
  const protein =
    (typeof targets.target_protein_g === 'number' ? targets.target_protein_g : undefined) ??
    (typeof targets.protein === 'number' ? targets.protein : undefined) ??
    null;
  return { calories, protein };
}

// ─── 拆分的子组件，降低主组件复杂度 ──────────────────────────

/** 顶部指标卡片：统一骨架占位，避免数据到达时跳动。 */
function MetricCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <Statistic title={title} valueRender={() => children} />
    </Card>
  );
}

/** 画像缺失时的占位提示。 */
function ProfileGuard({
  missing,
  profile,
  navigate,
}: {
  missing: boolean;
  profile: Profile | undefined;
  navigate: (path: string) => void;
}) {
  if (missing || !profile) {
    return (
      <PageContainer title="工作台" subtitle="从完善你的身体画像开始，生成个性化训练与饮食方案">
        <Alert
          type="info"
          showIcon
          message="尚未填写画像"
          description="生成计划前需要先保存一份身体画像，大约 1 分钟。"
          action={
            <Button type="primary" onClick={() => navigate('/profile')}>
              去填写画像
            </Button>
          }
        />
      </PageContainer>
    );
  }
  return null;
}

/** 当前计划卡片内容：有计划时显示摘要，无计划时引导生成。 */
function PlanCardContent({
  plan,
  profile,
  dayCount,
  navigate,
}: {
  plan: Plan | null;
  profile: Profile;
  dayCount: number;
  navigate: (path: string) => void;
}) {
  if (plan) {
    return (
      <Space direction="vertical" style={{ width: '100%' }} size={12}>
        <Space wrap>
          <Tag color={palette.primary} style={{ marginInlineEnd: 0 }}>
            {GOAL_LABEL[profile.goal]}
          </Tag>
          <Typography.Text type="secondary">
            {dayCount > 0 ? `${dayCount} 天训练安排` : '训练安排待生成'}
          </Typography.Text>
        </Space>
        <Typography.Paragraph ellipsis={{ rows: 3 }} style={{ color: palette.textSecondary, marginBottom: 0 }}>
          {plan.rationale || '暂无安排说明。'}
        </Typography.Paragraph>
        <Button onClick={() => navigate('/chat')}>对话调整计划</Button>
      </Space>
    );
  }
  return (
    <Space direction="vertical" align="center" style={{ width: '100%', padding: '12px 0' }}>
      <Typography.Text type="secondary">还没有计划，立即生成你的第一份方案</Typography.Text>
      <Button type="primary" onClick={() => navigate('/plan')}>
        生成一周计划
      </Button>
    </Space>
  );
}

// ─── 主组件 ──────────────────────────────────────────────────

export default function Dashboard() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['profile'],
    queryFn: getProfile,
    retry: false,
  });
  const profile = data?.profile;
  const { data: latestPlanData } = useLatestPlan();
  const plan = qc.getQueryData<Plan>(['plan']) ?? latestPlanData?.plan ?? null;

  const missing = isError && (error as { status?: number })?.status === 404;
  if (missing || !profile) {
    return (
      <ProfileGuard missing={missing} profile={profile} navigate={navigate} />
    );
  }

  const bmi = calcBmi(profile.height_cm, profile.weight_kg);
  const cat = bmiCategory(bmi);
  const { calories, protein } = computeNutrition(plan, profile);
  const completion = profileCompletion(profile);
  const dayCount = plan?.weekly_plan?.length ?? 0;

  return (
    <PageContainer
      title="工作台"
      subtitle="你的身体指标、营养目标与计划概览"
      extra={
        <Button type="primary" icon={<ThunderboltOutlined />} onClick={() => navigate('/plan')}>
          {plan ? '重新生成计划' : '生成计划'}
        </Button>
      }
    >
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} xl={6}>
          <MetricCard title="BMI">
            {isLoading ? (
              <Skeleton.Input active size="small" />
            ) : (
              <Space align="baseline">
                <span style={{ fontSize: 28, fontWeight: 600 }}>{bmi.toFixed(1)}</span>
                <Tag color={cat.color} style={{ marginInlineEnd: 0 }}>
                  {cat.label}
                </Tag>
              </Space>
            )}
          </MetricCard>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <MetricCard title="每日热量目标">
            <span style={{ fontSize: 28, fontWeight: 600 }}>
              <FireOutlined style={{ color: palette.warning, marginRight: 6, fontSize: 22 }} />
              {calories}
              <span style={{ fontSize: 14, fontWeight: 400, color: palette.textSecondary, marginLeft: 4 }}>kcal</span>
            </span>
          </MetricCard>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <MetricCard title="蛋白质目标">
            <span style={{ fontSize: 28, fontWeight: 600 }}>
              {protein !== null ? protein : '–'}
              {protein !== null && (
                <span style={{ fontSize: 14, fontWeight: 400, color: palette.textSecondary, marginLeft: 4 }}>g</span>
              )}
            </span>
          </MetricCard>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <MetricCard title="每周训练">
            <span style={{ fontSize: 28, fontWeight: 600 }}>
              <CalendarOutlined style={{ color: palette.primary, marginRight: 6, fontSize: 22 }} />
              {profile.days_per_week}
              <span style={{ fontSize: 14, fontWeight: 400, color: palette.textSecondary, marginLeft: 4 }}>天</span>
            </span>
          </MetricCard>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 0 }}>
        <Col xs={24} lg={14}>
          <Card
            title="当前计划"
            extra={
              plan ? (
                <Button type="link" size="small" onClick={() => navigate('/plan')}>
                  查看详情 <ArrowRightOutlined />
                </Button>
              ) : null
            }
          >
            <PlanCardContent plan={plan} profile={profile} dayCount={dayCount} navigate={navigate} />
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card title="画像完成度">
            <Progress type="dashboard" percent={completion} strokeColor={palette.primary} />
            <div style={{ marginTop: 16 }}>
              <Space wrap>
                <Tag>{GOAL_LABEL[profile.goal]}</Tag>
                <Tag>{profile.days_per_week} 天/周</Tag>
                <Tag>{profile.equipment.length} 类器械</Tag>
              </Space>
            </div>
            <Button block style={{ marginTop: 16 }} onClick={() => navigate('/profile')}>
              编辑画像
            </Button>
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
