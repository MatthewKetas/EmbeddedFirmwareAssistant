import React, { useState, useRef, useEffect } from 'react';
import {
  Plus,
  Globe,
  ArrowUp,
  ChevronDown,
  Paperclip,
  X,
  FileCode
} from 'lucide-react';
import { ModelConfig } from '../types/hardware';

interface MessageInputProps {
  onSendMessage: (text: string, attachments: string[]) => void;
  disabled?: boolean;
  models: ModelConfig[];
  selectedModel: string;
  onSelectModel: (modelId: string) => void;
  onOpenFileAttachment: () => void;
}

export const MessageInput: React.FC<MessageInputProps> = ({
  onSendMessage,
  disabled = false,
  models,
  selectedModel,
  onSelectModel,
  onOpenFileAttachment
}) => {
  const [input, setInput] = useState('');
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [ragGroundingEnabled, setRagGroundingEnabled] = useState(true);
  const [attachedFiles, setAttachedFiles] = useState<string[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setModelDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    if ((input.trim() || attachedFiles.length > 0) && !disabled) {
      onSendMessage(input.trim(), attachedFiles);
      setInput('');
      setAttachedFiles([]);
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    // Auto-adjust height
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
  };

  const removeAttachment = (index: number) => {
    setAttachedFiles(prev => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="p-4 sm:px-8 md:px-16 lg:px-24 bg-gradient-to-t from-[#0b0f14] via-[#0b0f14] to-transparent shrink-0">
      <div className="max-w-4xl mx-auto">
        {/* Input Card Container */}
        <div className="relative rounded-2xl bg-[#141b25] border border-white/[0.1] shadow-2xl focus-within:border-cyan-500/50 transition-all">
          
          {/* Attached files chips */}
          {attachedFiles.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 px-4 pt-3">
              {attachedFiles.map((file, i) => (
                <div
                  key={i}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono bg-cyan-950/60 text-cyan-300 border border-cyan-500/30"
                >
                  <FileCode className="w-3.5 h-3.5" />
                  <span className="truncate max-w-[140px]">{file}</span>
                  <button
                    onClick={() => removeAttachment(i)}
                    className="hover:text-cyan-100 p-0.5"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder="Send a message or ask about register timings, SVD masks, errata..."
            className="w-full bg-transparent text-slate-100 placeholder-slate-500 px-4 pt-3.5 pb-2 text-sm focus:outline-none resize-none min-h-[46px] max-h-40 leading-relaxed font-sans"
          />

          {/* Bottom Toolbar inside input container */}
          <div className="flex items-center justify-between px-3 pb-2.5 pt-1 text-slate-400">
            {/* Left buttons: attach (+) and globe/datasheet search */}
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => {
                  onOpenFileAttachment();
                  // simulate attaching a sample SVD / C header if clicked directly
                  setAttachedFiles(prev => [...prev, 'STM32H743.svd']);
                }}
                className="p-1.5 rounded-lg hover:bg-white/[0.08] hover:text-slate-200 transition-colors"
                title="Attach SVD, C header, or datasheet file"
              >
                <Plus className="w-4 h-4" />
              </button>

              <button
                type="button"
                onClick={() => setRagGroundingEnabled(!ragGroundingEnabled)}
                className={`p-1.5 rounded-lg transition-colors flex items-center gap-1 ${
                  ragGroundingEnabled
                    ? 'text-cyan-400 bg-cyan-950/40 hover:bg-cyan-900/50'
                    : 'text-slate-500 hover:bg-white/[0.08] hover:text-slate-300'
                }`}
                title={ragGroundingEnabled ? "Datasheet RAG Grounding Enabled" : "Enable Datasheet Grounding"}
              >
                <Globe className="w-4 h-4" />
              </button>
            </div>

            {/* Right buttons: Model Selector & Send Arrow */}
            <div className="flex items-center gap-2">
              {/* Model Dropdown */}
              <div className="relative" ref={dropdownRef}>
                <button
                  type="button"
                  onClick={() => setModelDropdownOpen(!modelDropdownOpen)}
                  className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-mono rounded-lg hover:bg-white/[0.08] text-slate-300 transition-colors border border-transparent hover:border-white/[0.06]"
                >
                  <span className="text-slate-300 truncate max-w-[150px]">{selectedModel}</span>
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                </button>

                {/* Dropdown Menu */}
                {modelDropdownOpen && (
                  <div className="absolute right-0 bottom-full mb-2 w-64 rounded-xl bg-[#121822] border border-white/[0.1] shadow-2xl py-1 z-30 font-mono text-xs">
                    <div className="px-3 py-1.5 text-[10px] uppercase text-slate-500 font-semibold border-b border-white/[0.05]">
                      Select Inference Model
                    </div>
                    {models.map((m) => (
                      <button
                        key={m.id}
                        type="button"
                        onClick={() => {
                          onSelectModel(m.id);
                          setModelDropdownOpen(false);
                        }}
                        className={`w-full flex items-center justify-between px-3 py-2 text-left hover:bg-white/[0.06] transition-colors ${
                          m.id === selectedModel
                            ? 'text-cyan-300 font-medium bg-cyan-950/40'
                            : 'text-slate-300'
                        }`}
                      >
                        <div className="min-w-0">
                          <div className="truncate">{m.name}</div>
                          <div className="text-[10px] text-slate-500">
                            {m.provider} · {m.contextLength}
                          </div>
                        </div>
                        {m.isLocal && (
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-500/20">
                            local
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Upward Send Button (Exact styling from screenshot) */}
              <button
                type="button"
                onClick={handleSubmit}
                disabled={(!input.trim() && attachedFiles.length === 0) || disabled}
                className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
                  input.trim() || attachedFiles.length > 0
                    ? 'bg-white text-slate-950 hover:bg-slate-200 active:scale-95 shadow-md cursor-pointer'
                    : 'bg-white/10 text-slate-500 cursor-not-allowed'
                }`}
                title="Send message (Enter)"
              >
                <ArrowUp className="w-4 h-4 stroke-[2.5]" />
              </button>
            </div>
          </div>
        </div>

        {/* Small bottom footer note */}
        <div className="flex items-center justify-between px-2 pt-2 text-[11px] font-mono text-slate-500">
          <span>Datasheet RAG Grounded: RM0433 Rev 7, DS12110, ES0392</span>
          <span>Press Enter to send, Shift+Enter for newline</span>
        </div>
      </div>
    </div>
  );
};
