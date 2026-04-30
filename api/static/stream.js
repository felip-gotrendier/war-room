/* stream.js — SSE message streaming for the conversation view.
 *
 * Requires globals defined in the conversation.html scripts block:
 *   CONV_ID  — conversation UUID
 *   thread   — the #message-thread DOM element
 */

const TOOL_LABELS = {
  check_metric:         'Checking metric…',
  get_recent_anomalies: 'Scanning for anomalies…',
  trigger_scan:         'Triggering fresh scan…',
  get_releases:         'Checking releases…',
  get_release:          'Loading release…',
  explain_release:      'Analysing release…',
};

const SOURCE_STYLES = {
  pulse: {
    dot:   'bg-teal-400',
    ring:  'border-teal-200/70 dark:border-teal-700/40',
    text:  'text-teal-600 dark:text-teal-400',
    label: 'pulse',
  },
  release_agent: {
    dot:   'bg-blue-400',
    ring:  'border-blue-200/70 dark:border-blue-700/40',
    text:  'text-blue-600 dark:text-blue-400',
    label: 'release',
  },
};
const _DEFAULT_STYLE = {
  dot:   'bg-zinc-400',
  ring:  'border-zinc-200/60 dark:border-zinc-700/30',
  text:  'text-zinc-500 dark:text-zinc-500',
  label: 'tool',
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

/* ── Sparkline SVG ───────────────────────────────────────────── */

function renderSparkline(values) {
  if (!values || values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const W = 48, H = 12;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * W;
    const y = H - ((v - min) / range) * (H - 2) - 1;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('width', W);
  svg.setAttribute('height', H);
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
  poly.setAttribute('points', pts);
  poly.setAttribute('fill', 'none');
  poly.setAttribute('stroke', 'currentColor');
  poly.setAttribute('stroke-width', '1.5');
  poly.setAttribute('stroke-linejoin', 'round');
  poly.setAttribute('stroke-linecap', 'round');
  svg.appendChild(poly);
  return svg;
}

/* ── Tool input summary ──────────────────────────────────────── */

function toolInputSummary(tool, input) {
  if (!input) return '';
  switch (tool) {
    case 'check_metric':         return input.metric_name || '';
    case 'get_recent_anomalies': return `last ${input.days || 7}d`;
    case 'get_releases':         return input.repo || '';
    case 'get_release':
    case 'explain_release':      return input.repo ? `${input.repo}/${input.id || ''}` : '';
    default:                     return '';
  }
}

/* ── Tool progress cards ─────────────────────────────────────── */

const _activeBadges = {};

function showToolBadge(tool, input) {
  const summary = toolInputSummary(tool, input);

  const wrapper = document.createElement('div');
  wrapper.className = 'flex justify-start';

  const card = document.createElement('div');
  card.className = [
    'inline-flex flex-col gap-0.5 px-3 py-1.5 rounded-lg text-xs border max-w-xs',
    'bg-zinc-50 border-zinc-200/60 text-zinc-500',
    'dark:bg-zinc-800/40 dark:border-zinc-700/30 dark:text-zinc-500',
  ].join(' ');

  const row = document.createElement('div');
  row.className = 'flex items-center gap-2';

  const dot = document.createElement('span');
  dot.setAttribute('data-role', 'tool-dot');
  dot.className = 'w-1.5 h-1.5 rounded-full bg-zinc-400 animate-pulse flex-shrink-0';

  const label = document.createElement('span');
  label.setAttribute('data-role', 'tool-label');
  label.className = 'font-medium';
  label.textContent = TOOL_LABELS[tool] || `${tool}…`;

  row.appendChild(dot);
  row.appendChild(label);

  if (summary) {
    const sep = document.createElement('span');
    sep.textContent = '·';
    sep.className = 'text-zinc-300 dark:text-zinc-700 select-none';
    const meta = document.createElement('span');
    meta.className = 'font-mono truncate max-w-[140px]';
    meta.textContent = summary;
    row.appendChild(sep);
    row.appendChild(meta);
  }

  const sparklineSlot = document.createElement('span');
  sparklineSlot.setAttribute('data-role', 'tool-sparkline');
  row.appendChild(sparklineSlot);

  const gapRow = document.createElement('div');
  gapRow.setAttribute('data-role', 'tool-gap');
  gapRow.className = 'hidden pl-3.5 truncate text-amber-600 dark:text-amber-400';

  card.appendChild(row);
  card.appendChild(gapRow);
  wrapper.appendChild(card);
  thread.appendChild(wrapper);
  thread.scrollTop = thread.scrollHeight;

  _activeBadges[tool] = wrapper;
}

function completeToolBadge(tool, data) {
  const wrapper = _activeBadges[tool];
  if (!wrapper) return;
  delete _activeBadges[tool];

  const card = wrapper.firstElementChild;
  const dot = card.querySelector('[data-role="tool-dot"]');
  const label = card.querySelector('[data-role="tool-label"]');
  const sparklineSlot = card.querySelector('[data-role="tool-sparkline"]');
  const gapRow = card.querySelector('[data-role="tool-gap"]');

  const source = data && data.source;
  const coverage = (data && data.coverage) || { is_complete: true, gaps: [] };
  const uiData = (data && data.ui_data) || {};
  const hasGap = !coverage.is_complete && coverage.gaps && coverage.gaps.length > 0;
  const style = SOURCE_STYLES[source] || _DEFAULT_STYLE;

  if (dot) {
    dot.className = `w-1.5 h-1.5 rounded-full flex-shrink-0 ${hasGap ? 'bg-amber-400' : 'bg-emerald-400'}`;
  }

  if (label && source) {
    label.textContent = style.label;
    label.className = `font-medium ${style.text}`;
  }

  if (sparklineSlot && uiData.sparkline && uiData.sparkline.length >= 2) {
    const svg = renderSparkline(uiData.sparkline);
    if (svg) {
      svg.className = `flex-shrink-0 opacity-60 ${style.text}`;
      sparklineSlot.appendChild(svg);
    }
  }

  if (gapRow && hasGap) {
    gapRow.textContent = `⚠ ${coverage.gaps[0]}`;
    gapRow.classList.remove('hidden');
  }

  if (source && SOURCE_STYLES[source]) {
    card.className = card.className
      .replace('border-zinc-200/60 dark:border-zinc-700/30', style.ring);
  }

  thread.scrollTop = thread.scrollHeight;
}

/* ── SSE event handler ───────────────────────────────────────── */

function handleSseEvent(type, data) {
  switch (type) {
    case 'tool_start':
      showToolBadge(data.tool, data.input);
      break;
    case 'tool_complete':
      completeToolBadge(data.tool, data);
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
        const headerTitle = document.querySelector('[data-role="conv-header-title"]');
        if (headerTitle) headerTitle.textContent = data.title;
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
