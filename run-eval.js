#!/usr/bin/env node
/* ============================================================================
 * World Cup 2026 Pick-'Ems — evaluation CLI ("who's winning right now")
 *
 *   node run-eval.js [--tag SDC|Lastinger] [--all] [--top N]
 *
 * Loads the private participant export, grades every entry against the current
 * answer key, applies the default-group rebalance, and prints a ranked board
 * with the locked-vs-pending split. This is the trust-the-numbers tool: the
 * leaderboard page renders the same engine (scoring.js), so what prints here is
 * what ships.
 *
 * Inputs (all local, none committed if private):
 *   data/private/_raw_export.json   wrangler d1 export (id,…,payload)
 *   data/groups.json                default group order (for default detection)
 *   data/answer_key.json            host truth; nulls = not graded yet
 *   data/private/tags.json          { slug|email: "SDC"|"Lastinger" }  (optional)
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const { scoreEntry, isDefaultGroupOrder, FULL_MAX, DEFAULT_GROUP_SCALE,
        bandIndexFor } = require('./scoring.js');

// Band option lists (mirror scoring.js BAND_OPTS) for the "which band is winning" view.
const BAND_OPTS = {
  q9:  ['0–149','150–169','170–184','185–199','200–219','220+'],
  q11: ['0–224','225–249','250–269','270–289','290–314','315+'],
  q12: ['0–4','5–7','8–10','11–13','14–16','17+'],
  q13: ['0–3','4–6','7–9','10–12','13–16','17+'],
  q14: ['0–4','5–8','9–13','14–18','19–25','26+'],
  q15: ['Under 20m','20–24m','25–29m','30–34m','35–40m','41m+'],
  q16: ['Under 11s','11–20s','21–35s','36–50s','51–90s','Over 90s'],
};

const ROOT = __dirname;
const readJSON = (p, fb) => {
  try { return JSON.parse(fs.readFileSync(path.join(ROOT, p), 'utf8')); }
  catch (e) { if (fb !== undefined) return fb; throw e; }
};

// ---- args -------------------------------------------------------------------
const args = process.argv.slice(2);
const opt = (flag) => { const i = args.indexOf(flag); return i >= 0 ? args[i + 1] : null; };
const tagFilter = opt('--tag');
const topN = parseInt(opt('--top') || '0', 10);
const showAll = args.includes('--all');

// ---- load -------------------------------------------------------------------
const rawExport = readJSON('data/private/_raw_export.json');
const rows = Array.isArray(rawExport) ? rawExport[0].results : rawExport.results;
const groups = readJSON('data/groups.json');
const keyFile = readJSON('data/answer_key.json');
let key = keyFile.answers || keyFile;
const tags = readJSON('data/tags.json', {});

// --project: grade against the CURRENT live standings (provisional group order +
// goals so far) as if the group stage ended now. Clearly a projection, not locked.
const project = args.includes('--project');
let projNote = '';
if (project) {
  const ls = readJSON('data/live_stats.json', null);
  if (!ls) { console.error('No data/live_stats.json — run: python scrape_live.py'); process.exit(1); }
  key = JSON.parse(JSON.stringify(key));
  key.q8 = key.q8 || {};
  Object.entries(ls.groups).forEach(([L, g]) => { key.q8[L] = g.provisional_order; });
  if (key.q9 == null) key.q9 = ls.group_goals_total;   // band graded vs current total
  // q10 hat-trick is genuinely locked once one happens (can't un-happen)
  if (key.q10 == null && ls.hat_trick_in_group_stage) key.q10 = 'Yes';
  // q18 Golden Boot (top scorer): current scoring leader (trending; full name match)
  if (key.q18_player == null && ls.top_scorers && ls.top_scorers.length) key.q18_player = ls.top_scorers[0].player;
  // band props from live timing + connected-ball data
  const gt = ls.goal_timing || {};
  if (key.q14 == null && gt.added_time_goals != null) key.q14 = gt.added_time_goals;     // added-time goals
  if (key.q16 == null && gt.fastest_goal_seconds != null) key.q16 = gt.fastest_goal_seconds; // fastest goal (s)
  const ball = readJSON('data/ball_stats.json', null);
  if (key.q15 == null && ball && ball.q15_longest_range_m != null) key.q15 = ball.q15_longest_range_m; // longest-range (m)
  const lead = ls.top_scorers && ls.top_scorers[0];
  projNote = `PROJECTED off live standings (${ls.matches_played} matches, ${ls.group_goals_total} goals` +
             `${ls.group_stage_complete ? ', group stage COMPLETE' : ', group stage in progress'})` +
             `\n  trending: hat-trick=${ls.hat_trick_in_group_stage ? 'YES (locked)' : 'none yet'}` +
             `  ·  Golden Boot leader=${lead ? lead.player + ' (' + lead.goals + ')' : '—'}`;
}

const tagOf = (r) => tags[r.slug] || tags[(r.email || '').toLowerCase()] || '';

// ---- score ------------------------------------------------------------------
let entries = rows.map((r) => {
  const a = JSON.parse(r.payload);
  const defaultGroup = isDefaultGroupOrder(a.q8, groups);
  const s = scoreEntry(a, key, { defaultGroup });
  return {
    name: r.name, handle: r.display_name, slug: r.slug, tag: tagOf(r),
    defaultGroup, picks: a, ...s,
  };
});

if (tagFilter) entries = entries.filter((e) => e.tag.toLowerCase() === tagFilter.toLowerCase());

// rank by current total; tiebreak by graded coverage then name
entries.sort((a, b) => b.total - a.total || b.graded - a.graded || a.name.localeCompare(b.name));

// ---- print ------------------------------------------------------------------
const anyGraded = entries.some((e) => e.graded > 0);
const f = (n) => (Math.round(n * 10) / 10).toString().padStart(6);
const pct = (e) => (e.graded > 0 ? Math.round((e.total / e.graded) * 100) + '%' : '—');

console.log(`\nWORLD CUP 2026 PICK-'EMS — current standings`);
if (projNote) console.log(projNote);
console.log(`entries: ${entries.length}${tagFilter ? `  ·  tag: ${tagFilter}` : ''}` +
            `  ·  graded so far: ${anyGraded ? 'partial' : 'NONE (answer key still empty)'}`);
console.log(`default-group (rebalanced ×${DEFAULT_GROUP_SCALE.toFixed(2)}): ` +
            entries.filter((e) => e.defaultGroup).length + ` of ${entries.length}\n`);

console.log('  #  NAME                      TAG        TOTAL  LOCKED   GROUP     KO   %OFGRADED  FLAG');
console.log('  ' + '-'.repeat(92));
const list = topN ? entries.slice(0, topN) : entries;
list.forEach((e, i) => {
  console.log(
    `${String(i + 1).padStart(3)}. ` +
    `${(e.name || e.handle).slice(0, 24).padEnd(24)}  ` +
    `${(e.tag || '·').slice(0, 9).padEnd(9)}  ` +
    `${f(e.total)} ${f(e.lockedTotal)} ${f(e.lockedGroup)} ${f(e.lockedKO)}   ` +
    `${pct(e).padStart(7)}    ${e.defaultGroup ? '*default-grp' : ''}`
  );
});
if (!showAll && topN) console.log(`\n  …${entries.length - topN} more (use --all)`);
console.log(`\n  * default-grp: never ranked the groups; q8 scored 0, other points ×${DEFAULT_GROUP_SCALE.toFixed(2)} so the ceiling stays ${FULL_MAX}.`);
if (!anyGraded) console.log('  NOTE: answer_key.json has no real outcomes yet — totals are all 0 until results are entered.\n');

// ---- JSON board export (for the local preview page) -------------------------
// `--json` writes data/private/board.json (contains names → local-only).
if (args.includes('--json')) {
  const ls = readJSON('data/live_stats.json', {});
  const ball = readJSON('data/ball_stats.json', {});
  // "which band is winning" per band prop: current value, correct band, pick distribution
  const props = {};
  Object.entries(BAND_OPTS).forEach(([qid, opts]) => {
    const real = key[qid];
    if (real == null) return;
    const correctIdx = bandIndexFor(Number(String(real).replace(/[ms]/gi, '')), opts);
    const dist = opts.map(() => 0);
    entries.forEach((e) => { const i = opts.indexOf(e.picks[qid]); if (i >= 0) dist[i]++; });
    props[qid] = { value: real, correctBand: opts[correctIdx] || null, options: opts, distribution: dist };
  });
  const board = {
    generated: new Date().toISOString(),
    projected: project,
    note: projNote || null,
    groupStageComplete: !!ls.group_stage_complete,
    trending: {
      group_goals: ls.group_goals_total ?? null,
      added_time_goals: (ls.goal_timing || {}).added_time_goals ?? null,
      fastest_goal_seconds: (ls.goal_timing || {}).fastest_goal_seconds ?? null,
      longest_range_m: ball.q15_longest_range_m ?? null,
      hat_trick: !!ls.hat_trick_in_group_stage,
      golden_boot: (ls.top_scorers || [])[0] || null,
    },
    top_scorers: ls.top_scorers || [],
    hat_tricks: ls.hat_tricks || [],
    longest_range_goals: ball.longest_range_goals || [],
    props,
    entries: entries.map((e, i) => ({
      rank: i + 1, name: e.name, handle: e.handle, tag: e.tag || null,
      total: Math.round(e.total * 10) / 10, lockedGroup: Math.round(e.lockedGroup * 10) / 10,
      lockedKO: Math.round(e.lockedKO * 10) / 10, pendingMax: Math.round(e.pendingMax * 10) / 10,
      defaultGroup: e.defaultGroup, pct: e.graded > 0 ? Math.round((e.total / e.graded) * 100) : null,
    })),
  };
  const out = path.join(ROOT, 'data', 'private', 'board.json');
  fs.writeFileSync(out, JSON.stringify(board, null, 2));
  console.log(`\n  wrote ${out} (${board.entries.length} entries) for the preview page`);
}
