/* 问：流式对话 + 引用 + 会话历史 */
import { api, chatStream } from '../api.js';
import { bindMdRefs, mdRender, openSheet, toast } from '../components.js';
import { h } from '../util.js';

const state = { sessionId: null, streaming: false };

export function render(container, ctx) {
  container.classList.add('chat-mode');
  const scroll = h('div', { class: 'chat-scroll' });
  const input = h('textarea', { rows: 1, placeholder: '问见微：政策、公司、申报窗口…', enterkeyhint: 'send' });
  const sendBtn = h('button', { class: 'send-btn', title: '发送' },
    h('span', { html: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13M22 2l-7 20-4-9-9-4z"/></svg>' }));
  const inputWrap = h('div', { class: 'chat-input-wrap' },
    h('div', { class: 'chat-input' },
      h('button', {
        class: 'icon-btn', title: '会话历史', style: 'border:none;background:none;width:34px;height:34px',
        onclick: showHistory,
      }, h('span', { html: '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 3"/></svg>' })),
      input, sendBtn));
  container.append(scroll, inputWrap);

  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 110) + 'px';
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
  });
  sendBtn.addEventListener('click', send);

  if (state.sessionId) {
    api.session(state.sessionId)
      .then((s) => { s.messages.forEach((m) => appendMsg(m.role, m.content, m.citations)); scrollBottom(); })
      .catch(() => { state.sessionId = null; showWelcome(); });
  } else {
    showWelcome();
  }

  function showWelcome() {
    api.sessions().then(({ suggested }) => {
      scroll.replaceChildren(
        h('div', { style: 'padding:26px 4px 14px;text-align:center' },
          h('div', { class: 'brand-seal', style: 'width:52px;height:52px;font-size:28px;border-radius:13px;margin:0 auto 12px' }, '问'),
          h('p', { style: 'font-family:var(--font-display);font-size:18px;font-weight:700' }, '问你的私人情报分析师'),
          h('p', { class: 'muted', style: 'margin-top:4px' }, '回答基于已收录情报，标注 [n] 引用可点击溯源')),
        ...suggested.map((q) => h('button', { class: 'suggest-card', onclick: () => { input.value = q; send(); } }, q)));
    }).catch(() => {});
  }

  function appendMsg(role, content, citations = []) {
    const bubble = h('div', { class: 'bubble' });
    if (role === 'assistant') {
      const md = h('div', { class: 'md', html: mdRender(content) });
      bindMdRefs(md, { onOpenItem: ctx.openItem, citations });
      bubble.append(md);
      if (citations?.length) {
        bubble.append(h('div', { class: 'cite-strip' }, citations.map((c) =>
          h('button', { class: 'chip chip-btn', onclick: () => ctx.openItem(c.item_id) },
            `[${c.n}] ${c.title.slice(0, 18)}${c.title.length > 18 ? '…' : ''}`))));
      }
    } else {
      bubble.textContent = content;
    }
    const msg = h('div', { class: `msg ${role}` }, bubble);
    scroll.append(msg);
    return bubble;
  }

  async function send() {
    const text = input.value.trim();
    if (!text || state.streaming) return;
    input.value = ''; input.style.height = 'auto';
    if (scroll.querySelector('.suggest-card')) scroll.replaceChildren();
    appendMsg('user', text);
    scrollBottom();

    state.streaming = true;
    sendBtn.disabled = true;
    const bubble = appendMsg('assistant', '');
    const md = bubble.querySelector('.md');
    md.classList.add('typing-cursor');
    let acc = '', citations = [];
    try {
      await chatStream(text, state.sessionId, {
        onMeta: (m) => { state.sessionId = m.session_id; citations = m.citations || []; },
        onDelta: (t) => {
          acc += t;
          md.innerHTML = mdRender(acc);
          scrollBottom();
        },
        onError: (msg) => { acc += `\n> ⚠ ${msg}`; md.innerHTML = mdRender(acc); },
      });
    } catch (e) {
      toast('对话失败：' + e.message);
    } finally {
      md.classList.remove('typing-cursor');
      md.innerHTML = mdRender(acc);
      bindMdRefs(md, { onOpenItem: ctx.openItem, citations });
      const used = new Set([...acc.matchAll(/\[(\d{1,2})\]/g)].map((m) => parseInt(m[1], 10)));
      const kept = citations.filter((c) => used.has(c.n));
      if (kept.length) {
        bubble.append(h('div', { class: 'cite-strip' }, kept.map((c) =>
          h('button', { class: 'chip chip-btn', onclick: () => ctx.openItem(c.item_id) },
            `[${c.n}] ${c.title.slice(0, 18)}${c.title.length > 18 ? '…' : ''}`))));
      }
      state.streaming = false;
      sendBtn.disabled = false;
      scrollBottom();
    }
  }

  function showHistory() {
    api.sessions().then(({ sessions }) => {
      openSheet(h('div', {},
        h('div', { class: 'detail-title', style: 'font-size:17px' }, '会话历史'),
        h('button', {
          class: 'btn', style: 'width:100%;margin-bottom:10px',
          onclick: () => { state.sessionId = null; location.reload(); },
        }, '＋ 新对话'),
        sessions.length ? sessions.map((s) => h('div', {
          class: 'lineage-entry', style: 'padding:10px 0',
          onclick: () => { state.sessionId = s.id; location.hash = '#/chat'; location.reload(); },
        }, h('span', { class: 'dt' }, s.updated_at.slice(5, 10)), h('span', {}, s.title)))
          : h('p', { class: 'muted' }, '暂无历史会话')));
    }).catch((e) => toast(e.message));
  }

  function scrollBottom() {
    scroll.scrollTop = scroll.scrollHeight;
  }

  return () => container.classList.remove('chat-mode');
}
