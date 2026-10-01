import { Table, Typography } from 'antd';
import type { Exercise, Plan } from '../types/plan';

function renderName(_name: string | undefined, row: Exercise) {
  const zh = row.name_zh;
  const en = row.name ?? row.name_en;
  if (!en) return '—';
  return zh && zh !== en ? `${zh}（${en}）` : en;
}

const columns = [
  { title: '动作', dataIndex: 'name', key: 'name', render: renderName },
  { title: '组数', dataIndex: 'sets', key: 'sets', render: (v?: number) => v ?? '' },
  { title: '次数', dataIndex: 'reps', key: 'reps', render: (v?: string) => v ?? '' },
  { title: '休息', dataIndex: 'rest', key: 'rest', render: (v?: string) => v ?? '' },
  { title: '说明', dataIndex: 'note', key: 'note', render: (v?: string) => v ?? '' },
];

export default function PlanTable({ plan }: { plan: Plan }) {
  const days = plan.weekly_plan ?? [];
  if (days.length === 0) {
    return <Typography.Text type="secondary">暂无训练计划</Typography.Text>;
  }
  return (
    <>
      {days.map((day, i) => (
        <div key={i} style={{ marginBottom: 24 }}>
          <Typography.Title level={5}>
            第 {day.day ?? i + 1} 天 · {day.focus ?? ''}
          </Typography.Title>
          <Table
            rowKey={(r: Exercise) => r.name ?? ''}
            columns={columns}
            dataSource={day.exercises ?? []}
            pagination={false}
            size="small"
          />
        </div>
      ))}
    </>
  );
}
