/* 工具：DOM 构建、轻量 Markdown、时间格式化 */

export function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c.nodeType ? c : document.createTextNode(c));
  }
  return el;
}

/* 轻量 Markdown → HTML（标题/加粗/列表/引用/链接/[#id]条目引用/[n]资料引用） */
export function mdRender(src) {
  const lines = String(src || '').split('\n');
  const out = [];
  let inUl = false, inOl = false;
  const closeList = () => {
    if (inUl) { out.push('</ul>'); inUl = false; }
    if (inOl) { out.push('</ol>'); inOl = false; }
  };
  const inline = (s) => esc(s)
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\[#(\d+)\]/g, '<span class="item-ref" data-item="$1">#$1</span>')
    .replace(/\[(\d{1,2})\]/g, '<span class="cite-ref" data-cite="$1">[$1]</span>');
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) { closeList(); continue; }
    let m;
    if ((m = line.match(/^(#{1,3})\s+(.*)/))) {
      closeList();
      out.push(`<h${m[1].length}>${inline(m[2])}</h${m[1].length}>`);
    } else if ((m = line.match(/^>\s?(.*)/))) {
      closeList();
      out.push(`<blockquote>${inline(m[1])}</blockquote>`);
    } else if ((m = line.match(/^[-*]\s+(.*)/))) {
      if (!inUl) { closeList(); out.push('<ul>'); inUl = true; }
      out.push(`<li>${inline(m[1])}</li>`);
    } else if ((m = line.match(/^\d+[.、]\s+(.*)/))) {
      if (!inOl) { closeList(); out.push('<ol>'); inOl = true; }
      out.push(`<li>${inline(m[1])}</li>`);
    } else {
      closeList();
      out.push(`<p>${inline(line)}</p>`);
    }
  }
  closeList();
  return out.join('\n');
}

const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六'];

export function fmtDateCN(d = new Date()) {
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
}
export function weekdayCN(d = new Date()) {
  return `星期${WEEKDAYS[d.getDay()]}`;
}

export function relTime(iso) {
  if (!iso) return '';
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return iso;
  const s = (Date.now() - t.getTime()) / 1000;
  if (s < 90) return '刚刚';
  if (s < 3600) return `${Math.floor(s / 60)}分钟前`;
  if (s < 86400) return `${Math.floor(s / 3600)}小时前`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}天前`;
  return iso.slice(0, 10);
}

export function daysUntil(dateStr) {
  if (!dateStr) return null;
  const target = new Date(dateStr + 'T23:59:59+08:00');
  const diff = Math.ceil((target - Date.now()) / 86400000);
  return diff;
}

export function debounce(fn, ms = 300) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}
