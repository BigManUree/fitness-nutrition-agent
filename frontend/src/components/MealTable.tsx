import { Alert, Table, Typography } from 'antd';
import type { MealItem, Plan } from '../types/plan';

function renderFood(_food: string | undefined, r: MealItem) {
  const en = r.food;
  const zh = r.food_zh;
  if (!en) return '—';
  return zh && zh !== en ? `${zh}（${en}）` : en;
}

const mealColumns = [
  { title: '食物', dataIndex: 'food', key: 'food', render: renderFood },
  { title: '分量', dataIndex: 'amount', key: 'amount', render: (v?: string) => v ?? '' },
  { title: '说明', dataIndex: 'note', key: 'note', render: (v?: string) => v ?? '' },
];

const MEALS: { key: 'breakfast' | 'lunch' | 'dinner'; label: string }[] = [
  { key: 'breakfast', label: '早餐' },
  { key: 'lunch', label: '午餐' },
  { key: 'dinner', label: '晚餐' },
];

export default function MealTable({ plan }: { plan: Plan }) {
  const meals = plan.daily_meals ?? {};
  const targets = plan.nutrition_targets;
  return (
    <div>
      {targets && (
        <Alert
          type="info"
          style={{ marginBottom: 12 }}
          message={`目标热量约 ${targets.calories ?? '—'} kcal · 蛋白质约 ${targets.protein ?? '—'} g`}
        />
      )}
      {MEALS.map((m) => {
        // antd rowKey 回调只收 record（无 index），这里把 index 注入 key，
        // 避免同名/无名字物导致重复 React key。
        const rows = (meals[m.key] ?? []).map((r, i) => ({ ...r, key: `${m.key}-${i}` }));
        return (
          <div key={m.key} style={{ marginBottom: 16 }}>
            <Typography.Title level={5}>{m.label}</Typography.Title>
            <Table rowKey="key" columns={mealColumns} dataSource={rows} pagination={false} size="small" />
          </div>
        );
      })}
    </div>
  );
}
