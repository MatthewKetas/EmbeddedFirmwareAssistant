import React, { useState } from 'react';
import {
  MessageSquarePlus,
  FileCode2,
  Cpu,
  Radio,
  Binary,
  MessageSquare,
  Settings,
  ChevronDown,
  ChevronRight,
  Plus
} from 'lucide-react';
import { HardwareWorkspace } from '../types/hardware';

interface SidebarProps {
  workspaces: HardwareWorkspace[];
  activeSessionId: string;
  onSelectSession: (sessionId: string, workspaceId: string) => void;
  onNewChat: () => void;
  onOpenSvdInspector: () => void;
  onOpenSettings: () => void;
  activeModelName: string;
}

export const Sidebar: React.FC<SidebarProps> = ({
  workspaces,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onOpenSvdInspector,
  onOpenSettings,
  activeModelName,
}) => {
  // Collapsed state for workspaces (default all open)
  const [collapsedWorkspaces, setCollapsedWorkspaces] = useState<Record<string, boolean>>({});

  const toggleWorkspace = (wsId: string) => {
    setCollapsedWorkspaces(prev => ({
      ...prev,
      [wsId]: !prev[wsId]
    }));
  };

  const getWorkspaceIcon = (iconType: string) => {
    switch (iconType) {
      case 'chip':
        return <Cpu className="w-4 h-4 text-cyan-400" />;
      case 'cpu':
        return <Binary className="w-4 h-4 text-amber-400" />;
      case 'radio':
        return <Radio className="w-4 h-4 text-sky-400" />;
      case 'dsp':
        return <Cpu className="w-4 h-4 text-emerald-400" />;
      default:
        return <Cpu className="w-4 h-4 text-slate-400" />;
    }
  };

  return (
    <aside className="w-64 h-full bg-[#0a0d13] border-r border-white/[0.07] flex flex-col justify-between select-none shrink-0 z-10 text-slate-300">
      {/* Top Action Buttons */}
      <div className="p-3 space-y-1.5 border-b border-white/[0.05]">
        {/* New Chat Button */}
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-between px-3 py-2 rounded-lg bg-white/[0.05] hover:bg-white/[0.09] active:bg-white/[0.04] text-slate-200 text-sm font-medium transition-all group border border-white/[0.04]"
        >
          <div className="flex items-center gap-2.5">
            <MessageSquarePlus className="w-4 h-4 text-cyan-400 group-hover:scale-105 transition-transform" />
            <span>New Chat</span>
          </div>
          <kbd className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-black/40 text-slate-400 border border-white/[0.06]">
            ⌘N
          </kbd>
        </button>

        {/* Index Datasheet / SVD Button */}
        <button
          onClick={onOpenSvdInspector}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-white/[0.05] text-sm font-medium transition-colors"
        >
          <FileCode2 className="w-4 h-4 text-slate-400" />
          <span>Index Datasheet / SVD</span>
        </button>
      </div>

      {/* Hardware Workspaces List */}
      <div className="flex-1 overflow-y-auto px-2 py-3 space-y-4">
        <div className="px-2 flex items-center justify-between text-[11px] font-mono font-semibold tracking-wider text-slate-500 uppercase">
          <span>Hardware Workspaces</span>
          <button 
            onClick={onOpenSvdInspector}
            className="hover:text-slate-300 p-0.5 rounded hover:bg-white/[0.05]"
            title="Add Custom Hardware Workspace"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="space-y-3">
          {workspaces.map((workspace) => {
            const isCollapsed = !!collapsedWorkspaces[workspace.id];

            return (
              <div key={workspace.id} className="space-y-1">
                {/* Workspace Header Row */}
                <button
                  onClick={() => toggleWorkspace(workspace.id)}
                  className="w-full flex items-center justify-between px-2 py-1 rounded text-xs hover:bg-white/[0.04] text-slate-300 group transition-colors"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-slate-500 group-hover:text-slate-400 transition-colors">
                      {isCollapsed ? (
                        <ChevronRight className="w-3 h-3" />
                      ) : (
                        <ChevronDown className="w-3 h-3" />
                      )}
                    </span>
                    {getWorkspaceIcon(workspace.iconType)}
                    <span className="font-medium text-slate-200 truncate text-[13px]">
                      {workspace.name}
                    </span>
                  </div>

                  {/* Datasheet Reference Badge */}
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/[0.04] text-slate-400 border border-white/[0.06] shrink-0">
                    {workspace.badge}
                  </span>
                </button>

                {/* Sessions list */}
                {!isCollapsed && (
                  <div className="pl-4 pr-1 space-y-0.5">
                    {workspace.sessions.map((session) => {
                      const isActive = session.id === activeSessionId;
                      return (
                        <button
                          key={session.id}
                          onClick={() => onSelectSession(session.id, workspace.id)}
                          className={`w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-xs font-mono text-left transition-all ${
                            isActive
                              ? 'bg-cyan-950/60 text-cyan-200 border border-cyan-500/30 font-medium'
                              : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                          }`}
                        >
                          <MessageSquare
                            className={`w-3.5 h-3.5 shrink-0 ${
                              isActive ? 'text-cyan-400' : 'text-slate-500'
                            }`}
                          />
                          <span className="truncate">{session.title}</span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Bottom Status: Local Ollama & Model Indicator */}
      <div className="p-3 border-t border-white/[0.07] bg-[#090c11]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5 min-w-0">
            {/* Pulsing Green Status Dot */}
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>

            <div className="min-w-0">
              <div className="text-xs font-medium text-slate-200">Local Ollama</div>
              <div className="text-[11px] font-mono text-slate-400 truncate">
                {activeModelName}
              </div>
            </div>
          </div>

          {/* Settings Button */}
          <button
            onClick={onOpenSettings}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-white/[0.08] rounded transition-colors"
            title="Inference & Python Settings"
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );
};
