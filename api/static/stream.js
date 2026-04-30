/* stream.js — SSE message streaming for the conversation view.
 *
 * Requires globals defined in the conversation.html scripts block:
 *   CONV_ID  — conversation UUID
 *   thread   — the #message-thread DOM element
 */

const TOOL_LABELS = {
  check_metric:         'Consulting pulse…',
  get_recent_anomalies: 'Scanning for anomalies…',
  trigger_scan:         'Triggering fresh scan…',
  get_releases:         'Checking releases…',
  get_release:          'Loading release…',
  explain_release:      'Analysing release…',
};

/* ── DOM helpers ─────────────────────────────────────────────── */

function escHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function appendMessage(role, text) {
  const isUser = role === 'user';
  const wrapper = document.createElement('div');
  wrapper.className = `flex ${isUser ? 'justify-end' : 'justify-start'}`;

  const bubble = document.createElement('div');
  bubble.className = [
    'max-w-[75%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed',
    isUser
      ? 'bg-violet-100 text-violet-900 rounded-br-sm dark:bg-violet-600/25 dark:text-violet-100'
      : 'bg-zinc-100 text-zinc-800 rounded-bl-sm dark:bg-zinc-800/80 dark:text-zinc-200',
  ].join(' ');

  const p = document.createElement('p');
  p.className = 'whitespace-pre-wrap';
  p.innerHTML = escHtml(text);
  bubble.appendChild(p);
  wrapper.appendChild(bubble);
  thread.appendChild(wrapper);
  thread.scrollTop = thread.scrollHeight;
}

function setInputDisabled(disabled) {
  document.getElementById('message-input').disabled = disabled;
  document.getElementById('send-btn').disabled = disabled;
}

/* ── Tool progress badges ────────────────────────────────────── */

const _activeBadges = {};

function showToolBadge(tool) {
  const wrapper = document.createElement('div');
  wrapper.className = 'flex justify-start';

  const badge = document.createElement('div');
  badge.className = [
    'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs',
    'bg-zinc-100 text-zinc-500 dark:bg-zinc-800/60 dark:text-zinc-500',
  ].join(' ');

  const dot = document.createElement('span');
  dot.className = 'w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse flex-shrink-0';

  const label = document.createElement('span');
  label.textContent = TOOL_LABELS[tool] || tool + '…';

  badge.appendChild(dot);
  badge.appendChild(label);
  wrapper.appendChild(badge);
  thread.appendChild(wrapper);
  thread.scrollTop = thread.scrollHeight;

  _activeBadges[tool] = { wrapper, dot };
}

function completeToolBadge(tool) {
  const entry = _activeBadges[tool];
  if (!entry) return;
  entry.dot.className = entry.dot.className
    .replace('bg-violet-400', 'bg-emerald-400')
    .replace('animate-pulse', '');
  delete _activeBadges[tool];
}

/* ── SSE event handler ───────────────────────────────────────── */

function handleSseEvent(type, data) {
  switch (type) {
    case 'tool_start':
      showToolBadge(data.tool);
      break;
    case 'tool_complete':
      completeToolBadge(data.tool);
      break;
    case 'text':
      appendMessage('assistant', data.text);
      break;
    case 'done':
      if (data.iteration_count >= 15) { window.location.reload(); return; }
      const counter = document.querySelector('[data-role="iter-counter"]');
      if (counter) counter.textContent = `${data.iteration_count} / 15 iterations`;
      if (data.title) {
        const titleEl = document.querySelector(`[data-conv-id="${CONV_ID}"] .conv-title`);
        if (titleEl) titleEl.textContent = data.title;
      }
      break;
    case 'error':
      if (data.code === 'iteration_cap_reached') { window.location.reload(); return; }
      appendMessage('assistant', 'Error: ' + escHtml(data.detail || 'Unknown error'));
      break;
  }
}

/* ── Form submit handler ─────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('send-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = document.getElementById('message-input');
    const message = input.value.trim();
    if (!message) return;

    input.value = '';
    setInputDisabled(true);
    appendMessage('user', message);

    try {
      const resp = await fetch(`/conversations/${CONV_ID}/messages/stream`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ message }),
      });

      if (!resp.ok) {
        if (resp.status === 409) { window.location.reload(); return; }
        const err = await resp.json().catch(() => ({}));
        appendMessage('assistant', 'Error: ' + escHtml(
          err?.detail?.message || err?.detail || 'Request failed'
        ));
        return;
      }

      /* Parse the SSE stream line by line */
      const reader  = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentEvent = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep any incomplete trailing line

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            let data;
            try { data = JSON.parse(line.slice(6)); } catch { continue; }
            handleSseEvent(currentEvent, data);
            currentEvent = null;
          }
        }
      }
    } catch {
      appendMessage('assistant', 'Connection error — please try again.');
    } finally {
      setInputDisabled(false);
      document.getElementById('message-input').focus();
    }
  });
});
