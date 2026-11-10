/* 问：SSE 流式，[n] 用事件委托，换会话不刷新整页。 */
import { api, chatStream } from '../api.js';
import { delegateRefs, mdRender, openSheet, toast } from '../components.js';
import { h } from '../util.js';

const state = { sessionId: null };

export function render(container, ctx) {
  container.classList.add('chat-mode');
  const scroll = h('div', { class: 'chat-scroll' });
  const input = h('textarea', { rows: 1, placeholder: '问政策、公司、申报窗口', 'aria-label': '提问', enterkeyhint: 'send' });
  const sendBtn = h('button', { type: 'button', class: 'send-btn', title: '发送', 'aria-label': '发送' }, '发送');
  const inputWrap = h('div', { class: 'chat-input-wrap' },
    h('div', { class: 'chat-input' },
      h('button', {
        type: 'button', class: 'icon-btn', title: '会话', 'aria-label': '会话历史',
        onclick: showHistory,
      }, '会话'),
      input, sendBtn));
  container.append(scroll, inputWrap);

  let streaming = false;
  let abort = null;
  const cites = new WeakMap();

  delegateRefs(scroll, {
    onOpenItem: ctx.openItem,
    citationsOf: (host) => cites.get(host) || [],
  });

  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
  });
  sendBtn.addEventListener('click', () => { if (streaming) stop(); else send(); });

  if (state.sessionId) {
    api.session(state.sessionId)
      .then((s) => { s.messages.forEach((m) => appendMsg(m.role, m.content, m.citations)); scrollBottom(); })
      .catch(() => { state.sessionId = null; showWelcome(); });
  } else showWelcome();

  function showWelcome() {
    scroll.replaceChildren(h('div', { class: 'skeleton', 'aria-hidden': 'true' }, h('i'), h('i')));
    api.sessions().then(({ suggested }) => {
      scroll.replaceChildren(
        h('div', { class: 'chat-welcome' },
          h('p', { class: 'kicker' }, '问'),
          h('h1', {}, '问你的情报分析师'),
          h('p', { class: 'muted' }, '回答来自己收录的情报。句末的 [n] 可以点开原文。')),
        ...(suggested || []).map((q) => h('button', {
          type: 'button', class: 'suggest-card',
          onclick: () => { input.value = q; send(); },
        }, q)));
    }).catch((e) => {
      scroll.replaceChildren(h('div', { class: 'error-box' },
        h('p', { class: 'empty-title' }, '提问入口没打开'),
        h('p', { class: 'muted' }, e.message),
        h('button', { type: 'button', class: 'btn small', onclick: showWelcome }, '重试')));
    });
  }

  function appendMsg(role, content, citations = []) {
    const bubble = h('div', { class: 'bubble', 'data-cite-host': '1' });
    cites.set(bubble, citations || []);
    if (role === 'assistant') {
      const md = h('div', { class: 'md', html: mdRender(content) });
      bubble.append(md);
      if (citations?.length) bubble.append(citeStrip(citations));
    } else bubble.textContent = content;
    const msg = h('div', { class: `msg ${role}` }, bubble);
    scroll.append(msg);
    return bubble;
  }

  function citeStrip(citations) {
    return h('div', { class: 'cite-strip' }, citations.map((c) =>
      h('button', {
        type: 'button', class: 'chip chip-btn',
        onclick: () => ctx.openItem(c.item_id),
      }, `[${c.n}] ${c.title}`)));
  }

  function scrollBottom() {
    scroll.scrollTop = scroll.scrollHeight;
  }

  function stop() {
    abort?.abort();
  }

  async function send() {
    const text = input.value.trim();
    if (!text || streaming) return;
    input.value = '';
    input.style.height = 'auto';
    if (scroll.querySelector('.suggest-card, .chat-welcome')) scroll.replaceChildren();
    appendMsg('user', text);

    streaming = true;
    sendBtn.textContent = '停止';
    sendBtn.setAttribute('aria-label', '停止');
    const bubble = appendMsg('assistant', '');
    const md = bubble.querySelector('.md');
    md.classList.add('typing-cursor');
    md.textContent = '在想…';
    let acc = '';
    let citations = [];
    abort = new AbortController();
    scrollBottom();
    try {
      await chatStream(text, state.sessionId, {
        signal: abort.signal,
        onMeta: (m) => {
          state.sessionId = m.session_id;
          citations = m.citations || [];
          cites.set(bubble, citations);
        },
        onThinking: (s) => { if (!acc) md.textContent = s ? `在想… ${s}s` : '在想…'; },
        onDelta: (t) => {
          acc += t;
          md.innerHTML = mdRender(acc);
          scrollBottom();
        },
        onError: (msg) => {
          acc += (acc ? '\n\n' : '') + `> ${msg}`;
          md.innerHTML = mdRender(acc);
        },
        onDone: () => {},
      });
    } catch (e) {
      if (e.name !== 'AbortError') toast('对话中断：' + e.message);
      else if (!acc) acc = '已停止。';
    } finally {
      streaming = false;
      abort = null;
      sendBtn.textContent = '发送';
      sendBtn.setAttribute('aria-label', '发送');
      md.classList.remove('typing-cursor');
      if (!acc) {
        md.innerHTML = mdRender('没有得到回答。');
      } else md.innerHTML = mdRender(acc);
      cites.set(bubble, citations);
      const used = new Set([...acc.matchAll(/\[(\d{1,2})\]/g)].map((m) => parseInt(m[1], 10)));
      const kept = citations.filter((c) => used.has(c.n));
      bubble.querySelector('.cite-strip')?.remove();
      if (kept.length) bubble.append(citeStrip(kept));
      scrollBottom();
    }
  }

  function showHistory() {
    api.sessions().then(({ sessions }) => {
      openSheet(h('div', {},
        h('h2', { class: 'detail-title' }, '会话'),
        h('button', {
          type: 'button', class: 'btn',
          onclick: () => { state.sessionId = null; showWelcome(); document.getElementById('overlay').click(); },
        }, '新对话'),
        sessions.length
          ? sessions.map((s) => h('button', {
            type: 'button', class: 'lineage-entry history-item',
            onclick: () => openSession(s.id),
          }, h('span', { class: 'dt' }, (s.updated_at || '').slice(5, 10)), h('span', {}, s.title)))
          : h('p', { class: 'muted' }, '还没有历史会话')));
    }).catch((e) => toast(e.message));
  }

  function openSession(id) {
    state.sessionId = id;
    document.getElementById('overlay').click();
    scroll.replaceChildren(h('div', { class: 'skeleton', 'aria-hidden': 'true' }, h('i'), h('i')));
    api.session(id).then((s) => {
      scroll.replaceChildren();
      s.messages.forEach((m) => appendMsg(m.role, m.content, m.citations));
      scrollBottom();
    }).catch((e) => {
      scroll.replaceChildren(h('div', { class: 'error-box' },
        h('p', { class: 'empty-title' }, '这场会话没打开'),
        h('p', { class: 'muted' }, e.message)));
    });
  }

  return () => {
    abort?.abort();
    container.classList.remove('chat-mode');
  };
}
