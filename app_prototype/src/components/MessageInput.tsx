import { useState } from 'react';
import { ArrowUp } from 'lucide-react';

interface MessageInputProps {
  onSendMessage: (text: string) => void;
  disabled: boolean;
}

export function MessageInput({ onSendMessage, disabled }: MessageInputProps) {
  const [input, setInput] = useState('');

  function submit() {
    if (disabled || !input.trim()) return;
    onSendMessage(input.trim());
    setInput('');
  }

  return (
    <form className="shrink-0 px-4 pb-4 sm:px-10" onSubmit={event => {
      event.preventDefault();
      submit();
    }}>
      <div className="mx-auto max-w-4xl">
        <div className="flex items-end gap-2 rounded-2xl border border-white/10 bg-[#141b25] p-3 shadow-2xl focus-within:border-cyan-500/50">
          <textarea rows={2} value={input} onChange={event => setInput(event.target.value)}
            aria-label="Message" placeholder="Ask about firmware, registers, or your board…"
            onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                submit();
              }
            }}
            className="min-w-0 flex-1 resize-y bg-transparent px-1 text-sm text-slate-100 placeholder-slate-400 focus:outline-none" />
          <button type="submit" aria-label="Send message" disabled={disabled || !input.trim()}
            className="flex size-8 shrink-0 items-center justify-center rounded-full bg-white text-slate-950 disabled:opacity-30">
            <ArrowUp className="size-4" />
          </button>
        </div>
        <p className="px-2 pt-2 font-mono text-[11px] text-slate-400">
          {disabled ? 'The local model is responding…' : 'Enter to send · Shift+Enter for a new line'}
        </p>
      </div>
    </form>
  );
}
