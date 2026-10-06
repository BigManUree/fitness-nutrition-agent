import { Alert, Card, Statistic, Table, Tag, Typography } from 'antd';
import { Row, Col } from 'antd';
import type { MealItem, Plan } from '../types/plan';
import { palette, spacing } from '../theme/tokens';

function renderFood(_food: string | undefined, r: MealItem) {
  const en = r.food;
  const zh = r.food_zh;
  if (!en && !zh) return '—';
  return zh && zh !== en ? `${zh}（${en}）` : zh ?? en;
}

function renderAmount(_v: string | undefined, r: MealItem) {
  return (
    <span>
      {r.amount ?? '—'}{' '}
      {r.estimated_portion && (
        <Tag
          style={{
            marginInlineEnd: 0,
            color: palette.warning,
            background: palette.warningBg,
            border: `1px solid ${palette.warning}22`,
          }}
        >
          估算
        </Tag>
      )}
    </span>
  );
}

const mealColumns = [
  { title: '食物', dataIndex: 'food', key: 'food', render: renderFood },
  { title: '分量', dataIndex: 'amount', key: 'amount', render: renderAmount },
  { title: '克重', dataIndex: 'amount_g', key: 'amount_g', width: 90,
    render: (v?: number) => (v ? `${v}g` : '—') },
  { title: '说明', dataIndex: 'note', key: 'note', render: (v?: string) => v ?? '' },
];

const MEALS: { key: 'breakfast' | 'lunch' | 'dinner'; label: string }[] = [
  { key: 'breakfast', label: '早餐' },
  { key: 'lunch', label: '午餐' },
  { key: 'dinner', label: '晚餐' },
];

export default function MealTable({ plan }: { plan: Plan }) {
  const meals = plan.daily_meals ?? {};
  // 后端字段为 target_calories / target_protein_g
  const targets = plan.nutrition_targets;
  const totals = plan.nutrition_totals as
    | { calories?: number; protein_g?: number }
    | undefined;

  return (
    <div>
      {targets && (
        <Alert
          type="info"
          style={{ marginBottom: 12 }}
          message={`全天目标：热量 ${targets.target_calories ?? '—'} kcal · 蛋白质 ${targets.target_protein_g ?? '—'} g`}
        />
      )}

      {MEALS.map((m) => {
        // antd rowKey 回调只收 record（无 index），这里把 index 注入 key，
        // 避免同名/无名字物导致重复 React key。
        const rows = (meals[m.key] ?? []).map((r, i) => ({ ...r, key: `${m.key}-${i}` }));
        return (
          <div key={m.key} style={{ marginBottom: 16 }}>
            <Typography.Title level={5} style={{ marginBottom: 8 }}>
              {m.label}
            </Typography.Title>
            <Table
              rowKey="key"
              columns={mealColumns}
              dataSource={rows}
              pagination={false}
              size="small"
            />
          </div>
        );
      })}

      {/* 实际核算：确定性核算的三餐合计，与目标对照 */}
      {totals && (totals.calories || totals.protein_g) && (
        <Row gutter={[16, 16]} style={{ marginTop: spacing.sm }}>
          <Col xs={24} sm={12}>
            <Card size="small">
              <Statistic title="三餐实际热量" value={totals.calories ?? 0} suffix="kcal" />
            </Card>
          </Col>
          <Col xs={24} sm={12}>
            <Card size="small">
              <Statistic title="三餐实际蛋白质" value={totals.protein_g ?? 0} suffix="g" precision={1} />
            </Card>
          </Col>
        </Row>
      )}
    </div>
  );
}
