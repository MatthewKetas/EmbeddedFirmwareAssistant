import { useEffect, useRef } from 'react';
import { Cpu } from 'lucide-react';
import type { ChatMessage } from '../types/hardware';

interface ChatAreaProps {
  messages: ChatMessage[];
  streamingText?: string;
  error?: string;
}

export function ChatArea({ messages, streamingText, error }: ChatAreaProps) {
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = scroller.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages, streamingText, error]);

  return (
    <div ref={scroller} className="flex-1 overflow-y-auto px-4 py-8 sm:px-10">
      <div className="mx-auto max-w-4xl space-y-6">
        {!messages.length && (
          <div className="mt-20 text-center">
            <Cpu className="mx-auto mb-4 size-8 text-cyan-400" />
            <h1 className="mb-2 text-xl font-semibold">Hardware Copilot</h1>
            <p className="text-sm text-slate-400">Ask a firmware question about this project’s board.</p>
          </div>
        )}
        {messages.map(message => (
          <div key={message.id} className={`flex ${message.sender === 'user' ? 'justify-end' : ''}`}>
            <div className={`min-w-0 rounded-2xl border border-white/[0.08] px-4 py-3 ${
              message.sender === 'user' ? 'max-w-[85%] bg-[#141b25]' : 'w-full bg-[#10161f]'
            }`}>
              <div className="mb-1 font-mono text-[11px] text-slate-400">
                {message.sender === 'user' ? 'You' : 'Hardware Copilot'} · {message.timestamp}
              </div>
              <div className="whitespace-pre-wrap wrap-anywhere text-sm leading-relaxed">{message.content}</div>
            </div>
          </div>
        ))}
        {streamingText !== undefined && (
          <div className="rounded-2xl border border-white/[0.08] bg-[#10161f] px-4 py-3">
            <div className="mb-1 font-mono text-[11px] text-cyan-400">Hardware Copilot</div>
            <div className="whitespace-pre-wrap wrap-anywhere text-sm leading-relaxed">{streamingText || 'Waiting for the local model…'}</div>
          </div>
        )}
        {error && <p role="alert" className="rounded-lg bg-amber-950/30 p-3 text-sm text-amber-300">{error}</p>}
      </div>
    </div>
  );
}
