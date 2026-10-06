import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useChatStream } from './useChatStream';
import { streamChat } from '../api/chat';

vi.mock('../api/chat', () => ({
  streamChat: vi.fn(),
}));

const PLAN = { weekly_plan: [] };

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function createWrapper() {
  const queryClient = makeClient();
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

describe('useChatStream', () => {
  beforeEach(() => {
    vi.mocked(streamChat).mockReset();
  });

  it('accumulates tokens into last assistant message', async () => {
    captureHandlers((h) => {
      h.onToken('你');
      h.onToken('好');
      h.onDone({ tool_results: [] });
    });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useChatStream(PLAN), { wrapper });
    await act(async () => {
      await result.current.send('你好');
    });
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[1].content).toBe('你好');
    expect(result.current.streaming).toBe(false);
  });

  it('sets pending from last tool result with alternatives', async () => {
    captureHandlers((h) => {
      h.onDone({
        tool_results: [
          {
            original_exercise: '卧推',
            alternatives: [{ name: 'Dumbbell Press' }],
            total: 1,
            source: 'mcp',
          },
        ],
      });
    });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useChatStream(PLAN), { wrapper });
    await act(async () => {
      await result.current.send('换动作');
    });
    expect(result.current.pending?.original_exercise).toBe('卧推');
  });

  it('removes the empty assistant bubble when the stream fails before any token', async () => {
    captureHandlers((h) => {
      h.onError('网络错误');
    });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useChatStream(PLAN), { wrapper });
    await act(async () => {
      await result.current.send('你好');
    });
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]).toMatchObject({ role: 'user', content: '你好' });
    expect(result.current.messages[0].id).toEqual(expect.any(String));
    expect(result.current.error).toBe('网络错误');
  });

  it('keeps partial content when the stream fails mid-way', async () => {
    captureHandlers((h) => {
      h.onToken('先说一半');
      h.onError('网络错误');
    });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useChatStream(PLAN), { wrapper });
    await act(async () => {
      await result.current.send('继续');
    });
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[1].content).toBe('先说一半');
  });

  it('keeps history and pending after unmount-remount (switching pages)', async () => {
    captureHandlers((h) => {
      h.onDone({
        tool_results: [
          {
            original_exercise: 'Bench Press',
            alternatives: [{ name: 'Dumbbell Press' }],
            total: 1,
            source: 'mcp',
          },
        ],
      });
    });
    const { wrapper } = createWrapper();
    const first = renderHook(() => useChatStream(PLAN), { wrapper });
    await act(async () => {
      await first.result.current.send('把卧推换掉');
    });
    expect(first.result.current.messages).toHaveLength(2);
    first.unmount();

    // 同一 QueryClient 下重新挂载：模拟切走再返回
    const second = renderHook(() => useChatStream(PLAN), { wrapper });
    expect(second.result.current.messages).toHaveLength(2);
    expect(second.result.current.messages[0]).toMatchObject({
      role: 'user',
      content: '把卧推换掉',
    });
    expect(second.result.current.pending?.original_exercise).toBe('Bench Press');
    expect(second.result.current.streaming).toBe(false);
  });
});
