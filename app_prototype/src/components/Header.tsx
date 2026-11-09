import { Cpu, PanelLeft } from 'lucide-react';

interface HeaderProps {
  project?: string;
  board?: string;
  title?: string;
  model: string;
  onToggleSidebar: () => void;
}

export function Header({ project, board, title, model, onToggleSidebar }: HeaderProps) {
  return (
    <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-white/[0.07] bg-[#0c1017] px-4">
      <div className="flex min-w-0 items-center gap-3">
        <button onClick={onToggleSidebar} aria-label="Toggle sidebar"
          className="rounded p-1.5 text-slate-400 hover:bg-white/10 hover:text-slate-200">
          <PanelLeft className="size-4" />
        </button>
        <span className="truncate text-sm font-medium">{project || 'Hardware Copilot'}</span>
        {title && <span className="hidden truncate border-l border-white/10 pl-3 text-xs text-slate-400 sm:inline">{title}</span>}
        {board && (
          <span className="flex min-w-0 items-center gap-1 rounded bg-cyan-950/70 px-2 py-0.5 font-mono text-[11px] text-cyan-300">
            <Cpu className="size-3 shrink-0" /> <span className="truncate">{board}</span>
          </span>
        )}
      </div>
      <span className="hidden shrink-0 items-center gap-2 font-mono text-xs text-slate-400 md:flex">
        <span className={`size-2 rounded-full ${model ? 'bg-emerald-400' : 'bg-amber-400'}`} />
        {model || 'Local backend offline'}
      </span>
    </header>
  );
}
