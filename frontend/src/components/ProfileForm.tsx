import { useState } from 'react';
import { Alert, Button, Form, InputNumber, Radio, Select, message } from 'antd';
import type { Goal, Profile } from '../types/profile';

const EQUIPMENT_OPTIONS = [
  { value: 'gym', label: '健身房（全部器械）' },
  { value: 'dumbbell', label: '哑铃' },
  { value: 'barbell', label: '杠铃' },
  { value: 'kettlebell', label: '壶铃' },
  { value: 'band', label: '弹力带' },
  { value: 'bodyweight', label: '自重（无器械）' },
  { value: 'bench', label: '卧推凳' },
  { value: 'cable', label: '绳索器械' },
  { value: 'machine', label: '固定器械' },
  { value: 'pull-up bar', label: '引体杆' },
];

const GOAL_OPTIONS: { value: Goal; label: string }[] = [
  { value: 'fat_loss', label: '减脂' },
  { value: 'muscle_gain', label: '增肌' },
  { value: 'recomp', label: '塑形（减脂+增肌）' },
  { value: 'general_fitness', label: '综合体能/健康' },
];

interface Props {
  initial?: Profile;
  onSave: (profile: Profile) => Promise<unknown>;
  onSaved: () => void;
  saving: boolean;
  saveWarning?: string | null;
}

const positiveRule = (label: string) => ({
  validator: (_: unknown, value: number | null) =>
    value === null || value === undefined || value > 0
      ? Promise.resolve()
      : Promise.reject(new Error(`${label}需大于 0`)),
});

export default function ProfileForm({ initial, onSave, onSaved, saving, saveWarning }: Props) {
  const [error, setError] = useState<string | null>(null);

  const finish = async (values: Profile) => {
    setError(null);
    try {
      await onSave(values);
      message.success('画像已保存 ✅');
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    }
  };

  return (
    <Form<Profile> layout="vertical" initialValues={initial} onFinish={finish} requiredMark>
      <Form.Item name="sex" label="性别" rules={[{ required: true, message: '请选择性别' }]}>
        <Radio.Group options={[{ value: 'male', label: '男' }, { value: 'female', label: '女' }]} />
      </Form.Item>

      <Form.Item
        name="age"
        label="年龄"
        rules={[
          { required: true, message: '请输入年龄' },
          { type: 'number', min: 14, max: 80, message: '年龄需在 14–80 之间' },
        ]}
      >
        <InputNumber style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item
        name="height_cm"
        label="身高（cm）"
        rules={[{ required: true, message: '请输入身高' }, positiveRule('身高')]}
      >
        <InputNumber style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item
        name="weight_kg"
        label="体重（kg）"
        rules={[{ required: true, 'message': '请输入体重' }, positiveRule('体重')]}
      >
        <InputNumber style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item name="goal" label="目标" rules={[{ required: true, message: '请选择目标' }]}>
        <Select options={GOAL_OPTIONS} />
      </Form.Item>

      <Form.Item
        name="days_per_week"
        label="每周训练天数"
        rules={[
          { required: true, message: '请输入训练天数' },
          { type: 'number', min: 1, max: 7, message: '训练天数需在 1–7 之间' },
        ]}
      >
        <InputNumber style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item
        name="equipment"
        label="可用器械"
        rules={[{ required: true, message: '请至少选择一种器械' }]}
      >
        <Select mode="multiple" options={EQUIPMENT_OPTIONS} placeholder="可多选" />
      </Form.Item>

      <Form.Item name="medical_conditions" label="伤病情况（可选）">
        <Select mode="tags" placeholder="如：膝盖、肩（回车添加）" open={false} />
      </Form.Item>

      <Form.Item name="dietary_preferences" label="饮食偏好（可选）">
        <Select mode="tags" placeholder="如：素食、低碳（回车添加）" open={false} />
      </Form.Item>

      <Form.Item name="allergies" label="过敏（可选）">
        <Select mode="tags" placeholder="如：花生、乳糖（回车添加）" open={false} />
      </Form.Item>

      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}
      {saveWarning && <Alert type="warning" message={saveWarning} style={{ marginBottom: 16 }} />}

      <Button type="primary" htmlType="submit" loading={saving} block>
        保存画像
      </Button>
    </Form>
  );
}
