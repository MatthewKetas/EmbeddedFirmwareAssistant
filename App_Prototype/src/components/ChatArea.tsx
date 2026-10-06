import React, { useState } from 'react';
import {
  Copy,
  Check,
  RotateCcw,
  ThumbsUp,
  ThumbsDown,
  Code2,
  FileText,
  Sliders,
  Sparkles
} from 'lucide-react';
import { ChatMessage, CitedDoc } from '../types/hardware';

interface ChatAreaProps {
  messages: ChatMessage[];
  isStreaming: boolean;
  streamingContent: string;
  onOpenCitedDoc: (doc: CitedDoc) => void;
  onRegenerate: () => void;
  onInspectRegister: (regName: string) => void;
}

export const ChatArea: React.FC<ChatAreaProps> = ({
  messages,
  isStreaming,
  streamingContent,
  onOpenCitedDoc,
  onRegenerate,
  onInspectRegister
}) => {
  const [copiedSnippetIndex, setCopiedSnippetIndex] = useState<string | null>(null);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [likedMap, setLikedMap] = useState<Record<string, 'like' | 'dislike' | null>>({});

  const handleCopyCode = (code: string, id: string) => {
    navigator.clipboard.writeText(code);
    setCopiedSnippetIndex(id);
    setTimeout(() => setCopiedSnippetIndex(null), 2000);
  };

  const handleCopyMessage = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedMessageId(id);
    setTimeout(() => setCopiedMessageId(null), 2000);
  };

  const toggleReaction = (id: string, type: 'like' | 'dislike') => {
    setLikedMap(prev => ({
      ...prev,
      [id]: prev[id] === type ? null : type
    }));
  };

  // Helper to colorize C code lines with syntax highlighting
  const renderCodeWithSyntax = (code: string) => {
    return code.split('\n').map((line, idx) => {
      // Comments
      if (line.trim().startsWith('//') || line.trim().startsWith('/*')) {
        return (
          <div key={idx} className="text-slate-500 italic">
            {line}
          </div>
        );
      }

      // Preprocessor #define
      if (line.trim().startsWith('#define')) {
        const parts = line.split(' ');
        const def = parts[0];
        const name = parts[1];
        const rest = parts.slice(2).join(' ');
        return (
          <div key={idx}>
            <span className="text-amber-400 font-semibold">{def} </span>
            <span className="text-cyan-300">{name} </span>
            <span className="text-emerald-300">{rest}</span>
          </div>
        );
      }

      // Keywords like while, uint32_t, void
      let formattedLine = line;
      if (line.includes('while')) {
        return (
          <div key={idx}>
            <span className="text-purple-400 font-semibold">while </span>
            <span className="text-slate-200">{line.replace('while', '').trim()}</span>
          </div>
        );
      }

      // Normal code lines: highlight registers and bit shifts
      return (
        <div key={idx} className="text-slate-200">
          {line.split(/(RCC->[A-Za-z0-9_]+|LTDC->[A-Za-z0-9_]+|RCC_[A-Za-z0-9_]+|LTDC_[A-Za-z0-9_]+|0x[0-9A-Fa-f]+|<<|\||&|\b(?:uint32_t|int|void)\b)/g).map((token, tokenIdx) => {
            if (/^(RCC->[A-Za-z0-9_]+|LTDC->[A-Za-z0-9_]+)/.test(token)) {
              return (
                <button
                  key={tokenIdx}
                  onClick={() => onInspectRegister(token.replace('->', '_'))}
                  className="text-cyan-300 hover:underline hover:text-cyan-200 transition-colors"
                  title="Inspect in SVD Register Tool"
                >
                  {token}
                </button>
              );
            }
            if (/^(RCC_[A-Za-z0-9_]+|LTDC_[A-Za-z0-9_]+)/.test(token)) {
              return <span key={tokenIdx} className="text-sky-300">{token}</span>;
            }
            if (/^0x[0-9A-Fa-f]+/.test(token)) {
              return <span key={tokenIdx} className="text-emerald-400">{token}</span>;
            }
            if (token === '<<' || token === '|' || token === '&') {
              return <span key={tokenIdx} className="text-amber-400/90 font-bold mx-0.5">{token}</span>;
            }
            if (token === 'uint32_t' || token === 'int' || token === 'void') {
              return <span key={tokenIdx} className="text-purple-400">{token}</span>;
            }
            return <span key={tokenIdx}>{token}</span>;
          })}
        </div>
      );
    });
  };

  return (
    <div className="flex-1 overflow-y-auto px-4 sm:px-6 md:px-12 lg:px-24 py-8 space-y-8 select-text">
      {messages.map((message) => {
        if (message.sender === 'user') {
          return (
            <div key={message.id} className="flex justify-end">
              <div className="max-w-3xl space-y-1.5">
                <div className="bg-[#141b25] border border-white/[0.08] text-slate-100 px-5 py-4 rounded-2xl shadow-lg leading-relaxed text-[15px]">
                  {/* Highlight keywords in user prompt */}
                  {message.content.split(/(`[^`]+`)/g).map((part, i) => {
                    if (part.startsWith('`') && part.endsWith('`')) {
                      return (
                        <code
                          key={i}
                          className="px-1.5 py-0.5 mx-0.5 rounded font-mono text-[13px] bg-cyan-950/70 text-cyan-300 border border-cyan-500/30"
                        >
                          {part.slice(1, -1)}
                        </code>
                      );
                    }
                    return part;
                  })}
                </div>
                <div className="text-right text-[11px] font-mono text-slate-500 pr-2">
                  {message.timestamp}
                </div>
              </div>
            </div>
          );
        }

        // Assistant Message
        return (
          <div key={message.id} className="max-w-4xl space-y-4">
            {/* Cited Documents Badges (Exact match to screenshot top citations) */}
            {message.citations && message.citations.length > 0 && (
              <div className="flex flex-wrap items-center gap-2 pt-1">
                {message.citations.map((cite) => {
                  const isErrata = cite.type === 'errata';
                  const isDs = cite.type === 'datasheet';

                  let badgeStyle = "bg-cyan-950/40 text-cyan-300 border-cyan-500/30 hover:bg-cyan-900/40";
                  if (isErrata) {
                    badgeStyle = "bg-amber-950/40 text-amber-300 border-amber-500/30 hover:bg-amber-900/40";
                  } else if (isDs) {
                    badgeStyle = "bg-emerald-950/40 text-emerald-300 border-emerald-500/30 hover:bg-emerald-900/40";
                  }

                  return (
                    <button
                      key={cite.id}
                      onClick={() => onOpenCitedDoc(cite)}
                      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-mono border transition-all cursor-pointer ${badgeStyle}`}
                      title="Click to view verified datasheet section"
                    >
                      <FileText className="w-3.5 h-3.5 opacity-80" />
                      <span>{cite.docCode}</span>
                    </button>
                  );
                })}
              </div>
            )}

            {/* Assistant Text Explanation */}
            <div className="text-slate-200 text-[15px] leading-relaxed">
              {message.content.split(/(LTDC|PLL3R|RCC_D1CCIPR|DS12110 p\. 118|RM0433)/g).map((tok, i) => {
                if (['LTDC', 'PLL3R', 'RCC_D1CCIPR', 'DS12110 p. 118', 'RM0433'].includes(tok)) {
                  return (
                    <code
                      key={i}
                      className="px-1.5 py-0.5 rounded text-[13px] font-mono bg-white/[0.06] text-cyan-300 border border-white/[0.08]"
                    >
                      {tok}
                    </code>
                  );
                }
                return tok;
              })}
            </div>

            {/* Code Snippets Block (Exact match of stm32h7_ltdc_init.c) */}
            {message.codeSnippets &&
              message.codeSnippets.map((snippet, sIdx) => {
                const isCopied = copiedSnippetIndex === `${message.id}-${sIdx}`;
                return (
                  <div
                    key={sIdx}
                    className="rounded-xl border border-white/[0.08] bg-[#0c1017] overflow-hidden my-3 shadow-xl"
                  >
                    {/* Code Header Bar */}
                    <div className="flex items-center justify-between px-4 py-2.5 bg-[#10151f] border-b border-white/[0.06]">
                      <div className="flex items-center gap-2 text-xs font-mono text-slate-300">
                        <Code2 className="w-4 h-4 text-cyan-400" />
                        <span className="font-semibold text-slate-200">{snippet.filename}</span>
                      </div>

                      <button
                        onClick={() => handleCopyCode(snippet.code, `${message.id}-${sIdx}`)}
                        className="flex items-center gap-1 px-2.5 py-1 text-xs font-mono rounded bg-white/[0.05] hover:bg-white/[0.1] text-slate-300 hover:text-white transition-colors"
                      >
                        {isCopied ? (
                          <>
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                            <span className="text-emerald-400">Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy className="w-3.5 h-3.5" />
                            <span>Copy</span>
                          </>
                        )}
                      </button>
                    </div>

                    {/* Code Content */}
                    <div className="p-4 font-mono text-[13px] leading-relaxed overflow-x-auto">
                      {renderCodeWithSyntax(snippet.code)}
                    </div>
                  </div>
                );
              })}

            {/* Register Breakdown / Details List */}
            {message.registerBreakdown && message.registerBreakdown.length > 0 && (
              <div className="space-y-2 pt-1 font-mono text-xs text-slate-300">
                {message.registerBreakdown.map((item, rbIdx) => (
                  <div key={rbIdx} className="flex items-start gap-2.5">
                    <span className="text-cyan-400 font-bold shrink-0 mt-0.5">•</span>
                    <div>
                      <button
                        onClick={() => onInspectRegister(item.register)}
                        className="font-bold text-cyan-300 hover:underline hover:text-cyan-200 transition-colors mr-1.5"
                      >
                        {item.register}:
                      </button>
                      <span className="text-slate-300">{item.description}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Bottom Actions Row: Copy, Regenerate, Thumbs, SVD Tool Link */}
            <div className="flex items-center gap-2 pt-2 text-xs text-slate-400 font-mono">
              <button
                onClick={() => handleCopyMessage(message.content, message.id)}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded hover:bg-white/[0.06] hover:text-slate-200 transition-colors"
              >
                {copiedMessageId === message.id ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-emerald-400">Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy</span>
                  </>
                )}
              </button>

              <button
                onClick={onRegenerate}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded hover:bg-white/[0.06] hover:text-slate-200 transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Regenerate</span>
              </button>

              <button
                onClick={() => toggleReaction(message.id, 'like')}
                className={`p-1.5 rounded hover:bg-white/[0.06] transition-colors ${
                  likedMap[message.id] === 'like' ? 'text-emerald-400' : 'hover:text-slate-200'
                }`}
                title="Helpful"
              >
                <ThumbsUp className="w-3.5 h-3.5" />
              </button>

              <button
                onClick={() => toggleReaction(message.id, 'dislike')}
                className={`p-1.5 rounded hover:bg-white/[0.06] transition-colors ${
                  likedMap[message.id] === 'dislike' ? 'text-red-400' : 'hover:text-slate-200'
                }`}
                title="Report inaccuracy"
              >
                <ThumbsDown className="w-3.5 h-3.5" />
              </button>

              <div className="h-3 w-px bg-white/10 mx-1" />

              <button
                onClick={() => onInspectRegister('LTDC_SSCR')}
                className="flex items-center gap-1.5 text-slate-500 hover:text-cyan-400 transition-colors"
              >
                <Sliders className="w-3.5 h-3.5" />
                <span>Bitfield Inspector</span>
              </button>
            </div>
          </div>
        );
      })}

      {/* Streaming response preview */}
      {isStreaming && (
        <div className="max-w-4xl space-y-4">
          <div className="flex items-center gap-2 text-xs font-mono text-cyan-400 animate-pulse">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Hardware Copilot is synthesizing register timings...</span>
          </div>
          <div className="text-slate-200 text-[15px] leading-relaxed bg-[#0c1017]/80 p-4 rounded-xl border border-cyan-500/20 font-mono">
            {streamingContent}
            <span className="inline-block w-2 h-4 ml-1 bg-cyan-400 animate-pulse align-middle" />
          </div>
        </div>
      )}
    </div>
  );
};
