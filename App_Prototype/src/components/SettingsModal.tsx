import React, { useState } from 'react';
import { X, Settings, Cpu, HardDrive, Check } from 'lucide-react';
import { ModelConfig } from '../types/hardware';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  models: ModelConfig[];
  selectedModel: string;
  onSelectModel: (mId: string) => void;
  onOpenPythonBridge: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  models,
  selectedModel,
  onSelectModel,
  onOpenPythonBridge
}) => {
  const [ollamaHost, setOllamaHost] = useState('http://127.0.0.1:11434');
  const [temperature, setTemperature] = useState(0.2);
  const [systemPrompt, setSystemPrompt] = useState(
    'You are Hardware Copilot, an expert embedded firmware & silicon engineer. Ground responses in verified reference manuals, SVD bitfields, and provide copy-paste ready C driver code.'
  );
  const [saved, setSaved] = useState(false);

  if (!isOpen) return null;

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => {
      setSaved(false);
      onClose();
    }, 800);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4 animate-in fade-in duration-200">
      <div className="w-full max-w-lg bg-[#0c1017] border border-white/[0.1] rounded-2xl shadow-2xl flex flex-col overflow-hidden font-sans">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.08] bg-[#10151f]">
          <div className="flex items-center gap-2.5">
            <Settings className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-mono font-semibold text-slate-100">
              Hardware Copilot Engine Settings
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-slate-400 hover:text-slate-200 rounded transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form Body */}
        <div className="p-6 space-y-4 font-mono text-xs">
          <div>
            <label className="block text-slate-400 mb-1">Local Ollama Host</label>
            <input
              type="text"
              value={ollamaHost}
              onChange={(e) => setOllamaHost(e.target.value)}
              className="w-full bg-[#131923] border border-white/[0.1] rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
            />
          </div>

          <div>
            <label className="block text-slate-400 mb-1">Active Model</label>
            <select
              value={selectedModel}
              onChange={(e) => onSelectModel(e.target.value)}
              className="w-full bg-[#131923] border border-white/[0.1] rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
            >
              {models.map(m => (
                <option key={m.id} value={m.id}>
                  {m.name} ({m.provider} - {m.contextLength})
                </option>
              ))}
            </select>
          </div>

          <div>
            <div className="flex justify-between text-slate-400 mb-1">
              <span>Sampling Temperature: {temperature}</span>
              <span className="text-[10px] text-slate-500">Low = strict register accuracy</span>
            </div>
            <input
              type="range"
              min="0.0"
              max="1.0"
              step="0.05"
              value={temperature}
              onChange={(e) => setTemperature(parseFloat(e.target.value))}
              className="w-full accent-cyan-400"
            />
          </div>

          <div>
            <label className="block text-slate-400 mb-1">System Prompt Directive</label>
            <textarea
              rows={3}
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              className="w-full bg-[#131923] border border-white/[0.1] rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500 font-sans text-xs"
            />
          </div>

          <div className="pt-2 border-t border-white/[0.06] flex items-center justify-between">
            <button
              onClick={() => {
                onClose();
                onOpenPythonBridge();
              }}
              className="text-cyan-400 hover:underline"
            >
              Configure Python Desktop Bridge →
            </button>

            <button
              onClick={handleSave}
              className="px-4 py-2 rounded-lg bg-cyan-950 text-cyan-300 hover:bg-cyan-900 border border-cyan-500/40 flex items-center gap-1.5 transition-colors"
            >
              {saved ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : null}
              <span>{saved ? 'Saved' : 'Save Preferences'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
