import { useRef, useState } from 'react';
import { Cpu, FolderPlus, MessageSquare, MessageSquarePlus, Plus } from 'lucide-react';
import type { Board, Project } from '../types/hardware';

interface SidebarProps {
  boards: Board[];
  projects: Project[];
  activeProjectId: string;
  uploading: boolean;
  boardError: string;
  onImportBoard: (file: File) => void;
  onCreateProject: (name: string, boardId: string) => void;
  onCreateChat: () => void;
  onSelectProject: (projectId: string) => void;
  onSelectChat: (projectId: string, chatId: string) => void;
}

const action = 'flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-300 hover:bg-white/10 disabled:opacity-50';

export function Sidebar({
  boards, projects, activeProjectId, uploading, boardError, onImportBoard,
  onCreateProject, onCreateChat, onSelectProject, onSelectChat,
}: SidebarProps) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [boardId, setBoardId] = useState('');
  const selectedBoardId = boardId || boards[0]?.id || '';

  return (
    <aside className="w-64 shrink-0 overflow-y-auto border-r border-white/[0.07] bg-[#0a0d13] px-3 py-3">
      <div className="space-y-1 border-b border-white/[0.07] pb-3">
        <button className={`${action} bg-white/[0.05]`} onClick={onCreateChat} disabled={!activeProjectId}>
          <MessageSquarePlus className="size-4 text-cyan-400" /> New chat
        </button>
        <button className={action} onClick={() => setCreating(open => !open)} disabled={!boards.length}
          aria-expanded={creating}>
          <FolderPlus className="size-4 text-slate-400" /> New project
        </button>
        {creating && (
          <form className="space-y-2 px-2 pb-1 text-sm" onSubmit={event => {
            event.preventDefault();
            if (!name.trim() || !selectedBoardId) return;
            onCreateProject(name.trim(), selectedBoardId);
            setName('');
            setCreating(false);
          }}>
            <label className="block text-xs text-slate-400">
              Project name
              <input autoFocus required maxLength={70} value={name} onChange={event => setName(event.target.value)}
                className="mt-1 w-full rounded border border-white/10 bg-[#141b25] px-2 py-1 text-sm text-slate-100" />
            </label>
            <label className="block text-xs text-slate-400">
              Board
              <select value={selectedBoardId} onChange={event => setBoardId(event.target.value)}
                className="mt-1 w-full rounded border border-white/10 bg-[#141b25] px-2 py-1 text-sm text-slate-100">
                {boards.map(board => <option key={board.id} value={board.id}>{board.name} ({board.revision})</option>)}
              </select>
            </label>
            <button type="submit" className="rounded bg-cyan-950 px-3 py-1 text-cyan-200">Create project</button>
          </form>
        )}
      </div>

      <div className="my-3 flex items-center justify-between px-2">
        <h2 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-slate-400">Projects</h2>
        <button type="button" onClick={() => fileInput.current?.click()} disabled={uploading || !boards.length}
          className="rounded p-1 text-cyan-400 hover:bg-white/10 disabled:opacity-50"
          aria-label="Add board" title="Add board from CMSIS-SVD XML">
          <Plus className="size-4" />
        </button>
        <input ref={fileInput} hidden type="file" accept=".xml,.svd,application/xml,text/xml"
          onChange={event => {
            const file = event.target.files?.[0];
            event.target.value = '';
            if (file) onImportBoard(file);
          }} />
      </div>
      {uploading && <p role="status" className="px-2 pb-3 text-xs text-slate-400">Importing board…</p>}
      {boardError && <p role="alert" className="px-2 pb-3 text-xs text-amber-300">{boardError}</p>}

      <div className="space-y-2">
        {projects.map(project => (
          <div key={project.id}>
            <button onClick={() => onSelectProject(project.id)} aria-expanded={project.id === activeProjectId}
              className={`${action} font-medium`}>
              <Cpu className="size-4 shrink-0 text-cyan-400" />
              <span className="truncate">{project.name}</span>
            </button>
            {project.id === activeProjectId && (
              <div className="ml-4 space-y-1">
                {project.chats.map(chat => (
                  <button key={chat.id} onClick={() => onSelectChat(project.id, chat.id)}
                    aria-current={chat.id === project.activeChatId ? 'true' : undefined}
                    className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left font-mono text-xs ${
                      chat.id === project.activeChatId
                        ? 'bg-cyan-950/60 text-cyan-200 ring-1 ring-inset ring-cyan-500/30'
                        : 'text-slate-400 hover:bg-white/5'
                    }`}>
                    <MessageSquare className="size-3.5 shrink-0" />
                    <span className="truncate">{chat.title}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </aside>
  );
}
