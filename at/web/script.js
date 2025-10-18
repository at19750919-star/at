const API_BASE = window.location.origin;

const STATE = {
  rounds: [],
  suitCounts: {},
  previewCards: [],
  cutSummary: null,
};

const SUIT_SYMBOL_TO_LETTER = {
  '\u2660': 'S',
  '\u2665': 'H',
  '\u2666': 'D',
  '\u2663': 'C',
};

const SIGNAL_SUIT_COLOR = {
  H: '#ff7a90',
  S: '#69c0ff',
  D: '#ffb74d',
  C: '#73d13d',
};

const SUIT_DISPLAY_NAME = {
  S: '\u9ed1\u6843',
  H: '\u7d05\u5fc3',
  D: '\u65b9\u584a',
  C: '\u6885\u82b1',
};

const $ = (id) => document.getElementById(id);

function toast(message) {
  const node = $('toast');
  if (!node) return;
  node.textContent = message;
  node.style.display = 'block';
  setTimeout(() => {
    node.style.display = 'none';
  }, 2200);
}

function csvDownloadHref(name) {
  return `${API_BASE}/api/export/${name}`;
}

function suitLetterFromLabel(label) {
  if (!label) return '';
  const value = String(label).trim();
  if (!value) return '';
  const symbol = value.slice(-1);
  if (SUIT_SYMBOL_TO_LETTER[symbol]) return SUIT_SYMBOL_TO_LETTER[symbol];
  const upper = symbol.toUpperCase();
  if (SUIT_SYMBOL_TO_LETTER[upper]) return SUIT_SYMBOL_TO_LETTER[upper];
  return upper;
}

function cardSuitFromCard(card) {
  if (!card) return '';
  if (typeof card === 'object') {
    if (card.suit) return card.suit;
    if (card.suit_symbol) return suitLetterFromLabel(card.suit_symbol);
    if (card.label) return suitLetterFromLabel(card.label);
  }
  return suitLetterFromLabel(card);
}

function cardLabel(card) {
  if (!card) return '';
  if (typeof card === 'object') {
    if (card.label) return card.label;
    if (card.short) return typeof card.short === 'function' ? card.short() : card.short;
  }
  return String(card);
}

function rankFromLabel(label) {
  if (!label) return '';
  const text = String(label).trim();
  if (!text) return '';
  const cleaned = text.replace(/[\u2660\u2665\u2666\u2663shdc]/gi, '');
  return cleaned.toUpperCase();
}

function gridValueFromLabel(label) {
  const rank = rankFromLabel(label);
  if (!rank) return '';
  if (rank === 'A') return '1';
  if (rank === 'T' || rank === '10' || rank === 'J' || rank === 'Q' || rank === 'K') return '0';
  const num = Number.parseInt(rank, 10);
  if (!Number.isNaN(num)) return String(num % 10);
  return rank;
}

function renderSuits(counts) {
  const container = $('suits');
  if (!container) return;
  if (!counts || !Object.keys(counts).length) {
    container.innerHTML = '<div class="small">\u5c1a\u7121\u8cc7\u6599</div>';
    renderCutSummary(null);
    return;
  }
  container.innerHTML = Object.entries(counts)
    .map(
      ([key, value]) => {
        const suitKey = String(key || '').toUpperCase();
        const display = SUIT_DISPLAY_NAME[suitKey] || suitKey || key;
        return `
        <div class="stat stat-${suitKey}">
          <div class="stat-label">${display}</div>
          <div class="stat-value">${value}</div>
        </div>
      `;
      },
    )
    .join('');
  renderCutSummary(STATE.cutSummary);
}

function renderCutSummary(summary) {
  const container = $('cutSummary');
  if (!container) return;
  if (!summary) {
    container.innerHTML = '';
    return;
  }
  const hitValue = typeof summary.avg_hit === 'number' ? summary.avg_hit.toFixed(3) : summary.avg_hit;
  const roundValue = typeof summary.avg_rounds === 'number' ? summary.avg_rounds.toFixed(3) : summary.avg_rounds;
  container.innerHTML = `
    <div class="small">\u5e73\u5747\u547d\u4e2d\u5f35\u6578\uff1a<span class="mono">${hitValue}</span></div>
    <div class="small">\u5e73\u5747\u6d88\u8017\u5c40\u6578\uff1a<span class="mono">${roundValue}</span></div>
  `;
}

function ensureRoundsHeader() {
  const headers = ['\u5c40\u865f', '1', '2', '3', '4', '5', '6', 'S_idx', '\u52dd\u65b9', '\u9592\u5bb6\u724c', '\u838a\u5bb6\u724c', '\u9592\u5bb6\u9ede\u6578', '\u838a\u5bb6\u9ede\u6578', '\u984f\u8272\u5e8f\u5217'];
  $('thead').innerHTML = `<tr>${headers.map((h) => `<th>${h}</th>`).join('')}</tr>`;
}

function renderRounds(rounds) {
  const tbody = $('tbody');
  if (!tbody) return;
  if (!rounds || !rounds.length) {
    tbody.innerHTML = '';
    return;
  }
  ensureRoundsHeader();
  const signal = $('signalSuit').value;
  const tieSet = new Set(['Tie', 'T', '\u548c']);
  const rowsHtml = rounds
    .map((round, index) => {
      const cards = round.cards || [];
      const result = round.result || round.winner || '';
      const winnerClass =
        result === 'Banker' || result === '\u838a' || result === 'B'
          ? 'win-bank'
          : result === 'Player' || result === '\u9592' || result === 'P'
            ? 'win-player'
            : result === 'Tie' || result === '\u548c' || result === 'T'
              ? 'win-tie'
              : '';
      const isTie = tieSet.has(result);
      const cardCells = [];
      for (let i = 0; i < 6; i += 1) {
        const card = cards[i];
        const label = cardLabel(card);
        const suit = cardSuitFromCard(card);
        let classes = 'mono';
        let inline = '';
        if (signal && !isTie && suit === signal) {
          classes += ` signal-card signal-card-${signal}`;
          const color = SIGNAL_SUIT_COLOR[signal];
          if (color) inline = ` style="color:${color}"`;
        }
        cardCells.push(`<td class="${classes}"${inline}>${label}</td>`);
      }
      const playerCards = (round.player || round.player_cards || []).join('/') || '';
      const bankerCards = (round.banker || round.banker_cards || []).join('/') || '';
      const colorSeq = round.color_seq || round.colors || '';
      const colorHtml = colorSeq
        ? colorSeq
            .split('')
            .map((ch) => {
              if (ch === 'R') return '<span class="color-r">R</span>';
              if (ch === 'B') return '<span class="color-b">B</span>';
              return `<span>${ch}</span>`;
            })
            .join('')
        : '';
      const isSIdx = Boolean(round.is_sidx);
      const sIdxOk = Boolean(round.s_idx_ok);
      const sIdxText = isSIdx ? (sIdxOk ? '\u2665' : '\u2716') : '';
      const sIdxClass = isSIdx ? (sIdxOk ? 'sidx-ok' : 'sidx-bad') : '';
      const indexLabel = round.is_tail ? '\u5c3e\u5c40' : index + 1;
      const rowClass = round.is_tail ? 'tail-row' : '';
      return `
        <tr class="${rowClass}">
          <td>${indexLabel}</td>
          ${cardCells.join('')}
          <td class="mono ${sIdxClass}">${sIdxText}</td>
          <td class="${winnerClass}">${result}</td>
          <td class="mono">${playerCards}</td>
          <td class="mono">${bankerCards}</td>
          <td>${round.player_point ?? ''}</td>
          <td>${round.banker_point ?? ''}</td>
          <td class="mono color-seq">${colorHtml}</td>
        </tr>
      `;
    })
    .join('');
  tbody.innerHTML = rowsHtml;
}

function sortedRoundsByStartIndex(rounds) {
  if (!Array.isArray(rounds)) return [];
  return rounds
    .map((round, idx) => ({
      round,
      idx,
      start:
        round && typeof round.start_index === 'number'
          ? round.start_index
          : null,
    }))
    .sort((a, b) => {
      const aHasStart = typeof a.start === 'number';
      const bHasStart = typeof b.start === 'number';
      if (aHasStart && bHasStart) return a.start - b.start;
      if (aHasStart) return -1;
      if (bHasStart) return 1;
      return a.idx - b.idx;
    })
    .map((item) => item.round);
}

function flattenRoundColorSequence(rounds) {
  const sorted = sortedRoundsByStartIndex(rounds);
  if (!sorted.length) return '';
  return sorted
    .map((round) => {
      const seq = round?.color_seq ?? round?.colors ?? '';
      if (Array.isArray(seq)) return seq.join('');
      if (typeof seq === 'string') return seq.replace(/\s+/g, '');
      return '';
    })
    .join('');
}

function buildDeckGrid(cards, signal, rounds = STATE.rounds) {
  const columns = 16;
  const rows = 26;
  const grid = [];
  const colorSequence = Array.isArray(rounds) && rounds.length ? flattenRoundColorSequence(rounds) : '';
  for (let r = 0; r < rows; r += 1) {
    const row = [];
    for (let c = 0; c < columns; c += 1) {
      const idx = r * columns + c;
      const raw = idx < cards.length ? cards[idx] : '';
      const originalLabel = cardLabel(raw);
      if (!originalLabel) {
        row.push({ label: '', className: '', title: '' });
        continue;
      }
      const displayLabel = gridValueFromLabel(originalLabel);
      const suit = suitLetterFromLabel(originalLabel);
      const suitDisplay = suit ? SUIT_DISPLAY_NAME[suit] || suit : '';
      const isSignal = signal && suit === signal;
      const colorChar = colorSequence.charAt(idx).toUpperCase();
      const classes = [];
      if (colorChar === 'R') classes.push('card-red');
      else if (colorChar === 'B') classes.push('card-blue');
      if (isSignal) classes.push('signal-match');
      const className = classes.join(' ');
      row.push({
        label: displayLabel,
        className,
        title: suitDisplay ? `${originalLabel} (${suitDisplay})` : originalLabel,
      });
    }
    grid.push(row);
  }
  return grid;
}

function renderPreview(cards) {
  const container = $('gridPreview');
  if (!container) return;
  if (!cards || !cards.length) {
    container.innerHTML = '<div class="small">\u5c1a\u7121\u724c\u9774\u8cc7\u6599</div>';
    return;
  }
  const signal = $('signalSuit').value;
  const grid = buildDeckGrid(cards, signal, STATE.rounds);
  container.innerHTML = grid
    .map((row) =>
      row
        .map((cell) => {
          const title = cell.title ? ` title="${cell.title}"` : '';
          return `<div class="cell ${cell.className}"${title}>${cell.label}</div>`;
        })
        .join(''),
    )
    .join('');
}

function openPreviewWindow(immediatePrint = false) {
  if (!STATE.previewCards.length) {
    toast('\u5c1a\u672a\u7522\u751f\u724c\u9774');
    return;
  }
  const signal = $('signalSuit').value;
  const grid = buildDeckGrid(STATE.previewCards, signal, STATE.rounds);
  const gridHtml = grid
    .map((row) =>
      row
        .map((cell) => {
          const title = cell.title ? ` title="${cell.title}"` : '';
          return `<div class="cell ${cell.className}"${title}>${cell.label}</div>`;
        })
        .join(''),
    )
    .join('');
  const html = `<!doctype html>
<html lang="zh-Hant">
  <head>
    <meta charset="utf-8" />
    <title>\u724c\u9774\u9810\u89bd</title>
    <style>
      /* === 基本版面設定（整體背景、字體大小）=== */
      body{margin:0;padding:24px;background:#0f111a;color:#eef3ff;font:14px/1.4 "Noto Sans TC",sans-serif;}
      body,table.deck td{-webkit-print-color-adjust:exact;print-color-adjust:exact;}
      /* === 操作按鈕列（可視需要保留或移除）=== */
      .actions{margin-bottom:12px;display:flex;gap:8px;}
      .actions button{padding:6px 12px;border:1px solid #24324a;border-radius:6px;background:#1d4ed8;color:#f3f8ff;cursor:pointer;}
      /* === 表格外觀（外框、間距、字體大小）=== */
      .deck-wrapper{display:inline-block;border:1px solid #394968;background:#121b2c;padding:8px;border-radius:8px;}
      table.deck{border-collapse:collapse;}
      table.deck td{width:38px;height:24px;text-align:center;font-weight:600;border:1px solid #2a3650;color:#d8e6ff;font-size:14px;padding:2px;}
      /* === 顏色設定（可自行調整）=== */
      table.deck td.card-red{background:#2d1b22;color:#ffd6dc;}
      table.deck td.card-blue{background:#162437;color:#d7e9ff;}
      table.deck td.signal-match{box-shadow:inset 0 0 0 2px #ffd591;}
      /* === 列印模式專用樣式 === */
      @media print{
        body{padding:8px;background:#fff;color:#000;}
        .actions{display:none !important;}
        .deck-wrapper{border:1px solid #666;background:#fff;padding:0;border-radius:0;}
        table.deck td{border:1px solid #888;color:#111;font-size:12px;padding:1px;}
        table.deck td.card-red{background:#ff4d4f !important;color:#fff !important;}
        table.deck td.card-blue{background:#2f54eb !important;color:#fff !important;}
        table.deck td.signal-match{box-shadow:inset 0 0 0 2px #faad14 !important;}
      }
    </style>
  </head>
  <body>
    <div class="actions">
      <button onclick="window.print()">\u5217\u5370</button>
      <button onclick="window.close()">\u95dc\u9589</button>
    </div>
    <div class="deck-wrapper">
      <table class="deck">
        <tbody>
          ${grid
            .map(
              (row) =>
                `<tr>${row
                  .map((cell) => `<td class="${cell.className}">${cell.label}</td>`)
                  .join('')}</tr>`,
            )
            .join('')}
        </tbody>
      </table>
    </div>
  </body>
</html>`;
  const blob = new Blob([html], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const win = window.open(url, '_blank');
  if (!win) {
    toast('\u700f\u89bd\u5668\u963b\u64cb\u5f48\u51fa\u8996\u7a97\uff0c\u8acb\u5141\u8a31\u5f8c\u518d\u8a66');
    URL.revokeObjectURL(url);
    return;
  }
  win.focus();
  win.onload = () => {
    if (immediatePrint) {
      try {
        win.print();
      } catch (err) {
        console.warn('preview print failed', err);
      }
    }
  };
  const revokeLater = () => {
    try {
      URL.revokeObjectURL(url);
    } catch (err) {
      // ignore
    }
  };
  win.addEventListener('beforeunload', revokeLater);
  setTimeout(revokeLater, 60000);
  if (immediatePrint) {
    setTimeout(() => {
      try {
        win.print();
      } catch (err) {
        console.warn('preview print failed', err);
      }
    }, 300);
  }
}

function splitCutRows(hitRows) {
  const header1 = hitRows[0] || [];
  const header2 = hitRows[1] || [];
  const rawRows = hitRows.slice(2);
  const dataRows = [];
  const averages = [];
  for (const row of rawRows) {
    if (!row) continue;
    const hasData = row.some((cell) => String(cell || '').trim().length);
    if (!hasData) continue;
    if (row[0] === '\u5e73\u5747' || row[0] === 'Average') {
      averages.push(row);
      continue;
    }
    dataRows.push(row);
  }
  return { header1, header2, dataRows, averages };
}

async function refreshCutSummary() {
  try {
    const hitsCsv = await fetchText(csvDownloadHref('cut_hits.csv'));
    const { averages } = splitCutRows(parseCSV(hitsCsv));
    if (averages.length) {
      const last = averages[averages.length - 1];
      const avgHit = parseFloat(last[1]) || 0;
      const avgRounds = parseFloat(last[last.length - 1]) || 0;
      STATE.cutSummary = { avg_hit: avgHit, avg_rounds: avgRounds };
      renderCutSummary(STATE.cutSummary);
    } else {
      STATE.cutSummary = null;
      renderCutSummary(null);
    }
  } catch (err) {
    console.warn('refreshCutSummary failed', err);
    STATE.cutSummary = null;
    renderCutSummary(null);
  }
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function fetchText(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.text();
}

function downloadFile(name, content, type = 'text/csv') {
  const blob = new Blob([content], { type });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

function csvEscape(value) {
  if (value == null) return '';
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function normalizeLines(text) {
  return text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
}

function parseCSV(text) {
  const source = normalizeLines(text);
  const out = [];
  let row = [];
  let field = '';
  let inQuote = false;
  for (let i = 0; i < source.length; i += 1) {
    const ch = source[i];
    if (inQuote) {
      if (ch === '"') {
        if (source[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          inQuote = false;
        }
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      inQuote = true;
    } else if (ch === ',') {
      row.push(field);
      field = '';
    } else if (ch === '\n') {
      row.push(field);
      out.push(row);
      row = [];
      field = '';
    } else {
      field += ch;
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    out.push(row);
  }
  return out;
}

function linesFromCSVorTxt(text) {
  return normalizeLines(text).trim().split('\n').filter(Boolean);
}

function applyGenerateResponse(data) {
  STATE.rounds = data.rounds || [];
  STATE.suitCounts = data.suit_counts || {};
  const vertical = data.vertical || '';
  STATE.previewCards = vertical.split('\n').filter(Boolean);
  STATE.cutSummary = null;

  renderSuits(STATE.suitCounts);
  renderRounds(STATE.rounds);
  renderPreview(STATE.previewCards);
  renderCutSummary(null);
  refreshCutSummary();

  const tables = $('tables');
  if (tables) tables.style.display = 'grid';
}

async function generateShoe() {
  const btn = $('btnGen');
  const spinner = $('spinGen');
  if (btn) btn.disabled = true;
  if (spinner) spinner.style.display = 'inline-block';
  try {
    const payload = {
      num_shoes: Number($('numShoes').value),
      signal_suit: $('signalSuit').value,
      tie_signal_suit: $('tieSuit').value || null,
    };
    const data = await fetchJson(`${API_BASE}/api/generate_shoe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (data.error) {
      toast(`\u5275\u5efa\u5931\u6557\uff1a${data.detail || data.error}`);
      return;
    }
    applyGenerateResponse(data);
    const count = (data.rounds || []).length;
    const fb = data.meta && data.meta.fallback ? `\uff08fallback: ${data.meta.fallback}\uff09` : '';
    toast(`\u724c\u9774\u5df2\u5b8c\u6210\uff0c\u5171 ${count} \u5c40${fb}`);
  } catch (err) {
    console.error(err);
    toast('\u5275\u5efa\u6642\u767c\u751f\u932f\u8aa4');
  } finally {
    if (btn) btn.disabled = false;
    if (spinner) spinner.style.display = 'none';
  }
}

async function simulateCut() {
  if (!STATE.rounds.length) {
    toast('\u8acb\u5148\u7522\u751f\u724c\u9774');
    return;
  }
  const btn = $('btnCut');
  const spinner = $('spinCut');
  if (btn) btn.disabled = true;
  if (spinner) spinner.style.display = 'inline-block';
  try {
    const payload = { cut_pos: Number($('cutPos').value) };
    const data = await fetchJson(`${API_BASE}/api/simulate_cut`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (data.error) {
      toast(`\u5207\u9774\u5931\u6557\uff1a${data.error}`);
      return;
    }
    STATE.rounds = data.rounds || [];
    STATE.suitCounts = data.suit_counts || {};
    STATE.cutSummary = null;
    renderRounds(STATE.rounds);
    renderSuits(STATE.suitCounts);
    renderCutSummary(null);
    await refreshCutSummary();
    toast('\u5207\u9774\u5b8c\u6210');
  } catch (err) {
    console.error(err);
    toast('\u5207\u9774\u6642\u767c\u751f\u932f\u8aa4');
  } finally {
    if (btn) btn.disabled = false;
    if (spinner) spinner.style.display = 'none';
  }
}

async function scanRounds() {
  if (!STATE.rounds.length) {
    toast('\u8acb\u5148\u7522\u751f\u724c\u9774');
    return;
  }
  try {
    const payload = {
      banker_point: Number($('bankerPoint').value),
      player_point: Number($('playerPoint').value),
      used_cards: Number($('usedCards').value),
    };
    const data = await fetchJson(`${API_BASE}/api/scan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    $('scanInfo').textContent = `\u547d\u4e2d ${data.count || 0} \u5c40`;
  } catch (err) {
    console.error(err);
    toast('\u6383\u63cf\u6642\u767c\u751f\u932f\u8aa4');
  }
}

async function exportCombined() {
  try {
    const [verticalTxt, hitsCsv] = await Promise.all([
      fetchText(csvDownloadHref('vertical')),
      fetchText(csvDownloadHref('cut_hits.csv')),
    ]);
    const vertical = linesFromCSVorTxt(verticalTxt);
    const hitRows = parseCSV(hitsCsv);
    const { header1, header2, dataRows, averages } = splitCutRows(hitRows);
    if (dataRows.length !== vertical.length) {
      toast(`\u884c\u6578\u4e0d\u4e00\u81f4\uff1a\u7d71\u8a08 ${dataRows.length} vs \u724c\u9774 ${vertical.length}`);
      return;
    }
    if (header2.length) {
      header2.push('\u539f\u59cb\u724c\u5e8f');
      header1.push('');
    }
    const merged = [
      header1,
      header2,
      ...dataRows.map((row, idx) => [...row, vertical[idx]]),
    ];
    const csv = merged.map((cols) => cols.map((cell) => csvEscape(cell)).join(',')).join('\r\n');
    downloadFile('combined_hits_vertical.csv', csv);
    STATE.cutSummary = null;
    renderCutSummary(null);
    if (averages.length) {
      const last = averages[averages.length - 1];
      const avgHit = parseFloat(last[1]) || 0;
      const avgRounds = parseFloat(last[last.length - 1]) || 0;
      STATE.cutSummary = { avg_hit: avgHit, avg_rounds: avgRounds };
      renderCutSummary(STATE.cutSummary);
    }
    toast('\u5df2\u4e0b\u8f09\u532f\u51fa\u6a94');
  } catch (err) {
    console.error(err);
    toast('\u532f\u51fa\u5931\u6557');
  }
}

function bindControls() {
  renderSuits({});
  renderCutSummary(null);
  renderPreview([]);

  const btnGen = $('btnGen');
  if (btnGen) btnGen.addEventListener('click', generateShoe);

  const btnCut = $('btnCut');
  if (btnCut) btnCut.addEventListener('click', simulateCut);

  const btnScan = $('btnScan');
  if (btnScan) btnScan.addEventListener('click', scanRounds);

  const btnExport = $('btnExportCombined');
  if (btnExport) btnExport.addEventListener('click', exportCombined);

  const btnPreview = $('btnPreview');
  if (btnPreview) btnPreview.addEventListener('click', () => openPreviewWindow(false));

  const btnPrint = $('btnPrint');
  if (btnPrint) btnPrint.addEventListener('click', () => openPreviewWindow(true));

  const signalSelect = $('signalSuit');
  if (signalSelect) {
    signalSelect.addEventListener('change', () => {
      renderRounds(STATE.rounds);
      renderPreview(STATE.previewCards);
    });
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bindControls);
} else {
  bindControls();
}
