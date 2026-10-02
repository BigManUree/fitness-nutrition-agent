export interface Exercise {
  name?: string;
  name_zh?: string;
  name_en?: string;
  sets?: number;
  reps?: string;
  rest?: string;
  note?: string;
  weight?: string;
  rpe?: string;
  [k: string]: unknown;
}

export interface PlanDay {
  day?: number;
  focus?: string;
  exercises?: Exercise[];
  [k: string]: unknown;
}

export interface MealItem {
  food?: string;
  food_zh?: string;
  amount?: string;
  note?: string;
  [k: string]: unknown;
}

export interface DailyMeals {
  breakfast?: MealItem[];
  lunch?: MealItem[];
  dinner?: MealItem[];
  [k: string]: MealItem[] | undefined;
}

export interface Plan {
  weekly_plan?: PlanDay[];
  daily_meals?: DailyMeals;
  nutrition_targets?: { calories?: number; protein?: number; [k: string]: unknown };
  nutrition_totals?: Record<string, unknown>;
  rationale?: string;
  weight_guidance?: string;
  progression_guide?: string;
  translation_warning?: string;
  [k: string]: unknown;
}
