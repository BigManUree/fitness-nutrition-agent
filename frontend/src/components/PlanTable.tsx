import { Table, Typography } from 'antd';
import type { Exercise, Plan } from '../types/plan';
import ExerciseDetail from './ExerciseDetail';
import { fontSize, palette } from '../theme/tokens';

const { Text } = Typography;

function renderName(_name: string | undefined, row: Exercise) {
  const zh = row.name_zh;
  const en = row.name ?? row.name_en;
  if (!en && !zh) return '—';
  return zh && zh !== en ? `${zh}（${en}）` : zh ?? en;
}

/** 合并重量区间与目标强度，如 "20-40kg（RPE 7-8）"。 */
function renderWeight(_: unknown, row: Exercise) {
  const weight = row.weight;
  const rpe = row.rpe;
  if (weight && rpe) return `${weight}（${rpe}）`;
  return weight || rpe || '—';
}

/** 动作要领（中文译文优先），多条合并展示。 */
function renderFormTips(_: unknown, row: Exercise) {
  const tips = row.form_tips_zh?.length ? row.form_tips_zh : row.form_tips;
  if (!tips?.length) return <span />;
  return (
    <Text style={{ fontSize: fontSize.caption, color: palette.textSecondary }}>
      {tips.map((t) => `· ${t}`).join('\n')}
    </Text>
  );
}

const textOrDash = (v?: string | number) =>
  v === undefined || v === '' ? '—' : v;

const columns = [
  { title: '动作', dataIndex: 'name', key: 'name', width: 200, render: renderName },
  { title: '建议重量', key: 'weight', width: 150, render: renderWeight },
  { title: '组数', dataIndex: 'sets', key: 'sets', width: 70, render: textOrDash },
  { title: '次数', dataIndex: 'reps', key: 'reps', width: 90, render: textOrDash },
  { title: '休息', dataIndex: 'rest', key: 'rest', width: 90, render: textOrDash },
  { title: '动作要领', key: 'form_tips', render: renderFormTips },
  { title: '说明', dataIndex: 'note', key: 'note', width: 140, render: (v?: string) => textOrDash(v) },
];

/** 该动作是否有可展开的详细资料。 */
function hasDetail(ex: Exercise): boolean {
  return Boolean(
    ex.image_urls?.length ||
      ex.videos?.length ||
      ex.overview_zh ||
      ex.overview ||
      ex.instructions_zh?.length ||
      ex.instructions?.length ||
      ex.form_tips_zh?.length ||
      ex.form_tips?.length ||
      ex.common_mistakes_zh?.length ||
      ex.common_mistakes?.length ||
      ex.safety_zh ||
      ex.safety ||
      ex.variations_zh?.length ||
      ex.variations?.length ||
      ex.keywords_zh?.length ||
      ex.keywords?.length ||
      ex.progression,
  );
}

export default function PlanTable({ plan }: { plan: Plan }) {
  // 归一化 day 序号：LLM 偶发缺省 day 时按顺序补齐，保证渲染 key 稳定
  const days = (plan.weekly_plan ?? []).map((day, i) => ({ ...day, day: day.day ?? i + 1 }));
  if (days.length === 0) {
    return <Typography.Text type="secondary">暂无训练计划</Typography.Text>;
  }
  return (
    <>
      {days.map((day) => (
        <div key={`day-${day.day}`} style={{ marginBottom: 24 }}>
          <Typography.Title level={5} style={{ marginBottom: 8 }}>
            第 {day.day} 天 · {day.focus ?? ''}
          </Typography.Title>
          <Table
            rowKey="key"
            columns={columns}
            dataSource={(day.exercises ?? []).map((ex, j) => ({ ...ex, key: `d${day.day}-ex${j}` }))}
            pagination={false}
            size="small"
            scroll={{ x: 960 }}
            expandable={{
              expandedRowRender: (record: Exercise) => (
                <div style={{ padding: '8px 8px 8px 32px' }}>
                  <ExerciseDetail ex={record} />
                </div>
              ),
              rowExpandable: (record: Exercise) => hasDetail(record),
            }}
          />
        </div>
      ))}
    </>
  );
}
