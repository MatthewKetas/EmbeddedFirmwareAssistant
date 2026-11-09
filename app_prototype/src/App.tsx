import React, { useState, useEffect, useCallback } from 'react';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { ChatArea } from './components/ChatArea';
import { MessageInput } from './components/MessageInput';
import { CitedDocsDrawer } from './components/CitedDocsDrawer';
import { SvdInspectorModal } from './components/SvdInspectorModal';
import { PythonBackendModal } from './components/PythonBackendModal';
import { SettingsModal } from './components/SettingsModal';
import { INITIAL_WORKSPACES, INITIAL_MODELS } from './data/mockHardwareData';
import { HardwareWorkspace, ChatSession, ChatMessage, CitedDoc, PythonBackendStatus } from './types/hardware';
import { pythonBridge } from './services/pythonBackendBridge';

export default function App() {
  const [workspaces, setWorkspaces] = useState<HardwareWorkspace[]>(INITIAL_WORKSPACES);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string>('stm32h7');
  const [activeSessionId, setActiveSessionId] = useState<string>('session-ltdc-dma2d');
  
  const [models, setModels] = useState(INITIAL_MODELS);
  const [selectedModel, setSelectedModel] = useState<string>('qwen2.5-coder:32b');
  
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  
  // Modals & Drawers
  const [citedDocsOpen, setCitedDocsOpen] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [svdModalOpen, setSvdModalOpen] = useState(false);
  const [selectedRegisterToInspect, setSelectedRegisterToInspect] = useState<string | null>(null);
  const [pythonModalOpen, setPythonModalOpen] = useState(false);
  const [settingsModalOpen, setSettingsModalOpen] = useState(false);
  
  const [pythonStatus, setPythonStatus] = useState<PythonBackendStatus>(pythonBridge.getStatus());

  // Refresh backend status
  const refreshPythonStatus = useCallback(() => {
    setPythonStatus(pythonBridge.getStatus());
  }, []);

  useEffect(() => {
    // Initial backend ping
    pythonBridge.checkHealth().then(() => {
      refreshPythonStatus();
    });
  }, [refreshPythonStatus]);

  // Current active workspace and session
  const currentWorkspace = workspaces.find(w => w.id === activeWorkspaceId) || workspaces[0];
  const currentSession = currentWorkspace.sessions.find(s => s.id === activeSessionId) || currentWorkspace.sessions[0];

  // Aggregate all citations in current session for the "3 Cited Docs" counter
  const allCitations: CitedDoc[] = React.useMemo(() => {
    const list: CitedDoc[] = [];
    currentSession?.messages.forEach(m => {
      if (m.citations) {
        m.citations.forEach(c => {
          if (!list.some(existing => existing.docCode === c.docCode)) {
            list.push(c);
          }
        });
      }
    });
    return list;
  }, [currentSession]);

  // Keyboard shortcuts (Cmd+N, Cmd+B, Escape)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'n') {
        e.preventDefault();
        handleNewChat();
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        setSidebarOpen(prev => !prev);
      } else if (e.key === 'Escape') {
        setCitedDocsOpen(false);
        setSvdModalOpen(false);
        setPythonModalOpen(false);
        setSettingsModalOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeWorkspaceId]);

  const handleSelectSession = (sessionId: string, workspaceId: string) => {
    setActiveWorkspaceId(workspaceId);
    setActiveSessionId(sessionId);
  };

  const handleNewChat = () => {
    const newSessionId = `session-${Date.now()}`;
    const newSession: ChatSession = {
      id: newSessionId,
      title: 'New Hardware Session',
      workspaceId: activeWorkspaceId,
      targetMcu: currentWorkspace.name.split('/')[0].trim(),
      timestamp: 'Just now',
      messages: []
    };

    setWorkspaces(prev =>
      prev.map(ws => {
        if (ws.id === activeWorkspaceId) {
          return {
            ...ws,
            sessions: [newSession, ...ws.sessions]
          };
        }
        return ws;
      })
    );

    setActiveSessionId(newSessionId);
  };

  const handleSendMessage = (text: string, _attachments: string[]) => {
    if (!text.trim() || isStreaming) return;

    const userMsg: ChatMessage = {
      id: `msg-user-${Date.now()}`,
      sender: 'user',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      content: text
    };

    // Update session with user message
    setWorkspaces(prev =>
      prev.map(ws => {
        if (ws.id === activeWorkspaceId) {
          return {
            ...ws,
            sessions: ws.sessions.map(s => {
              if (s.id === activeSessionId) {
                return {
                  ...s,
                  title: s.messages.length === 0 ? (text.slice(0, 24) + '...') : s.title,
                  messages: [...s.messages, userMsg]
                };
              }
              return s;
            })
          };
        }
        return ws;
      })
    );

    setIsStreaming(true);
    setStreamingContent('');

    // Stream from Python bridge or local simulator
    pythonBridge.streamChat(
      text,
      currentSession.messages,
      currentSession.targetMcu,
      selectedModel,
      (chunk) => {
        setStreamingContent(prev => prev + chunk);
      },
      (assistantMsgPartial) => {
        setIsStreaming(false);
        setStreamingContent('');

        const assistantMsg: ChatMessage = {
          id: `msg-asst-${Date.now()}`,
          sender: 'assistant',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          content: assistantMsgPartial.content || '',
          citations: assistantMsgPartial.citations,
          codeSnippets: assistantMsgPartial.codeSnippets,
          registerBreakdown: assistantMsgPartial.registerBreakdown
        };

        setWorkspaces(prev =>
          prev.map(ws => {
            if (ws.id === activeWorkspaceId) {
              return {
                ...ws,
                sessions: ws.sessions.map(s => {
                  if (s.id === activeSessionId) {
                    return {
                      ...s,
                      messages: [...s.messages, assistantMsg]
                    };
                  }
                  return s;
                })
              };
            }
            return ws;
          })
        );
      },
      (err) => {
        console.error('Chat stream error:', err);
        setIsStreaming(false);
      }
    );
  };

  const handleOpenCitedDoc = (doc: CitedDoc) => {
    setSelectedDocId(doc.id);
    setCitedDocsOpen(true);
  };

  const handleInspectRegister = (regName: string) => {
    setSelectedRegisterToInspect(regName);
    setSvdModalOpen(true);
  };

  const handleRegenerate = () => {
    const lastUserMsg = [...currentSession.messages].reverse().find(m => m.sender === 'user');
    if (lastUserMsg) {
      handleSendMessage(lastUserMsg.content, []);
    }
  };

  const handleExportSession = () => {
    const mdContent = `# Hardware Copilot Session: ${currentSession.title}
Target MCU: ${currentSession.targetMcu}
Workspace: ${currentWorkspace.name}
Export Date: ${new Date().toLocaleString()}

${currentSession.messages.map(m => {
  const author = m.sender === 'user' ? '### Engineer' : '### Hardware Copilot';
  let body = `${author} (${m.timestamp})\n\n${m.content}\n`;
  if (m.codeSnippets && m.codeSnippets.length > 0) {
    m.codeSnippets.forEach(cs => {
      body += `\n\`\`\`${cs.language} // ${cs.filename}\n${cs.code}\n\`\`\`\n`;
    });
  }
  return body;
}).join('\n---\n\n')}`;

    const blob = new Blob([mdContent], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${currentSession.title.toLowerCase().replace(/[^a-z0-9]/g, '_')}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="h-screen w-screen flex flex-col bg-[#0b0f14] text-slate-100 overflow-hidden font-sans">
      {/* Top Header Bar */}
      <Header
        sessionTitle={currentSession?.title || 'DMA2D & LTDC Register Config'}
        targetMcu={currentSession?.targetMcu || 'STM32H743ZI'}
        citedDocsCount={allCitations.length || 3}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen(prev => !prev)}
        onOpenCitedDocs={() => {
          setSelectedDocId(null);
          setCitedDocsOpen(true);
        }}
        onOpenPythonModal={() => setPythonModalOpen(true)}
        onExportSession={handleExportSession}
        pythonStatus={pythonStatus}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar */}
        {sidebarOpen && (
          <Sidebar
            workspaces={workspaces}
            activeSessionId={activeSessionId}
            onSelectSession={handleSelectSession}
            onNewChat={handleNewChat}
            onOpenSvdInspector={() => {
              setSelectedRegisterToInspect(null);
              setSvdModalOpen(true);
            }}
            onOpenSettings={() => setSettingsModalOpen(true)}
            activeModelName={selectedModel}
          />
        )}

        {/* Center / Right Chat View */}
        <main className="flex-1 flex flex-col bg-[#0b0f14] overflow-hidden relative">
          <ChatArea
            messages={currentSession?.messages || []}
            isStreaming={isStreaming}
            streamingContent={streamingContent}
            onOpenCitedDoc={handleOpenCitedDoc}
            onRegenerate={handleRegenerate}
            onInspectRegister={handleInspectRegister}
          />

          {/* Bottom Floating Input Bar */}
          <MessageInput
            onSendMessage={handleSendMessage}
            disabled={isStreaming}
            models={models}
            selectedModel={selectedModel}
            onSelectModel={setSelectedModel}
            onOpenFileAttachment={() => {
              setSelectedRegisterToInspect(null);
              setSvdModalOpen(true);
            }}
          />
        </main>
      </div>

      {/* Cited Documents Slide-Over Drawer */}
      <CitedDocsDrawer
        isOpen={citedDocsOpen}
        onClose={() => setCitedDocsOpen(false)}
        citations={allCitations}
        selectedDocId={selectedDocId}
      />

      {/* SVD Register & Bitfield Explorer Modal */}
      <SvdInspectorModal
        isOpen={svdModalOpen}
        onClose={() => setSvdModalOpen(false)}
        initialRegisterName={selectedRegisterToInspect}
      />

      {/* Python Backend & Desktop Wire-Up Modal */}
      <PythonBackendModal
        isOpen={pythonModalOpen}
        onClose={() => setPythonModalOpen(false)}
        status={pythonStatus}
        onRefreshStatus={refreshPythonStatus}
      />

      {/* Inference & System Settings Modal */}
      <SettingsModal
        isOpen={settingsModalOpen}
        onClose={() => setSettingsModalOpen(false)}
        models={models}
        selectedModel={selectedModel}
        onSelectModel={setSelectedModel}
        onOpenPythonBridge={() => setPythonModalOpen(true)}
      />
    </div>
  );
}
