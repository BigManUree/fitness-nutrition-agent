import { fetchEventSource } from '@microsoft/fetch-event-source';
import { notifyUnauthorized } from './client';
import type { Plan } from '../types/plan';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

export interface ToolResult {
  original_exercise: string;
  alternatives: { name: string; [k: string]: unknown }[];
  total: number;
  source: string;
  note?: string;
}

export interface ChatDone {
  tool_results: ToolResult[];
  applied_plan?: Plan | null;
}

export interface ChatHistoryResponse {
  messages: { role: 'user' | 'assistant'; content: string }[];
  pending: ToolResult | null;
}

export async function getChatHistory(): Promise<ChatHistoryResponse> {
  const res = await fetch('/api/chat/history', {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    if (res.status === 401) notifyUnauthorized();
    throw new Error(`读取对话历史失败（${res.status}）`);
  }
  return res.json();
}

export interface ChatStreamHandlers {
  onToken: (text: string) => void;
  onDone: (done: ChatDone) => void;
  onError: (message: string) => void;
}

export function streamChat(
  plan: Plan,
  messages: ChatMessage[],
  message: string,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
) {
  return fetchEventSource('/api/plans/chat', {
    method: 'POST',
    signal,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan, messages, message }),
    async onopen(response) {
      if (!response.ok) {
        if (response.status === 401) notifyUnauthorized();
        let detail = '';
        try {
          detail = JSON.stringify(await response.json());
        } catch {
          /* ignore */
        }
        handlers.onError(detail || `请求失败（${response.status}）`);
        throw new Error(detail || 'chat request failed');
      }
    },
    onmessage(msg) {
      if (msg.event === 'token') {
        // 后端 token 事件 data 为 JSON 编码的字符串（见 _sse_event），需反解
        try {
          handlers.onToken(JSON.parse(msg.data));
        } catch {
          handlers.onToken(msg.data);
        }
      } else if (msg.event === 'done') {
        let done: ChatDone = { tool_results: [] };
        try {
          done = JSON.parse(msg.data);
        } catch {
          /* ignore */
        }
        handlers.onDone(done);
      } else if (msg.event === 'error') {
        let message = msg.data;
        try {
          message = JSON.parse(msg.data).message ?? msg.data;
        } catch {
          /* ignore */
        }
        handlers.onError(message);
      }
    },
    onerror(err) {
      handlers.onError(err instanceof Error ? err.message : String(err));
      throw err; // 抛出让 fetch-event-source 停止重连
    },
  });
}
