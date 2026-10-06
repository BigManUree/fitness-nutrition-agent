import { useQuery } from '@tanstack/react-query';
import { getLatestPlan } from '../api/plan';

/** 查询键（Plan / Dashboard / Chat 共用同一缓存）。 */
export const LATEST_PLAN_KEY = ['latestPlan'] as const;

/**
 * 拉取当前账号最近一次持久化的计划。
 * 用于整页刷新 / 重新登录后恢复计划视图（404 表示从未生成，静默处理）。
 */
export function useLatestPlan() {
  return useQuery({
    queryKey: LATEST_PLAN_KEY,
    queryFn: getLatestPlan,
    retry: false,
    staleTime: 60_000,
  });
}
