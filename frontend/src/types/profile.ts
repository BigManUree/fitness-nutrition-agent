export type Sex = 'male' | 'female';
export type Goal = 'fat_loss' | 'muscle_gain' | 'recomp' | 'general_fitness';

export interface Profile {
  sex: Sex;
  age: number;
  height_cm: number;
  weight_kg: number;
  goal: Goal;
  days_per_week: number;
  equipment: string[];
  medical_conditions?: string[];
  dietary_preferences?: string[];
  allergies?: string[];
}
