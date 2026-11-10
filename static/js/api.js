/* API 客户端 + SSE 流读取 */
const BASE = '/api/v1';

async function req(path, opts = {}) {
  const r = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try { detail = (await r.json()).detail || detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return r.json();
}

export const api = {
  feed: (params = {}) => req('/feed?' + new URLSearchParams(Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')))),
  item: (id) => req(`/items/${id}`),
  feedback: (id, action) => req(`/items/${id}/feedback`, { method: 'POST', body: { action } }),
  search: (q) => req('/search?' + new URLSearchParams({ q })),
  lineages: () => req('/policies/lineages'),

  briefToday: () => req('/brief/today'),
  briefs: (limit = 14) => req(`/briefs?limit=${limit}`),
  briefByDate: (d) => req(`/briefs/${d}`),
  briefGenerate: () => req('/brief/generate', { method: 'POST' }),
  briefGenerateStatus: () => req('/brief/generate/status'),

  profile: () => req('/profile'),
  saveProfile: (body) => req('/profile', { method: 'PUT', body }),
  saveLenses: (lenses) => req('/lenses', { method: 'PUT', body: lenses }),
  entities: (params = {}) => req('/entities?' + new URLSearchParams(params)),
  entityTimeline: (id) => req(`/entities/${id}/timeline`),
  watchEntity: (id, watch) => req(`/entities/${id}/watch`, { method: 'POST', body: { watch } }),
  createEntity: (body) => req('/entities', { method: 'POST', body }),

  sessions: () => req('/chat/sessions'),
  session: (id) => req(`/chat/sessions/${id}`),
  deleteSession: (id) => req(`/chat/sessions/${id}`, { method: 'DELETE' }),

  status: () => req('/system/status'),
  sources: () => req('/system/sources'),
  fetchSource: (id) => req(`/system/sources/${id}/fetch`, { method: 'POST' }),
  ingestAll: () => req('/system/ingest', { method: 'POST' }),
  analyzeNow: () => req('/system/analyze', { method: 'POST' }),

  evolutionLog: () => req('/evolution/log'),
  evolutionRun: () => req('/evolution/run', { method: 'POST' }),
  decideSuggestion: (id, decision) => req(`/evolution/suggestions/${id}/${decision}`, { method: 'POST' }),
};

/* SSE：POST /chat/stream。signal 可中止；末包没有换行也会被读完。 */
export async function chatStream(message, sessionId, { onMeta, onThinking, onDelta, onError, onDone, signal } = {}) {
  let r;
  try {
    r = await fetch(BASE + '/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ message, session_id: sessionId }),
      signal,
    });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    onError?.(e.message || '连接中断');
    return;
  }
  if (!r.ok || !r.body) {
    let detail = `连接失败（HTTP ${r.status}）`;
    try { detail = (await r.json()).detail || detail; } catch { /* 非 JSON */ }
    onError?.(detail);
    return;
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = '', event = '';
  const take = (line) => {
    const s = line.replace(/\r$/, '');
    if (!s) { event = ''; return; }
    if (s.startsWith(':')) return;
    if (s.startsWith('event:')) { event = s.slice(6).trim(); return; }
    if (!s.startsWith('data:')) return;
    let d;
    try { d = JSON.parse(s.slice(5).trim()); } catch { return; }
    if (event === 'meta') onMeta?.(d);
    else if (event === 'thinking') onThinking?.(d.s || 0);
    else if (event === 'delta') onDelta?.(d.text || '');
    else if (event === 'error') onError?.(d.message || '未知错误');
    else if (event === 'done') onDone?.(d);
  };
  try {
    for (;;) {
      const { done, value } = await reader.read();
      buf += decoder.decode(value || new Uint8Array(), { stream: !done });
      const lines = buf.split('\n');
      buf = done ? '' : (lines.pop() ?? '');
      for (const line of lines) take(line);
      if (done) {
        if (buf) take(buf);
        break;
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    onError?.(e.message || '连接中断');
  } finally {
    reader.releaseLock?.();
  }
}
