import type { Goal, Sex } from '../types/profile';

export const SEX_LABEL: Record<Sex, string> = {
  male: '男',
  female: '女',
};

export const GOAL_LABEL: Record<Goal, string> = {
  fat_loss: '减脂',
  muscle_gain: '增肌',
  recomp: '塑形',
  general_fitness: '综合体能',
};

/** BMI 分级（中国成人标准）。 */
export function bmiCategory(bmi: number): { label: string; color: string } {
  if (bmi < 18.5) return { label: '偏瘦', color: '#E8A13A' };
  if (bmi < 24) return { label: '正常', color: '#18A058' };
  if (bmi < 28) return { label: '超重', color: '#E8A13A' };
  return { label: '肥胖', color: '#E04F4F' };
}

export function calcBmi(heightCm: number, weightKg: number): number {
  const m = heightCm / 100;
  if (m <= 0) return 0;
  return weightKg / (m * m);
}

/**
 * 基础代谢率（Mifflin-St Jeor），用于在缺少模型营养目标时给出参考值。
 * 仅供前端展示，计划仍以后端 nutrition_targets 为准。
 */
export function calcBmr(p: {
  sex: Sex;
  age: number;
  height_cm: number;
  weight_kg: number;
}): number {
  const base = 10 * p.weight_kg + 6.25 * p.height_cm - 5 * p.age;
  return Math.round(p.sex === 'male' ? base + 5 : base - 161);
}
