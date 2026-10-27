(() => {
  'use strict';
  const $ = (s) => document.querySelector(s);
  const state = { data: null, range: 7, metric: 'steps', loading: false };
  const labels = { steps: '步数', active_kcal: '活动能量', heart_rate_avg_bpm: '心率记录均值', resting_bpm: '静息心率', weight_kg: '体重', sleep_minutes: '睡眠' };
  const units = { steps: '步', active_kcal: 'kcal', heart_rate_avg_bpm: 'bpm', resting_bpm: 'bpm', weight_kg: 'kg', sleep_minutes: '分钟' };
  const local = ['localhost', '127.0.0.1', '::1'].includes(location.hostname);
  const demo = new URLSearchParams(location.search).get('demo') === '1' || !local;
  const num = (v) => typeof v === 'number' && Number.isFinite(v) ? v : null;
  const fmt = (v, digits = 0) => num(v) === null ? '—' : Number(v).toLocaleString('zh-CN', { maximumFractionDigits: digits });
  const sleep = (value) => { if (num(value) === null) return '—'; const total = Math.round(value), hours = Math.floor(total / 60), minutes = total % 60; return hours ? hours + '小时' + (minutes ? ' ' + minutes + '分' : '') : minutes + '分钟'; };
  const sleepClock = (value) => Math.floor(Math.round(value) / 60) + ':' + String(Math.round(value) % 60).padStart(2, '0');
  const date = (s) => { if (!s) return '—'; const d = new Date(`${s}T00:00:00`); return Number.isNaN(d.getTime()) ? s : d.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' }); };
  const text = (el, value) => { if (el) el.textContent = value == null ? '' : String(value); };
  function setStatus(kind, title, message) { $('#statusDot').className = `status-dot ${kind || ''}`; text($('#statusTitle'), title); text($('#statusText'), message); }
  function sourceStatus(data) {
    const s = data.source || {}; text($('#sourceLabel'), s.label || (demo ? '合成演示数据' : '本机 iCloud'));
    text($('#latestExport'), s.latest_export ? new Date(s.latest_export).toLocaleString('zh-CN', {timeZone: s.timezone || 'Asia/Shanghai', hour12: false}) : '暂无文件记录');
    text($('#fileStatus'), `${fmt(s.files_read)} 个文件，跳过 ${fmt(s.files_skipped)} 个；去重 ${fmt(data.counts?.duplicate_samples)} 条样本`);
    const existing = $('#fileStatus').parentElement; existing.querySelectorAll('.paths').forEach((node) => node.remove()); const paths = document.createElement('div'); paths.className = 'paths'; const pathLabel = document.createElement('span'); pathLabel.className = 'detail-label'; pathLabel.textContent = '读取路径'; paths.append(pathLabel); const pathText = document.createElement('p'); const dirs = demo ? [] : (Array.isArray(s.directories) ? s.directories : []); pathText.textContent = dirs.length ? dirs.join('；') : (demo ? '（合成演示数据，无本机路径）' : '暂无路径；请确认本机服务已读取目录'); paths.append(pathText); existing.append(paths);
    const warning = Array.isArray(s.warnings) ? s.warnings.filter(Boolean) : [];
    const box = $('#warnings'); box.hidden = warning.length === 0; box.textContent = warning.join('；');
  }
  function latestFor(days, key) { return [...days].reverse().find((d) => num(d[key]) !== null) || null; }
  function renderSummary() {
    const days = state.data?.days || [];
    const keys = [['metricSteps','steps'],['metricEnergy','active_kcal'],
      ['metricResting','resting_bpm'],['metricHeart','heart_rate_avg_bpm'],
      ['metricSleep','sleep_minutes'],['metricWeight','weight_kg']];
    keys.forEach(([id, key]) => {
      const row = latestFor(days, key), element = $('#' + id);
      text(element, row ? (key === 'sleep_minutes' ? sleepClock(row[key]) :
        fmt(row[key], key === 'weight_kg' ? 1 : 0)) : '—');
      let stamp = element.parentElement.querySelector('.metric-date');
      if (!stamp) {
        stamp = document.createElement('span');
        stamp.className = 'metric-date';
        element.parentElement.append(stamp);
      }
      stamp.textContent = row ? date(row.date) +
        (key === 'sleep_minutes' ? ' 醒来' : '') + ((row.partial_metrics || []).includes(key) ? ' · 部分记录' : '') : '暂无记录';
    });
    text($('#summaryDate'), '每项标注自己的记录日期');
  }
  function svgEl(name, attrs) { const e = document.createElementNS('http://www.w3.org/2000/svg', name); Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, String(v))); return e; }
  function renderChart() {
    if (!state.data) return;
    const all = Array.isArray(state.data.days) ? state.data.days : [];
    const records = new Map(all.map(row => [row.date, row]));
    const lastDate = all.length ? all[all.length - 1].date :
      new Date().toLocaleDateString('sv-SE');
    // Calendar dates are labels, not instants in the browser's timezone.
    const anchor = new Date(lastDate + 'T00:00:00Z');
    const days = Array.from({length: state.range}, (_, index) => {
      const instant = new Date(anchor);
      instant.setUTCDate(anchor.getUTCDate() - state.range + 1 + index);
      const key = instant.toISOString().slice(0, 10);
      return records.get(key) || {date: key};
    });
    const values = days.map(row => num(row[state.metric]));
    const present = values.filter(value => value !== null).length;
    text($('#rangeLabel'), days[0].date + ' 至 ' + days[days.length - 1].date +
      ' · ' + present + '/' + state.range + ' 天有记录');
    const chart = $('#chart');
    chart.replaceChildren();
    const picker = $('#selectedDay');
    picker.replaceChildren();
    days.forEach(row => {
      const option = document.createElement('option');
      option.value = row.date;
      option.textContent = row.date + (num(row[state.metric]) === null ? ' · 无记录' : '');
      picker.append(option);
    });
    const showSelection = row => {
      state.selectedDate = row.date;
      picker.value = row.date;
      const value = num(row[state.metric]);
      const amount = value === null ? '暂无记录' :
        (state.metric === 'sleep_minutes' ? sleep(value) :
          fmt(value, state.metric === 'weight_kg' ? 1 : 0) + ' ' + units[state.metric]);
      const partial = (row.partial_metrics || []).includes(state.metric);
      text($('#chartSelection'), row.date + ' · ' + labels[state.metric] + ' ' + amount +
        (value !== null ? ' · 来源：' + (row.sources?.[state.metric] || '未注明') : '') +
        (partial ? ' · 部分记录' : ''));
    };
    const defaultDay = days.find(row => row.date === state.selectedDate) ||
      [...days].reverse().find(row => num(row[state.metric]) !== null) || days[days.length - 1];
    showSelection(defaultDay);
    picker.onchange = () => showSelection(days.find(row => row.date === picker.value));
    if (!present) {
      const empty = document.createElement('div');
      empty.className = 'empty-chart';
      empty.textContent = '这个范围内还没有可绘制的数据。缺失记录保留为空，不按 0 计算。';
      chart.append(empty);
      text($('#chartSummary'), '当前范围没有可用数据');
      return;
    }
    const width = 760, height = 250, left = 54, right = 20, top = 19, bottom = 34;
    const plotWidth = width - left - right, plotHeight = height - top - bottom;
    const valid = values.filter(value => value !== null);
    const minimum = Math.min(...valid), maximum = Math.max(...valid);
    const padding = maximum - minimum || Math.max(maximum * .08, 1);
    const low = Math.max(0, minimum - padding * .12), high = maximum + padding * .12;
    const x = index => left + index * plotWidth / (days.length - 1);
    const y = value => top + (high - value) * plotHeight / (high - low);
    const svg = svgEl('svg', {viewBox: '0 0 ' + width + ' ' + height,
      role: 'group', 'aria-label': labels[state.metric] + '最近 ' + state.range + ' 天趋势'});
    const title = svgEl('title', {});
    title.textContent = labels[state.metric] + '趋势';
    svg.append(title);
    const axisUnit = svgEl('text', {x: width - right, y: 12, 'text-anchor': 'end', class: 'chart-label'});
    axisUnit.textContent = '单位：' + units[state.metric];
    svg.append(axisUnit);
    for (let index = 0; index < 3; index++) {
      const level = top + index * plotHeight / 2;
      svg.append(svgEl('line', {x1: left, x2: width - right,
        y1: level, y2: level, class: 'grid-line'}));
      const label = svgEl('text', {x: 3, y: level + 4, class: 'chart-label'});
      label.textContent = fmt(high - index * (high - low) / 2,
        state.metric === 'weight_kg' ? 1 : 0);
      svg.append(label);
    }
    let segment = [];
    const finishSegment = () => {
      if (segment.length) svg.append(svgEl('polyline',
        {points: segment.join(' '), class: 'trend-line'}));
      segment = [];
    };
    values.forEach((value, index) => {
      if (value === null) finishSegment();
      else segment.push(x(index) + ',' + y(value));
    });
    finishSegment();
    values.forEach((value, index) => {
      if (value === null) return;
      const name = days[index].date + ' ' + labels[state.metric] + ' ' +
        fmt(value, state.metric === 'weight_kg' ? 1 : 0) + ' ' + units[state.metric];
      const dot = svgEl('circle', {cx: x(index), cy: y(value), r: 5,
        class: 'trend-dot', tabindex: '0', role: 'button', 'aria-label': name});
      const tip = svgEl('title', {});
      tip.textContent = name;
      dot.append(tip);
      dot.addEventListener('focus', () => showSelection(days[index]));
      dot.addEventListener('click', () => showSelection(days[index]));
      dot.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          showSelection(days[index]);
        }
      });
      svg.append(dot);
    });
    const stride = Math.max(1, Math.ceil(days.length / 6));
    days.forEach((row, index) => {
      if (index % stride && index !== days.length - 1) return;
      const label = svgEl('text', {x: x(index), y: height - 9,
        'text-anchor': 'middle', class: 'chart-label'});
      label.textContent = row.date.slice(5);
      svg.append(label);
    });
    chart.append(svg);
    text($('#chartSummary'), labels[state.metric] + '趋势，' + days[0].date +
      ' 至 ' + days[days.length - 1].date + '。' + present +
      ' 天有记录；空白日期代表没有记录。');
  }
  function renderDays() {
    const list = $('#dayList'); list.replaceChildren(); const days = (state.data.days || []).slice().reverse();
    if (!days.length) { const p = document.createElement('p'); p.className = 'muted'; p.textContent = '尚未读取到任何日期。请确认快捷指令已经运行并等待 iCloud 同步。'; list.append(p); return; }
    days.forEach((d) => { const article = document.createElement('article'); article.className = 'day-card'; const head = document.createElement('header'), time = document.createElement('time'); time.dateTime = d.date || ''; time.textContent = d.date || '未知日期'; const quality = document.createElement('span'); quality.className = 'day-quality'; const metricKeys = ['steps','active_kcal','heart_rate_avg_bpm','resting_bpm','weight_kg','sleep_minutes']; const available = metricKeys.filter((k) => num(d[k]) !== null).length; const partial = Array.isArray(d.partial_metrics) ? d.partial_metrics.map((x) => ({steps:'步数',active_kcal:'活动能量',heart_rate_avg_bpm:'心率记录均值',resting_bpm:'静息心率',weight_kg:'体重',sleep_minutes:'睡眠'}[x] || x)) : []; quality.textContent = `${available}/${metricKeys.length} 项有记录${partial.length ? ` · 部分记录：${partial.join('、')}` : ''}`; head.append(time, quality); const vals = document.createElement('div'); vals.className = 'day-values'; [['步数','steps','步'],['活动','active_kcal','kcal'],['心率记录均值','heart_rate_avg_bpm','bpm'],['静息心率','resting_bpm','bpm'],['睡眠','sleep_minutes',''],['体重','weight_kg','kg']].forEach(([label,key,unit]) => { const span = document.createElement('span'); const b = document.createElement('b'); b.textContent = key === 'sleep_minutes' ? sleep(d[key]) : fmt(d[key], key === 'weight_kg' ? 1 : 0); span.append(document.createTextNode(`${label} `), b, unit && num(d[key]) !== null ? document.createTextNode(` ${unit}`) : document.createTextNode('')); vals.append(span); }); const stages = d.sleep_stages; if (stages && typeof stages === 'object') { const stage = document.createElement('span'); const b = document.createElement('b'); const parts = [['核心', stages.core], ['深度', stages.deep], ['REM', stages.rem], ['未分层', stages.asleep]].filter(([,v]) => num(v) !== null).map(([k,v]) => `${k} ${fmt(v)}分`); b.textContent = parts.length ? parts.join(' · ') : '—'; stage.append(document.createTextNode('睡眠阶段 '), b); vals.append(stage); } article.append(head, vals); list.append(article); });
  }
  function render() { $('#localGuide').hidden = !demo; const d = state.data; const isDemoData = d.mode === 'demo' || demo; const hasDays = Array.isArray(d.days) && d.days.length > 0; text($('#modeBadge'), isDemoData ? '示例数据 · 合成演示' : '本机数据 · iCloud'); setStatus(isDemoData ? 'ok' : (hasDays ? 'ok' : 'error'), isDemoData ? '正在查看示例' : (hasDays ? '本机已连接' : '本机暂无记录'), isDemoData ? '这是合成数据，不会读取或上传你的健康记录。' : (hasDays ? `${d.days.length} 天记录已整理，可继续刷新。` : '尚未读取到有效记录；请确认快捷指令运行完成并等待 iCloud 同步。')); sourceStatus(d); renderSummary(); renderChart(); renderDays(); }
  async function load() { if (state.loading) return; state.loading = true; const button = $('#refreshBtn'); button.disabled = true; button.textContent = demo ? '重新加载示例…' : '刷新中…'; try { const response = await fetch(demo ? './demo.json' : '/api/health', { cache: 'no-store' }); if (!response.ok) throw new Error(`HTTP ${response.status}`); const data = await response.json(); if (!data || !Array.isArray(data.days)) throw new Error('返回数据缺少 days'); state.data = data; render(); } catch (error) { state.data = { days: [], source: { warnings: [] } }; text($('#modeBadge'), demo ? '示例数据 · 读取失败' : '本机数据 · 未连接'); setStatus('error', '暂时无法读取', demo ? '请刷新页面重试示例数据。' : '请确认本机服务运行在 127.0.0.1:8764，再点击刷新；不会自动切换为示例数据。'); sourceStatus(state.data); renderSummary(); renderChart(); renderDays(); } finally { state.loading = false; button.disabled = false; button.textContent = demo ? '重新加载示例' : '刷新数据'; } }
  document.addEventListener('click', (event) => { const range = event.target.closest('[data-range]'), metric = event.target.closest('[data-metric]'); if (range) { state.range = Number(range.dataset.range); document.querySelectorAll('[data-range]').forEach((b) => { const active = b === range; b.classList.toggle('active', active); b.setAttribute('aria-pressed', String(active)); }); renderChart(); } if (metric) { state.metric = metric.dataset.metric; document.querySelectorAll('[data-metric]').forEach((b) => { const active = b === metric; b.classList.toggle('active', active); b.setAttribute('aria-pressed', String(active)); }); renderChart(); } });
  $('#refreshBtn').addEventListener('click', load); load();
})();
