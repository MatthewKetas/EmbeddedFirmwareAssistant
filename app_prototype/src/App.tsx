import { Fragment, useEffect, useState } from 'react';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { ChatArea } from './components/ChatArea';
import { MessageInput } from './components/MessageInput';
import { loadBoards, loadModel, streamChat, uploadBoard } from './services/firmwareApi';
import type { Board, ChatMessage, Project, ProjectChat } from './types/hardware';

function newChat(): ProjectChat {
  return { id: crypto.randomUUID(), title: 'New chat', messages: [] };
}

function newProject(name: string, boardId: string): Project {
  const chat = newChat();
  return { id: crypto.randomUUID(), name, boardId, activeChatId: chat.id, chats: [chat] };
}

function message(sender: ChatMessage['sender'], content: string): ChatMessage {
  return {
    id: crypto.randomUUID(),
    sender,
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    content,
  };
}

export default function App() {
  const [boards, setBoards] = useState<Board[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [model, setModel] = useState('');
  const [setupError, setSetupError] = useState('');
  const [boardError, setBoardError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [reply, setReply] = useState<{ chatId: string; text: string } | null>(null);

  const project = projects.find(item => item.id === activeProjectId);
  const board = boards.find(item => item.id === project?.boardId);
  const chat = project?.chats.find(item => item.id === project.activeChatId);

  async function connect() {
    setSetupError('');
    try {
      const [availableBoards, activeModel] = await Promise.all([loadBoards(), loadModel()]);
      const starterProjects = availableBoards.map(item => newProject(item.name, item.id));
      setBoards(availableBoards);
      setProjects(starterProjects);
      setActiveProjectId(starterProjects[0]?.id ?? '');
      setModel(activeModel);
    } catch (error) {
      setSetupError((error as Error).message);
    }
  }

  useEffect(() => { void connect(); }, []);

  function updateProject(id: string, update: (project: Project) => Project) {
    setProjects(current => current.map(item => item.id === id ? update(item) : item));
  }

  function createProject(name: string, boardId: string) {
    const item = newProject(name, boardId);
    setProjects(current => [...current, item]);
    setActiveProjectId(item.id);
  }

  function createChat() {
    if (!project) return;
    const item = newChat();
    updateProject(project.id, current => ({
      ...current, activeChatId: item.id, chats: [item, ...current.chats],
    }));
  }

  function selectChat(projectId: string, chatId: string) {
    setActiveProjectId(projectId);
    updateProject(projectId, current => ({ ...current, activeChatId: chatId }));
  }

  async function importBoard(file: File) {
    setBoardError('');
    setUploading(true);
    try {
      const imported = await uploadBoard(file);
      setBoards(current => current.some(item => item.id === imported.id) ? current : [...current, imported]);
      const existingProject = projects.find(item => item.boardId === imported.id);
      if (existingProject) setActiveProjectId(existingProject.id);
      else createProject(imported.name, imported.id);
    } catch (error) {
      setBoardError((error as Error).message);
    } finally {
      setUploading(false);
    }
  }

  async function send(text: string) {
    if (!project || !chat || reply) return;
    const projectId = project.id;
    const chatId = chat.id;

    function updateChat(update: (current: ProjectChat) => ProjectChat) {
      updateProject(projectId, current => ({
        ...current, chats: current.chats.map(item => item.id === chatId ? update(item) : item),
      }));
    }

    const userMessage = message('user', text);
    updateChat(current => ({
      ...current,
      title: current.messages.length ? current.title : text.slice(0, 45),
      messages: [...current.messages, userMessage],
      error: undefined,
    }));
    setReply({ chatId, text: '' });

    let answer = '';
    try {
      await streamChat(project.boardId, text, chat.messages, chunk => {
        answer += chunk;
        setReply({ chatId, text: answer });
      });
      if (!answer.trim()) throw new Error('The local model returned an empty reply.');
      const assistantMessage = message('assistant', answer);
      updateChat(current => ({ ...current, messages: [...current.messages, assistantMessage] }));
    } catch (error) {
      updateChat(current => ({ ...current, error: (error as Error).message }));
    } finally {
      setReply(null);
    }
  }

  return (
    <div className="h-screen w-screen flex flex-col bg-[#0b0f14] text-slate-100 overflow-hidden">
      <Header project={project?.name} board={board?.name} title={chat?.title} model={model}
        onToggleSidebar={() => setSidebarOpen(open => !open)} />
      <div className="flex flex-1 min-h-0">
        {sidebarOpen && (
          <Sidebar boards={boards} projects={projects} activeProjectId={activeProjectId}
            uploading={uploading} boardError={boardError} onImportBoard={importBoard}
            onCreateProject={createProject} onCreateChat={createChat}
            onSelectProject={setActiveProjectId} onSelectChat={selectChat} />
        )}
        <main className="flex-1 min-w-0 flex flex-col">
          {setupError ? (
            <div className="m-auto p-6 text-center">
              <p role="alert" className="mb-3 text-amber-300">{setupError}</p>
              <button className="rounded-lg bg-white/10 px-4 py-2" onClick={connect}>Retry connection</button>
            </div>
          ) : chat ? (
            <Fragment key={chat.id}>
              <ChatArea messages={chat.messages} error={chat.error}
                streamingText={reply?.chatId === chat.id ? reply.text : undefined} />
              <MessageInput onSendMessage={send} disabled={!!reply} />
            </Fragment>
          ) : (
            <p role="status" className="m-auto text-slate-400">Connecting to the local backend…</p>
          )}
        </main>
      </div>
    </div>
  );
}
