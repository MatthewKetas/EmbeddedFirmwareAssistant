import React, { useState } from 'react';
import {
  X,
  Terminal,
  Server,
  Play,
  Copy,
  Check,
  Download,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  Code2
} from 'lucide-react';
import { pythonBridge } from '../services/pythonBackendBridge';
import { PythonBackendStatus } from '../types/hardware';

interface PythonBackendModalProps {
  isOpen: boolean;
  onClose: () => void;
  status: PythonBackendStatus;
  onRefreshStatus: () => void;
}

export const PythonBackendModal: React.FC<PythonBackendModalProps> = ({
  isOpen,
  onClose,
  status,
  onRefreshStatus
}) => {
  const [activeTab, setActiveTab] = useState<'status' | 'backend' | 'desktop' | 'requirements'>('status');
  const [urlInput, setUrlInput] = useState(status.url);
  const [isPinging, setIsPinging] = useState(false);
  const [copiedCode, setCopiedCode] = useState(false);
  const [pingResult, setPingResult] = useState<{ success: boolean; msg: string } | null>(null);

  if (!isOpen) return null;

  const backendCode = pythonBridge.getPythonServerTemplate();
  const desktopCode = pythonBridge.getPythonDesktopTemplate();
  const requirementsTxt = pythonBridge.getRequirementsTxt();

  const handleTestConnection = async () => {
    setIsPinging(true);
    setPingResult(null);
    pythonBridge.setBackendUrl(urlInput);
    const ok = await pythonBridge.checkHealth();
    setIsPinging(false);
    onRefreshStatus();
    if (ok) {
      setPingResult({ success: true, msg: `Successfully connected to live Python backend at ${urlInput} (latency: ${pythonBridge.getStatus().latencyMs}ms)` });
    } else {
      setPingResult({ success: false, msg: `No server detected on ${urlInput}. Using high-precision embedded simulator mode.` });
    }
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedCode(true);
    setTimeout(() => setCopiedCode(false), 2000);
  };

  const handleDownloadFile = (filename: string, content: string) => {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-4 animate-in fade-in duration-200">
      <div className="w-full max-w-4xl max-h-[88vh] bg-[#0c1017] border border-white/[0.1] rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.08] bg-[#10151f]">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-emerald-950/60 border border-emerald-500/30 text-emerald-400">
              <Terminal className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-slate-100 font-mono flex items-center gap-2">
                Python Desktop & Backend Wire-Up
                <span className="text-[11px] font-normal px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-500/20">
                  Ready to Wire
                </span>
              </h2>
              <p className="text-xs text-slate-400 font-mono">
                Wire this frontend to your native Python application or PyWebView desktop bundle
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-white/[0.08] rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center gap-1 px-6 pt-3 border-b border-white/[0.06] bg-[#0c1017] text-xs font-mono">
          <button
            onClick={() => setActiveTab('status')}
            className={`px-3 py-2 border-b-2 font-medium transition-all ${
              activeTab === 'status'
                ? 'border-cyan-400 text-cyan-300'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            Connection & Endpoints
          </button>
          <button
            onClick={() => setActiveTab('backend')}
            className={`px-3 py-2 border-b-2 font-medium transition-all ${
              activeTab === 'backend'
                ? 'border-cyan-400 text-cyan-300'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            backend.py (FastAPI)
          </button>
          <button
            onClick={() => setActiveTab('desktop')}
            className={`px-3 py-2 border-b-2 font-medium transition-all ${
              activeTab === 'desktop'
                ? 'border-cyan-400 text-cyan-300'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            desktop_main.py (PyWebView)
          </button>
          <button
            onClick={() => setActiveTab('requirements')}
            className={`px-3 py-2 border-b-2 font-medium transition-all ${
              activeTab === 'requirements'
                ? 'border-cyan-400 text-cyan-300'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            requirements.txt
          </button>
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto p-6 font-mono text-xs">
          {activeTab === 'status' && (
            <div className="space-y-6">
              {/* Connection Status Card */}
              <div className="p-4 rounded-xl bg-[#131923] border border-white/[0.08] space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span
                      className={`w-3 h-3 rounded-full shrink-0 ${
                        status.connected ? 'bg-emerald-400 shadow-[0_0_8px_#34d399]' : 'bg-amber-400'
                      }`}
                    />
                    <div>
                      <div className="font-semibold text-slate-100 text-sm">
                        {status.connected ? 'Live Python Server Connected' : 'Simulated Desktop Bridge Active'}
                      </div>
                      <div className="text-slate-400 text-[11px]">
                        Mode: <span className="text-cyan-300">{status.mode}</span> · Latency: {status.latencyMs}ms · Version: {status.version}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        const newMode = status.mode === 'live' ? 'simulated' : 'live';
                        pythonBridge.setMode(newMode);
                        onRefreshStatus();
                      }}
                      className="px-3 py-1.5 rounded-lg bg-white/[0.06] hover:bg-white/[0.1] text-slate-300 transition-colors"
                    >
                      Toggle Mode ({status.mode})
                    </button>
                  </div>
                </div>

                {/* Target URL input & Ping */}
                <div className="flex flex-col sm:flex-row gap-2 pt-2 border-t border-white/[0.05]">
                  <input
                    type="text"
                    value={urlInput}
                    onChange={(e) => setUrlInput(e.target.value)}
                    placeholder="http://127.0.0.1:8000"
                    className="flex-1 bg-black/40 border border-white/[0.1] rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                  />
                  <button
                    onClick={handleTestConnection}
                    disabled={isPinging}
                    className="px-4 py-2 rounded-lg bg-cyan-950/80 text-cyan-300 hover:bg-cyan-900 border border-cyan-500/40 flex items-center justify-center gap-2 shrink-0 transition-colors"
                  >
                    <Play className="w-3.5 h-3.5" />
                    <span>{isPinging ? 'Pinging...' : 'Test Connection'}</span>
                  </button>
                </div>

                {pingResult && (
                  <div
                    className={`p-3 rounded-lg border flex items-center gap-2 text-[11px] ${
                      pingResult.success
                        ? 'bg-emerald-950/40 text-emerald-300 border-emerald-500/30'
                        : 'bg-amber-950/40 text-amber-300 border-amber-500/30'
                    }`}
                  >
                    {pingResult.success ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                    ) : (
                      <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
                    )}
                    <span>{pingResult.msg}</span>
                  </div>
                )}
              </div>

              {/* Endpoints Contract Table */}
              <div className="space-y-3">
                <h3 className="font-semibold text-slate-300 uppercase tracking-wider text-[11px]">
                  Wire-Up REST & Streaming Contracts
                </h3>
                <div className="overflow-x-auto rounded-xl border border-white/[0.08] bg-[#111721]">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-white/[0.06] text-slate-500 bg-black/20">
                        <th className="py-2.5 px-4 font-semibold">Method</th>
                        <th className="py-2.5 px-4 font-semibold">Endpoint</th>
                        <th className="py-2.5 px-4 font-semibold">Payload / Function</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.04] text-slate-300 font-mono">
                      <tr>
                        <td className="py-2.5 px-4 text-emerald-400 font-bold">GET</td>
                        <td className="py-2.5 px-4 text-cyan-300">/api/health</td>
                        <td className="py-2.5 px-4 text-slate-400">Heartbeat check, active Ollama model, and bridge version</td>
                      </tr>
                      <tr>
                        <td className="py-2.5 px-4 text-purple-400 font-bold">POST</td>
                        <td className="py-2.5 px-4 text-cyan-300">/api/chat</td>
                        <td className="py-2.5 px-4 text-slate-400">&#123; prompt, mcu, model, history &#125; → Token streaming response</td>
                      </tr>
                      <tr>
                        <td className="py-2.5 px-4 text-purple-400 font-bold">POST</td>
                        <td className="py-2.5 px-4 text-cyan-300">/api/index-svd</td>
                        <td className="py-2.5 px-4 text-slate-400">Multipart upload of ARM SVD XML file → Parsed register json</td>
                      </tr>
                      <tr>
                        <td className="py-2.5 px-4 text-purple-400 font-bold">POST</td>
                        <td className="py-2.5 px-4 text-cyan-300">/api/registers/calculate</td>
                        <td className="py-2.5 px-4 text-slate-400">&#123; register, fields &#125; → Calculates hex mask, binary and bit shifts</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Instructions */}
              <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] text-slate-400 space-y-2 text-[11px] leading-relaxed">
                <div className="text-slate-200 font-semibold">How to run as a full desktop application:</div>
                <ol className="list-decimal list-inside space-y-1">
                  <li>Download or copy the files from the tabs above (<code className="text-cyan-300">backend.py</code>, <code className="text-cyan-300">desktop_main.py</code>, <code className="text-cyan-300">requirements.txt</code>).</li>
                  <li>Install dependencies with <code className="text-cyan-300">pip install -r requirements.txt</code>.</li>
                  <li>Start Ollama locally with <code className="text-cyan-300">ollama run qwen2.5-coder:32b</code>.</li>
                  <li>Run <code className="text-cyan-300">python desktop_main.py</code> to launch the complete native desktop application!</li>
                </ol>
              </div>
            </div>
          )}

          {activeTab === 'backend' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">FastAPI Server with Ollama SSE & SVD Parser</span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleCopy(backendCode)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] text-slate-200 transition-colors"
                  >
                    {copiedCode ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copiedCode ? 'Copied' : 'Copy Code'}</span>
                  </button>
                  <button
                    onClick={() => handleDownloadFile('backend.py', backendCode)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-950 text-cyan-300 hover:bg-cyan-900 border border-cyan-500/40 transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download backend.py</span>
                  </button>
                </div>
              </div>
              <pre className="p-4 rounded-xl bg-black/60 border border-white/[0.06] text-slate-200 overflow-x-auto text-xs leading-relaxed max-h-[500px]">
                {backendCode}
              </pre>
            </div>
          )}

          {activeTab === 'desktop' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">PyWebView Native Desktop Window Launcher</span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleCopy(desktopCode)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] text-slate-200 transition-colors"
                  >
                    {copiedCode ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copiedCode ? 'Copied' : 'Copy Code'}</span>
                  </button>
                  <button
                    onClick={() => handleDownloadFile('desktop_main.py', desktopCode)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-950 text-cyan-300 hover:bg-cyan-900 border border-cyan-500/40 transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download desktop_main.py</span>
                  </button>
                </div>
              </div>
              <pre className="p-4 rounded-xl bg-black/60 border border-white/[0.06] text-slate-200 overflow-x-auto text-xs leading-relaxed max-h-[500px]">
                {desktopCode}
              </pre>
            </div>
          )}

          {activeTab === 'requirements' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Python Dependencies</span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleCopy(requirementsTxt)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] text-slate-200 transition-colors"
                  >
                    {copiedCode ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copiedCode ? 'Copied' : 'Copy Code'}</span>
                  </button>
                  <button
                    onClick={() => handleDownloadFile('requirements.txt', requirementsTxt)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-950 text-cyan-300 hover:bg-cyan-900 border border-cyan-500/40 transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download requirements.txt</span>
                  </button>
                </div>
              </div>
              <pre className="p-4 rounded-xl bg-black/60 border border-white/[0.06] text-slate-200 overflow-x-auto text-xs leading-relaxed">
                {requirementsTxt}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
