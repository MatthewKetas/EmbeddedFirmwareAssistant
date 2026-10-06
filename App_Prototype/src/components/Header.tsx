import React from 'react';
import { BookOpen, Download, PanelLeft, Terminal, Cpu } from 'lucide-react';
import { PythonBackendStatus } from '../types/hardware';

interface HeaderProps {
  sessionTitle: string;
  targetMcu: string;
  citedDocsCount: number;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  onOpenCitedDocs: () => void;
  onOpenPythonModal: () => void;
  onExportSession: () => void;
  pythonStatus: PythonBackendStatus;
}

export const Header: React.FC<HeaderProps> = ({
  sessionTitle,
  targetMcu,
  citedDocsCount,
  sidebarOpen,
  onToggleSidebar,
  onOpenCitedDocs,
  onOpenPythonModal,
  onExportSession,
  pythonStatus
}) => {
  return (
    <header className="h-12 border-b border-white/[0.07] bg-[#0c1017] flex items-center justify-between px-4 select-none shrink-0 z-20">
      {/* Left zone: Window dots, sidebar toggle, session breadcrumb */}
      <div className="flex items-center gap-3 min-w-0">
        {/* macOS-style window controls */}
        <div className="flex items-center gap-2 mr-2">
          <button 
            title="Close" 
            aria-label="Close window"
            className="w-3 h-3 rounded-full bg-[#ff5f56] hover:brightness-110 active:brightness-90 transition-all border border-black/20" 
          />
          <button 
            title="Minimize" 
            aria-label="Minimize window"
            className="w-3 h-3 rounded-full bg-[#ffbd2e] hover:brightness-110 active:brightness-90 transition-all border border-black/20" 
          />
          <button 
            title="Maximize" 
            aria-label="Maximize window"
            className="w-3 h-3 rounded-full bg-[#27c93f] hover:brightness-110 active:brightness-90 transition-all border border-black/20" 
          />
        </div>

        {/* Sidebar toggle */}
        <button
          onClick={onToggleSidebar}
          title={sidebarOpen ? "Hide Sidebar (⌘B)" : "Show Sidebar (⌘B)"}
          className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-white/[0.06] rounded transition-colors"
        >
          <PanelLeft className="w-4 h-4" />
        </button>

        {/* Session Title & Target Chip */}
        <div className="flex items-center gap-2.5 min-w-0 overflow-hidden text-sm">
          <span className="text-slate-400 font-mono text-xs hidden sm:inline">Session:</span>
          <span className="font-medium text-slate-200 truncate font-mono text-xs sm:text-sm tracking-tight">
            {sessionTitle}
          </span>

          {/* MCU Target Pill Badge */}
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-medium tracking-wide bg-cyan-950/80 text-cyan-300 border border-cyan-500/30 shrink-0">
            <Cpu className="w-3 h-3 text-cyan-400" />
            {targetMcu}
          </span>
        </div>
      </div>

      {/* Right zone: Python Bridge, Cited Docs, Export */}
      <div className="flex items-center gap-2 shrink-0">
        {/* Python Backend Desktop Bridge Status Button */}
        <button
          onClick={onOpenPythonModal}
          title="Configure Python Backend & Desktop Runner"
          className="hidden md:flex items-center gap-2 px-2.5 py-1 text-xs font-mono rounded bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-slate-300 transition-colors"
        >
          <span className={`w-2 h-2 rounded-full ${pythonStatus.connected ? 'bg-emerald-400 shadow-[0_0_8px_#34d399]' : 'bg-amber-400 animate-pulse'}`} />
          <Terminal className="w-3.5 h-3.5 text-slate-400" />
          <span className="font-medium">Python Bridge</span>
          <span className="text-[10px] text-slate-500 hidden lg:inline">
            {pythonStatus.connected ? '8000 Live' : 'Simulated'}
          </span>
        </button>

        {/* Cited Documents trigger */}
        <button
          onClick={onOpenCitedDocs}
          className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-mono rounded bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-amber-300/90 hover:text-amber-200 transition-colors"
          title="View verified datasheet pages & errata citations"
        >
          <BookOpen className="w-3.5 h-3.5 text-amber-400" />
          <span>{citedDocsCount} Cited Docs</span>
        </button>

        {/* Export / Download Session */}
        <button
          onClick={onExportSession}
          className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-white/[0.06] rounded transition-colors"
          title="Export conversation & C code snippets"
        >
          <Download className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};
