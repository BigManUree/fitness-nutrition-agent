import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useChatStream } from './useChatStream';
import { getChatHistory, streamChat } from '../api/chat';

vi.mock('../api/chat', () => ({
  streamChat: vi.fn(),
  getChatHistory: vi.fn(),
}));

const PLAN = { weekly_plan: [] };

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, wrapper };
}

function captureHandlers(impl: (h: any) => void) {
  vi.mocked(streamChat).mockImplementation((_plan, _msgs, _msg, handlers) => {
    impl(handlers);
    return Promise.resolve();
  });
}

async function renderAndWait(wrapper: any) {
  const hook = renderHook(() => useChatStream(PLAN), { wrapper });
  await waitFor(() => expect(hook.result.current.historyLoading).toBe(false));
  return hook;
}

describe('useChatStream', () => {
  beforeEach(() => {
    vi.mocked(streamChat).mockReset();
    vi.mocked(getChatHistory).mockReset();
    vi.mocked(getChatHistory).mockResolvedValue({ messages: [], pending: null });
  });

  it('restores persisted server history on mount', async () => {
    vi.mocked(getChatHistory).mockResolvedValue({
      messages: [
        { role: 'user', content: '把卧推换掉' },
        { role: 'assistant', content: '建议换成 Dumbbell Press，你同意吗？' },
      ],
      pending: null,
    });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useChatStream(PLAN), { wrapper });
    await waitFor(() => expect(result.current.historyLoading).toBe(false));
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[1].content).toContain('Dumbbell Press');
  });

  it('accumulates tokens into last assistant message', async () => {
    captureHandlers((h) => {
      h.onToken('你');
      h.onToken('好');
      h.onDone({ tool_results: [], applied_plan: null });
    });
    const { wrapper } = createWrapper();
    const { result } = await renderAndWait(wrapper);
    await act(async () => {
      await result.current.send('你好');
    });
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[1].content).toBe('你好');
    expect(result.current.streaming).toBe(false);
  });

  it('invokes onAppliedPlan when the server returns the applied plan', async () => {
    const updatedPlan = { weekly_plan: [{ day: 1, exercises: [{ name: 'Dumbbell Press' }] }] };
    captureHandlers((h) => {
      h.onDone({ tool_results: [], applied_plan: updatedPlan });
    });
    const onAppliedPlan = vi.fn();
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useChatStream(PLAN, onAppliedPlan), { wrapper });
    await waitFor(() => expect(result.current.historyLoading).toBe(false));
    await act(async () => {
      await result.current.send('同意，换吧');
    });
    expect(onAppliedPlan).toHaveBeenCalledWith(updatedPlan);
  });

  it('removes the empty assistant bubble when the stream fails before any token', async () => {
    captureHandlers((h) => {
      h.onError('网络错误');
    });
    const { wrapper } = createWrapper();
    const { result } = await renderAndWait(wrapper);
    await act(async () => {
      await result.current.send('你好');
    });
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]).toMatchObject({ role: 'user', content: '你好' });
    expect(result.current.error).toBe('网络错误');
  });

  it('keeps partial content when the stream fails mid-way', async () => {
    captureHandlers((h) => {
      h.onToken('先说一半');
      h.onError('网络错误');
    });
    const { wrapper } = createWrapper();
    const { result } = await renderAndWait(wrapper);
    await act(async () => {
      await result.current.send('继续');
    });
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[1].content).toBe('先说一半');
  });

  it('keeps history after unmount-remount (switching pages)', async () => {
    captureHandlers((h) => {
      h.onDone({ tool_results: [], applied_plan: null });
    });
    const { wrapper } = createWrapper();
    const first = await renderAndWait(wrapper);
    await act(async () => {
      await first.result.current.send('把卧推换掉');
    });
    expect(first.result.current.messages).toHaveLength(2);
    first.unmount();

    // 同一 QueryClient 下重新挂载：模拟切走再返回（缓存命中，不再拉取历史）
    const second = renderHook(() => useChatStream(PLAN), { wrapper });
    expect(second.result.current.messages).toHaveLength(2);
    expect(second.result.current.messages[0]).toMatchObject({
      role: 'user',
      content: '把卧推换掉',
    });
    expect(second.result.current.streaming).toBe(false);
  });
});
