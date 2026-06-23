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
const { scoreEntry, isDefaultGroupOrder, FULL_MAX, DEFAULT_GROUP_SCALE } = require('./scoring.js');

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
const key = keyFile.answers || keyFile;
const tags = readJSON('data/private/tags.json', {});

const tagOf = (r) => tags[r.slug] || tags[(r.email || '').toLowerCase()] || '';

// ---- score ------------------------------------------------------------------
let entries = rows.map((r) => {
  const a = JSON.parse(r.payload);
  const defaultGroup = isDefaultGroupOrder(a.q8, groups);
  const s = scoreEntry(a, key, { defaultGroup });
  return {
    name: r.name, handle: r.display_name, slug: r.slug, tag: tagOf(r),
    defaultGroup, ...s,
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
