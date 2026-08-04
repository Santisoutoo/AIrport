// Chat bubble rendering shared by the PTT pipeline and the WebSocket client.

export interface ChatMessage {
  type: 'controller' | 'agent';
  text: string;
  callsign?: string;
  dep?: string | null;
  time?: string;
}

export const ROBOT_SVG = `<svg viewBox="0 0 18 18" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="6" width="12" height="9" rx="2"/>
  <circle cx="6.5" cy="10.5" r="1" fill="currentColor" stroke="none"/>
  <circle cx="11.5" cy="10.5" r="1" fill="currentColor" stroke="none"/>
  <path d="M6.5 13h5"/>
  <path d="M9 6V3.5"/>
  <circle cx="9" cy="2.5" r="1" fill="currentColor" stroke="none"/>
  <path d="M3 9.5H1.5M16.5 9.5H15"/>
</svg>`;

export function escChat(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export function buildBubble(m: ChatMessage): string {
  const safe = escChat(m.text);
  if (m.type === 'controller') {
    return (
      `<div class="chat-msg chat-ctrl">` +
      `<div class="chat-bubble chat-bubble-ctrl">${safe}</div>` +
      `<div class="chat-meta"><span class="chat-sender">TWR</span><span class="chat-time">${m.time}</span></div>` +
      `</div>`
    );
  }
  const cs = escChat(m.callsign || '???');
  const depCls = m.dep ? ` chat-dep-${m.dep.toLowerCase()}` : '';
  return (
    `<div class="chat-msg chat-agent${depCls}">` +
    `<div class="chat-agent-header">${ROBOT_SVG}<span class="chat-callsign">${cs}</span></div>` +
    `<div class="chat-bubble chat-bubble-agent">${safe}</div>` +
    `<div class="chat-meta"><span class="chat-time">${m.time}</span></div>` +
    `</div>`
  );
}

/** Transient three-dot typing indicator (#chat-typing). */
export function showTyping(side: 'ctrl' | 'agent', dep?: string | null): void {
  const log = document.getElementById('chat-log');
  if (!log || document.getElementById('chat-typing')) return;
  const div = document.createElement('div');
  div.id = 'chat-typing';
  const isAgent = side === 'agent';
  const depCls = isAgent && dep ? ` chat-dep-${dep.toLowerCase()}` : '';
  div.className = 'chat-msg ' + (isAgent ? 'chat-agent' : 'chat-ctrl') + depCls;
  const bubbleClass = isAgent ? 'chat-bubble-agent' : 'chat-bubble-ctrl';
  div.innerHTML =
    `<div class="chat-bubble ${bubbleClass} chat-typing-bubble">` +
    `<span class="typing-dot"></span>` +
    `<span class="typing-dot"></span>` +
    `<span class="typing-dot"></span>` +
    `</div>`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

export function hideTyping(): void {
  document.getElementById('chat-typing')?.remove();
}

export function utcTime(d: Date): string {
  return (
    String(d.getUTCHours()).padStart(2, '0') +
    ':' +
    String(d.getUTCMinutes()).padStart(2, '0') +
    ':' +
    String(d.getUTCSeconds()).padStart(2, '0') +
    'Z'
  );
}
