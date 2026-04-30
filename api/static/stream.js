/* stream.js — SSE message streaming for the conversation view.
 *
 * Requires globals defined in the conversation.html scripts block:
 *   CONV_ID  — conversation UUID
 *   thread   — the #message-thread DOM element
 *
 * Optional global: Chart (Chart.js@4 via CDN). If absent, check_metric
 * cards degrade to compact badges without a chart.
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

// Platform → chart line color.
// TODO: hardcoded for the current GoTrendier platform set. When pulse adds
// new platforms or rita introduces new sources, update this map. A shared
// config (served from the API or embedded at template render) would be more
// maintainable but is premature until the platform list stabilises.
const PLATFORM_COLORS = {
  mx_android: 'rgb(20, 184, 166)',
  mx_ios:     'rgb(59, 130, 246)',
  co_android: 'rgb(168, 85, 247)',
  co_ios:     'rgb(249, 115, 22)',
};
const _COLOR_CYCLE = [
  'rgb(20,184,166)', 'rgb(59,130,246)',
  'rgb(168,85,247)', 'rgb(249,115,22)',
  'rgb(236,72,153)', 'rgb(132,204,22)',
];

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

/* ── Date formatting ────────────────────────────────────────── */

const _MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

// Parse an ISO date string (YYYY-MM-DD) to "Apr 22" without constructing a
// Date object. new Date("2026-04-22") is parsed as UTC midnight and
// toLocaleDateString() would show "Apr 21" in UTC-6 timezones.
function formatIsoDate(isoDate) {
  const p = isoDate.split('-');
  return `${_MONTHS[parseInt(p[1], 10) - 1]} ${parseInt(p[2], 10)}`;
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
    'inline-flex flex-col gap-1.5 px-3 py-2 rounded-lg text-xs border',
    'bg-zinc-50 border-zinc-200/60 text-zinc-500',
    'dark:bg-zinc-800/40 dark:border-zinc-700/30 dark:text-zinc-500',
  ].join(' ');

  // Main row: dot + label + optional metadata
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
    meta.className = 'font-mono truncate max-w-[200px]';
    meta.textContent = summary;
    row.appendChild(sep);
    row.appendChild(meta);
  }

  // Chart container — separate block below main row, hidden until tool_complete
  const chartContainer = document.createElement('div');
  chartContainer.setAttribute('data-role', 'tool-chart');
  chartContainer.className = 'hidden';
  chartContainer.style.height = '200px';
  chartContainer.style.position = 'relative'; // required by Chart.js responsive mode

  // Gap row — hidden until tool_complete with coverage gap
  const gapRow = document.createElement('div');
  gapRow.setAttribute('data-role', 'tool-gap');
  gapRow.className = 'hidden pl-3.5 truncate text-amber-600 dark:text-amber-400';

  card.appendChild(row);
  card.appendChild(chartContainer);
  card.appendChild(gapRow);
  wrapper.appendChild(card);
  thread.appendChild(wrapper);
  thread.scrollTop = thread.scrollHeight;

  _activeBadges[tool] = wrapper;
}

/* Apply completion state to a tool card wrapper.
 * Used by both completeToolBadge (live SSE) and the DOMContentLoaded static-card
 * initializer (persisted view) — same code path guarantees coherence by construction.
 * TODO (C5): on dark/light toggle, destroy and recreate Chart instances so grid
 * and tick colors stay in sync with the theme.
 */
function _applyCompletedState(wrapper, tool, source, uiData, coverage) {
  const card = wrapper.firstElementChild;
  const dot = card.querySelector('[data-role="tool-dot"]');
  const label = card.querySelector('[data-role="tool-label"]');
  const chartContainer = card.querySelector('[data-role="tool-chart"]');
  const gapRow = card.querySelector('[data-role="tool-gap"]');

  const hasGap = !coverage.is_complete && coverage.gaps && coverage.gaps.length > 0;
  const style = SOURCE_STYLES[source] || _DEFAULT_STYLE;

  if (dot) {
    dot.className = `w-1.5 h-1.5 rounded-full flex-shrink-0 ${hasGap ? 'bg-amber-400' : 'bg-emerald-400'}`;
  }

  if (label && source) {
    label.textContent = style.label;
    label.className = `font-medium ${style.text}`;
  }

  // Chart for check_metric — only if platforms data is present and Chart.js loaded.
  // If Chart is undefined (CDN unreachable): chartContainer stays hidden,
  // card remains compact — no JS error, no empty whitespace.
  const platforms = uiData && uiData.platforms;
  if (chartContainer && platforms && platforms.length > 0 && typeof Chart !== 'undefined') {
    card.style.width = '420px';
    chartContainer.classList.remove('hidden');

    const canvas = document.createElement('canvas');
    chartContainer.appendChild(canvas);

    const isDark = document.documentElement.classList.contains('dark');
    const gridColor = isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.07)';
    const tickColor = isDark ? 'rgba(255,255,255,0.40)' : 'rgba(0,0,0,0.40)';

    const labels = (platforms[0].series || []).map(s => formatIsoDate(s.date));

    const datasets = platforms.map((p, i) => {
      const color = PLATFORM_COLORS[p.platform] || _COLOR_CYCLE[i % _COLOR_CYCLE.length];
      return {
        label: p.platform,
        data: (p.series || []).map(s => s.value),
        borderColor: color,
        backgroundColor: 'transparent',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
      };
    });

    new Chart(canvas, {
      type: 'line',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
          x: {
            grid:  { color: gridColor },
            ticks: { color: tickColor, maxTicksLimit: 7, font: { size: 10 } },
          },
          y: {
            grid:  { color: gridColor },
            ticks: { color: tickColor, maxTicksLimit: 5, font: { size: 10 } },
          },
        },
        plugins: {
          legend: {
            position: 'bottom',
            labels: { color: tickColor, boxWidth: 10, padding: 8, font: { size: 10 } },
          },
          tooltip: { mode: 'index', intersect: false },
        },
      },
    });
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

function completeToolBadge(tool, data) {
  const wrapper = _activeBadges[tool];
  if (!wrapper) return;
  delete _activeBadges[tool];

  const source = data && data.source;
  const coverage = (data && data.coverage) || { is_complete: true, gaps: [] };
  const uiData = (data && data.ui_data) || {};

  _applyCompletedState(wrapper, tool, source, uiData, coverage);
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
  /* Initialise persisted tool cards rendered by the server on page load. */
  document.querySelectorAll('[data-role="static-tool-card"]').forEach(wrapper => {
    const tool = wrapper.dataset.tool;
    const source = wrapper.dataset.source;
    let uiData = {}, coverage = { is_complete: true, gaps: [] };
    try { uiData = JSON.parse(wrapper.dataset.uiData || '{}'); } catch {}
    try { coverage = JSON.parse(wrapper.dataset.coverage || '{}'); } catch {}
    _applyCompletedState(wrapper, tool, source, uiData, coverage);
  });

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
