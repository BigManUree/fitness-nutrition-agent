import { useCallback, useRef, useState } from 'react';
import { streamChat } from '../api/chat';
import type { ChatDone, ChatMessage, ToolResult } from '../api/chat';
import type { Plan } from '../types/plan';

export function useChatStream(plan: Plan) {
  const planRef = useRef(plan);
  planRef.current = plan;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [pending, setPending] = useState<ToolResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const send = useCallback(
    async (text: string) => {
      const history = [...messages];
      setMessages((m) => [...m, { role: 'user', content: text }]);
      setStreaming(true);
      setError(null);
      setPending(null);

      let acc = '';
      setMessages((m) => [...m, { role: 'assistant', content: '' }]);

      try {
        await streamChat(planRef.current, history, text, {
          onToken: (t) => {
            acc += t;
            setMessages((m) => {
              const next = [...m];
              next[next.length - 1] = { role: 'assistant', content: acc };
              return next;
            });
          },
          onDone: (done: ChatDone) => {
            const latest = [...done.tool_results].reverse().find((r) => r.alternatives?.length);
            if (latest) setPending(latest);
          },
          onError: (msg) => setError(msg),
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setStreaming(false);
      }
    },
    [messages],
  );

  return { messages, streaming, pending, error, send };
}
