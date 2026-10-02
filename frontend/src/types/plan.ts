export interface ExerciseVideo {
  url?: string;
  [k: string]: unknown;
}

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

  // ---- MCP 动作库富字段（enrich_plan 注入，translate_plan 提供 _zh 译文）----
  overview?: string;
  overview_zh?: string;
  instructions?: string[];
  instructions_zh?: string[];
  form_tips?: string[];
  form_tips_zh?: string[];
  common_mistakes?: string[];
  common_mistakes_zh?: string[];
  safety?: string;
  safety_zh?: string;
  variations?: string[];
  variations_zh?: string[];
  keywords?: string[];
  keywords_zh?: string[];
  videos?: ExerciseVideo[];
  image_urls?: string[];
  progression?: string;

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
  amount_g?: number;
  note?: string;
  estimated_portion?: boolean;
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
