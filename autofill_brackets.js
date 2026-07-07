// One-off: quietly complete near-complete brackets (exactly 29 or 30 of 31 picks).
// For each missing match, infer the pick in this order:
//   1. Their own DOWNSTREAM picks imply it (they picked X to win a later match on
//      this winner-chain, and X is one of the two teams meeting here in THEIR tree).
//   2. Their Final Four answers (q1 champion > q2 runner-up > q3a/q3b semifinalists).
//   3. Higher FIFA seed (lower fifa_rank in teams.json).
// Emits data/private/autofill.sql (D1 UPDATEs) + a human-readable report to stdout.
// Usage: node autofill_brackets.js   (requires data/private/_autofill_export.json)
const fs = require('fs');
const struct = JSON.parse(fs.readFileSync('data/bracket.json', 'utf8'));
const state = JSON.parse(fs.readFileSync('data/bracket_state.json', 'utf8'));
const teams = JSON.parse(fs.readFileSync('data/teams.json', 'utf8'));
const rows = JSON.parse(fs.readFileSync('data/private/_autofill_export.json', 'utf8'))[0].results;

const ALL_MIDS = struct.rounds.flatMap(r => r.matches).map(String); // 31, ascending
// consumer[mid] = the later match this winner feeds
const consumer = {};
for (const [cid, m] of Object.entries(struct.matches)) {
  for (const s of [m.s1, m.s2]) if (s.t === 'W' && s.m) consumer[String(s.m)] = cid;
}
const rank = t => (teams[t] && teams[t].fifa_rank) || 999;

function theirTeams(mid, bracket) { // the two teams meeting at mid in THEIR tree
  const m = struct.matches[mid];
  if (m.round === 'R32') { const r = state.r32_teams[mid] || {}; return [r.s1, r.s2]; }
  return [bracket[String(m.s1.m)] || null, bracket[String(m.s2.m)] || null];
}

const sql = [];
for (const row of rows) {
  const payload = JSON.parse(row.payload);
  const a = payload.answers || payload; // payload shape: answers at top or nested
  const br = a.bracket || {};
  const n = ALL_MIDS.filter(m => br[m]).length;
  if (n !== 29 && n !== 30) continue;

  const filled = [];
  for (const mid of ALL_MIDS) { // ascending → feeders resolve before consumers
    if (br[mid]) continue;
    const [t1, t2] = theirTeams(mid, br);
    if (!t1 || !t2) { filled.push([mid, null, 'unresolvable (feeder also empty)']); continue; }
    let pick = null, why = '';
    for (let c = consumer[mid]; c; c = consumer[c]) { // 1. downstream implication
      const p = br[c];
      if (p === t1 || p === t2) { pick = p; why = `their M${c} pick`; break; }
    }
    if (!pick) { // 2. final four
      for (const [q, lbl] of [['q1', 'champion'], ['q2', 'runner-up'], ['q3a', 'semifinalist'], ['q3b', 'semifinalist']]) {
        if (a[q] === t1 || a[q] === t2) { pick = a[q]; why = `their ${lbl} pick (${q})`; break; }
      }
    }
    if (!pick) { pick = rank(t1) <= rank(t2) ? t1 : t2; why = `higher seed (#${rank(pick)} vs #${rank(pick === t1 ? t2 : t1)})`; }
    br[mid] = pick;
    filled.push([mid, pick, why]);
  }
  if (!filled.length) continue;
  console.log(`\n${row.display_name} (${row.slug}) — had ${n}/31:`);
  filled.forEach(([m, p, w]) => console.log(`  M${m} -> ${p || 'SKIPPED'}  [${w}]`));
  a.bracket = br;
  const esc = JSON.stringify(payload).replace(/'/g, "''");
  sql.push(`UPDATE submissions SET payload='${esc}' WHERE slug='${row.slug}';`);
}
fs.writeFileSync('data/private/autofill.sql', sql.join('\n') + '\n');
console.log(`\n${sql.length} entries to update -> data/private/autofill.sql`);
