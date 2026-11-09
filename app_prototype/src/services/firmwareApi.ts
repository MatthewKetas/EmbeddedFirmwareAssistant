import type { Board, ChatMessage } from '../types/hardware';

async function request(path: string, init?: RequestInit) {
  const response = await fetch(`/api/${path}`, init).catch(() => {
    throw new Error('Could not reach the local Python backend.');
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string'
      ? body.detail
      : `The local Python backend returned HTTP ${response.status}.`);
  }
  return response;
}

export async function loadBoards(): Promise<Board[]> {
  return (await request('boards')).json();
}

export async function loadModel(): Promise<string> {
  const { active_model } = await (await request('health')).json();
  return active_model;
}

export async function uploadBoard(file: File): Promise<Board> {
  const body = new FormData();
  body.append('file', file);
  return (await request('boards', { method: 'POST', body })).json();
}

export async function streamChat(
  boardId: string,
  prompt: string,
  history: ChatMessage[],
  onText: (text: string) => void,
) {
  const response = await request('chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      board_id: boardId,
      prompt,
      history: history.map(({ sender, content }) => ({ role: sender, content })),
    }),
  });

  const reader = response.body?.pipeThrough(new TextDecoderStream()).getReader();
  if (!reader) throw new Error('The backend returned an empty response.');

  let buffer = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) throw new Error('The local model stopped before finishing its reply.');
      const lines = (buffer + value).split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        const event = JSON.parse(line);
        if (event.error) throw new Error(event.error);
        if (event.done) return;
        if (event.text) onText(event.text);
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
