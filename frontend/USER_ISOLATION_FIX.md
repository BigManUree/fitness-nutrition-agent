# 多用户数据隔离验证步骤

## 问题描述
新用户注册登录后还没有画像，但计划界面显示的是上一个用户的计划。

## 根本原因
前端 React Query 缓存（`['plan']` 和 `['latestPlan']`）是全局的，没有按用户隔离。
登出时只清理了 `user` 状态，没有清理缓存，导致新用户看到旧数据。

## 修复方案
在 `AuthProvider` 的登出逻辑中调用 `queryClient.clear()` 清理所有 React Query 缓存。

## 验证步骤

### 手动测试
1. **用户 A 操作**
   - 注册用户 A（如 `testuser1`）
   - 登录用户 A
   - 填写用户 A 的画像（如：25岁男性，增肌目标）
   - 生成计划 A
   - 确认计划 A 显示正确

2. **用户 A 登出**
   - 点击登出按钮

3. **用户 B 操作**
   - 注册用户 B（如 `testuser2`）
   - 登录用户 B
   - **验证点 1**：计划页面应显示空白（无计划），不应显示用户 A 的计划
   - **验证点 2**：画像页面应显示空白或提示填写画像

4. **用户 B 生成自己的计划**
   - 填写用户 B 的画像（如：30岁女性，减脂目标）
   - 生成计划 B
   - 确认计划 B 显示正确（与用户 A 的计划不同）

### 自动化测试
运行前端测试：
```bash
cd frontend
npm test
```

应看到 23 个测试通过，包括新增的缓存清理测试：
- `AuthProvider > clears React Query cache on logout to prevent data leakage between users`

## 技术细节

### 修改的文件
- `frontend/src/auth/AuthProvider.tsx` — 在登出时清理缓存
- `frontend/src/auth/AuthProvider.test.tsx` — 新增缓存清理测试
- `frontend/src/pages/Login.test.tsx` — 添加 QueryClientProvider
- `frontend/src/test/smoke.test.tsx` — 添加 QueryClientProvider

### 关键代码
```typescript
// AuthProvider.tsx
const queryClient = useQueryClient();

const logout = useCallback(async () => {
  try {
    await apiLogout();
  } catch {
    /* 服务端失败也清本地会话 */
  }
  setUser(null);
  // 清理所有 React Query 缓存，防止新用户看到旧数据
  queryClient.clear();
}, [queryClient]);
```

## 预期结果
- ✅ 用户切换时，旧数据被完全清理
- ✅ 新用户登录后，看到空白状态（无画像、无计划）
- ✅ 每个用户只能看到自己的数据
- ✅ 所有测试通过
