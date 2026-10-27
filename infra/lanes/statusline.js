// Status line for Travel Yantra lanes: lane, model, context used,
// 5-hour and weekly usage. Claude Code sends session JSON on stdin.
let raw = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => { raw += chunk; });
process.stdin.on('end', () => {
  let d = {};
  try { d = JSON.parse(raw); } catch (e) { d = {}; }
  const pct = (v) => (typeof v === 'number' ? `${Math.round(v)}%` : '-');
  const lane = process.env.TY_LANE || 'TY?';
  const model = (d.model && d.model.display_name) || '';
  const ctxUsed = d.context_window ? d.context_window.used_percentage : null;
  const rl = d.rate_limits || {};
  const five = rl.five_hour ? pct(rl.five_hour.used_percentage) : '-';
  const week = rl.seven_day ? pct(rl.seven_day.used_percentage) : '-';
  const relay = typeof ctxUsed === 'number' && ctxUsed >= 60 ? ' | RELAY due' : '';
  process.stdout.write(`${lane} | ${model} | ctx ${pct(ctxUsed)} | 5h ${five} | week ${week}${relay}`);
});
