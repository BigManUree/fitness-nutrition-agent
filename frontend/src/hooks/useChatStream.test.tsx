import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useChatStream } from './useChatStream';
import { streamChat } from '../api/chat';

vi.mock('../api/chat', () => ({
  streamChat: vi.fn(),
}));

const PLAN = { weekly_plan: [] };

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
    const { result } = renderHook(() => useChatStream(PLAN));
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
    const { result } = renderHook(() => useChatStream(PLAN));
    await act(async () => {
      await result.current.send('换动作');
    });
    expect(result.current.pending?.original_exercise).toBe('卧推');
  });

  it('removes the empty assistant bubble when the stream fails before any token', async () => {
    captureHandlers((h) => {
      h.onError('网络错误');
    });
    const { result } = renderHook(() => useChatStream(PLAN));
    await act(async () => {
      await result.current.send('你好');
    });
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]).toEqual({ role: 'user', content: '你好' });
    expect(result.current.error).toBe('网络错误');
  });

  it('keeps partial content when the stream fails mid-way', async () => {
    captureHandlers((h) => {
      h.onToken('先说一半');
      h.onError('网络错误');
    });
    const { result } = renderHook(() => useChatStream(PLAN));
    await act(async () => {
      await result.current.send('继续');
    });
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[1].content).toBe('先说一半');
  });
});
