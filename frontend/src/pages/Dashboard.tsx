import { useNavigate } from 'react-router-dom';
import { Alert, Button, Card, Col, Progress, Row, Space, Statistic, Tag, Typography } from 'antd';
import {
  ArrowRightOutlined,
  CalendarOutlined,
  FireOutlined,
  HeartOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getProfile } from '../api/profile';
import type { Profile } from '../types/profile';
import type { Plan } from '../types/plan';
import PageContainer from '../components/PageContainer';
import { bmiCategory, calcBmi, calcBmr, GOAL_LABEL } from '../utils/format';

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

export default function Dashboard() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['profile'],
    queryFn: getProfile,
    retry: false,
  });
  const profile = data?.profile;
  const plan = qc.getQueryData<Plan>(['plan']) ?? null;

  const missing = isError && (error as { status?: number })?.status === 404;

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

  const bmi = calcBmi(profile.height_cm, profile.weight_kg);
  const cat = bmiCategory(bmi);
  const targets = plan?.nutrition_targets ?? {};
  const calories = typeof targets.calories === 'number' ? targets.calories : calcBmr(profile);
  const protein = typeof targets.protein === 'number' ? targets.protein : null;
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
          <Card variant="borderless">
            <Statistic
              title="BMI"
              valueRender={() => (
                <Space align="baseline">
                  <span style={{ fontSize: 28, fontWeight: 600 }}>{isLoading ? '–' : bmi.toFixed(1)}</span>
                  <Tag color={cat.color} style={{ marginInlineEnd: 0 }}>
                    {cat.label}
                  </Tag>
                </Space>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card variant="borderless">
            <Statistic title="每日热量目标" value={calories} suffix="kcal" prefix={<FireOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card variant="borderless">
            <Statistic
              title="蛋白质目标"
              value={protein ?? '–'}
              suffix={protein !== null ? 'g' : ''}
              prefix={<HeartOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card variant="borderless">
            <Statistic title="每周训练" value={profile.days_per_week} suffix="天" prefix={<CalendarOutlined />} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 0 }}>
        <Col xs={24} lg={14}>
          <Card
            title="当前计划"
            variant="borderless"
            extra={
              plan ? (
                <Button type="link" size="small" onClick={() => navigate('/plan')}>
                  查看详情 <ArrowRightOutlined />
                </Button>
              ) : null
            }
          >
            {plan ? (
              <Space direction="vertical" style={{ width: '100%' }} size={12}>
                <Space>
                  <Tag color="blue">{GOAL_LABEL[profile.goal]}</Tag>
                  <Typography.Text type="secondary">
                    {dayCount > 0 ? `${dayCount} 天训练安排` : '训练安排待生成'}
                  </Typography.Text>
                </Space>
                <Typography.Paragraph ellipsis={{ rows: 3 }} style={{ color: '#5A6478', marginBottom: 0 }}>
                  {plan.rationale || '暂无安排说明。'}
                </Typography.Paragraph>
                <Button icon={<ThunderboltOutlined />} onClick={() => navigate('/chat')}>
                  对话调整计划
                </Button>
              </Space>
            ) : (
              <Space direction="vertical" align="center" style={{ width: '100%', padding: '12px 0' }}>
                <Typography.Text type="secondary">还没有计划，立即生成你的第一份方案</Typography.Text>
                <Button type="primary" onClick={() => navigate('/plan')}>
                  生成一周计划
                </Button>
              </Space>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card title="画像完成度" variant="borderless">
            <Progress type="dashboard" percent={completion} strokeColor="#3A5BDE" />
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
