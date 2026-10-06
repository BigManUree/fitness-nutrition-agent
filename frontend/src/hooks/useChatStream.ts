import { useCallback, useEffect, useRef, useState } from 'react';
import { streamChat } from '../api/chat';
import type { ChatDone, ChatMessage, ToolResult } from '../api/chat';
import type { Plan } from '../types/plan';

export function useChatStream(plan: Plan) {
  const planRef = useRef(plan);
  useEffect(() => {
    planRef.current = plan;
  }, [plan]);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [pending, setPending] = useState<ToolResult | null>(null);
  const [error, setError] = useState<string | null>(null);

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
    [messages],
  );

  return { messages, streaming, pending, error, send };
}
