import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { streamChat } from '../api/chat';
import type { ChatDone, ChatMessage, ToolResult } from '../api/chat';
import type { Plan } from '../types/plan';

/** 会话历史缓存键：组件卸载重挂载（切换页面）后从此恢复；登出时统一 clear。 */
export const CHAT_MESSAGES_KEY = ['chatMessages'] as const;
/** 待确认的替代动作候选：与历史同样保留，切走再返回仍可应用。 */
export const CHAT_PENDING_KEY = ['chatPending'] as const;

export function useChatStream(plan: Plan) {
  const queryClient = useQueryClient();
  const planRef = useRef(plan);
  useEffect(() => {
    planRef.current = plan;
  }, [plan]);

  // 初始值从 React Query 缓存恢复：页面切换导致的卸载重挂载不再清空历史
  const [messages, setMessagesState] = useState<ChatMessage[]>(
    () => queryClient.getQueryData<ChatMessage[]>(CHAT_MESSAGES_KEY) ?? [],
  );
  const [streaming, setStreaming] = useState(false);
  const [pending, setPendingState] = useState<ToolResult | null>(
    () => queryClient.getQueryData<ToolResult>(CHAT_PENDING_KEY) ?? null,
  );
  const [error, setError] = useState<string | null>(null);

  // 同时写 state 与缓存，保证卸载后下一次挂载能读到最新值
  const setMessages = useCallback(
    (updater: (m: ChatMessage[]) => ChatMessage[]) => {
      setMessagesState((m) => {
        const next = updater(m);
        queryClient.setQueryData(CHAT_MESSAGES_KEY, next);
        return next;
      });
    },
    [queryClient],
  );

  const setPending = useCallback(
    (next: ToolResult | null) => {
      setPendingState(next);
      queryClient.setQueryData(CHAT_PENDING_KEY, next);
    },
    [queryClient],
  );

  const send = useCallback(
    async (text: string) => {
      const history = [...messages];
      setMessages((m) => [...m, { id: crypto.randomUUID(), role: 'user', content: text }]);
      setStreaming(true);
      setError(null);
      setPending(null);

      let acc = '';
      let failed = false;
      setMessages((m) => [...m, { id: crypto.randomUUID(), role: 'assistant', content: '' }]);

      const markError = (msg: string) => {
        failed = true;
        setError(msg);
      };

      try {
        await streamChat(planRef.current, history, text, {
          onToken: (t) => {
            acc += t;
            setMessages((m) => {
              const next = [...m];
              const last = next[next.length - 1];
              next[next.length - 1] = { ...last, content: acc };
              return next;
            });
          },
          onDone: (done: ChatDone) => {
            const latest = [...done.tool_results].reverse().find((r) => r.alternatives?.length);
            if (latest) setPending(latest);
          },
          onError: markError,
        });
      } catch (err) {
        markError(err instanceof Error ? err.message : String(err));
      } finally {
        if (failed && acc === '') {
          // 一个 token 都没收到：撤掉占位空气泡，只保留用户消息
          setMessages((m) => {
            const last = m[m.length - 1];
            return last?.role === 'assistant' && last.content === '' ? m.slice(0, -1) : m;
          });
        }
        setStreaming(false);
      }
    },
    [messages, setMessages, setPending],
  );

  return { messages, streaming, pending, error, send };
}
