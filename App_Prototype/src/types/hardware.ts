export interface CitedDoc {
  id: string;
  title: string;
  docCode: string; // e.g. "RM0433 Rev 7 · Sec 34.7.1, p. 1942"
  section: string;
  page: number | string;
  type: 'reference_manual' | 'datasheet' | 'errata' | 'app_note';
  snippet: string;
  verified: boolean;
  statusText?: string; // e.g. "Errata ES0392 § 2.2.14 verified"
  url?: string;
}

export interface RegisterField {
  name: string;
  bitStart: number;
  bitEnd: number;
  access: 'R' | 'W' | 'RW' | 'RC' | 'RS';
  resetValue: number;
  description: string;
}

export interface SvdRegister {
  name: string;
  offset: string;
  size: number;
  description: string;
  resetValue: string;
  fields: RegisterField[];
}

export interface SvdPeripheral {
  name: string;
  baseAddress: string;
  description: string;
  registers: SvdRegister[];
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  timestamp: string;
  content: string;
  citations?: CitedDoc[];
  codeSnippets?: {
    filename: string;
    language: string;
    code: string;
  }[];
  registerBreakdown?: {
    register: string;
    description: string;
  }[];
}

export interface ChatSession {
  id: string;
  title: string;
  workspaceId: string;
  targetMcu: string;
  timestamp: string;
  messages: ChatMessage[];
}

export interface HardwareWorkspace {
  id: string;
  name: string;
  core: string;
  badge: string; // e.g. "DS12110", "TRM v1.4", "PS v1.3", "C2000"
  iconType: 'chip' | 'cpu' | 'radio' | 'dsp';
  sessions: ChatSession[];
  datasheets: string[];
}

export interface ModelConfig {
  id: string;
  name: string;
  provider: 'ollama' | 'python_bridge' | 'lmstudio' | 'gemini';
  contextLength: string;
  isLocal: boolean;
}

export interface PythonBackendStatus {
  connected: boolean;
  url: string;
  mode: 'live' | 'simulated';
  latencyMs: number;
  activeModel: string;
  version: string;
}
