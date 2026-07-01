/* ============================================================================
 * World Cup 2026 Pick-'Ems — shared scoring engine
 * Include AFTER i18n.js. Pure functions; no DOM.
 *
 *   scoreEntry(answers, key) -> { total, max, graded, breakdown:{ qid: {pts,max} } }
 *
 * `answers` is a submission's answers object (q1..q21 + q8).
 * `key` is answer_key.json's `answers` object — fill values in as outcomes are known;
 * any null/missing value is simply "not graded yet" (contributes 0 to total, but its
 * max is excluded from `graded` so percentages stay fair mid-tournament).
 * ========================================================================== */

const POINTS = {
  q1:25, q2:12, q3:6 /* each */, q4:10, q5:8, q6:8, q7:8,
  q8:72 /* 6 per group */, q9:8, q10:4, q11:8, q12:6, q13:5, q14:5, q15:6, q16:4,
  q17:12, q18:12, q19:8, q20:6, q21:6, q22:6,
};

// Full perfect score across every question (q3 is worth 6 twice = 12).
const FULL_MAX = Object.values(POINTS).reduce((a, b) => a + b, 0) + POINTS.q3; // 251
// Pool of points available to a "default-group" entry (everything except q8).
const NON_Q8_MAX = FULL_MAX - POINTS.q8; // 179
// Rebalance factor: a default-group entry can still reach FULL_MAX by earning more on
// every other question, so q8's 72 pts are redistributed proportionally over the rest.
const DEFAULT_GROUP_SCALE = FULL_MAX / NON_Q8_MAX; // ≈ 1.402

// Which questions settle when the GROUP STAGE ends (vs. over the knockout/whole tournament).
const GROUP_QS = ['q8', 'q9', 'q10'];

// True if a submission's q8 is byte-for-byte the form's default order in every group
// (i.e. the person never dragged anything). `groups` is data/groups.json.
function isDefaultGroupOrder(q8, groups) {
  if (!q8 || !groups) return false;
  const letters = Object.keys(groups);
  if (letters.length === 0) return false;
  return letters.every(L => {
    const def = groups[L], mine = q8[L];
    return Array.isArray(mine) && Array.isArray(def) &&
           mine.length === def.length && mine.every((t, i) => t === def[i]);
  });
}

// Band options per numeric question (must match the form's BANDS).
const BAND_OPTS = {
  q9:  ['0–149','150–169','170–184','185–199','200–219','220+'],
  q11: ['0–224','225–249','250–269','270–289','290–314','315+'],
  q12: ['0–4','5–7','8–10','11–13','14–16','17+'],
  q13: ['0–3','4–6','7–9','10–12','13–16','17+'],
  q14: ['0–4','5–8','9–13','14–18','19–25','26+'],
  q15: ['Under 20m','20–24m','25–29m','30–34m','35–40m','41m+'],
  q16: ['Under 11s','11–20s','21–35s','36–50s','51–90s','Over 90s'],
};
const HALF = { q9:4, q11:4, q12:3, q13:3, q14:3, q15:3, q16:2 };

// Parse a band label into [lo, hi] (inclusive; null = open end). Units (m/s) ignored.
function bandRange(opt) {
  const s = String(opt).replace(/[ms]/gi, '').trim();
  let m;
  if ((m = s.match(/^Under\s+(\d+)/i)))  return [null, parseInt(m[1], 10) - 1];
  if ((m = s.match(/^Over\s+(\d+)/i)))   return [parseInt(m[1], 10) + 1, null];
  if ((m = s.match(/^(\d+)\+/)))         return [parseInt(m[1], 10), null];
  if ((m = s.match(/^(\d+)\s*[–-]\s*(\d+)/))) return [parseInt(m[1], 10), parseInt(m[2], 10)];
  if ((m = s.match(/^(\d+)$/)))          return [parseInt(m[1], 10), parseInt(m[1], 10)];
  return [null, null];
}
function bandIndexFor(value, opts) {
  for (let i = 0; i < opts.length; i++) {
    const [lo, hi] = bandRange(opts[i]);
    if ((lo == null || value >= lo) && (hi == null || value <= hi)) return i;
  }
  return -1;
}

function scoreBand(qid, picked, value) {
  const opts = BAND_OPTS[qid];
  const full = POINTS[qid];
  if (value == null || !picked) return 0;
  const pickedIdx  = opts.indexOf(picked);
  const correctIdx = bandIndexFor(Number(value), opts);
  if (pickedIdx < 0 || correctIdx < 0) return 0;
  if (pickedIdx === correctIdx) return full;
  if (Math.abs(pickedIdx - correctIdx) === 1) return HALF[qid];
  return 0;
}

function scoreEntry(answers, key, opts) {
  answers = answers || {};
  key = key || {};
  opts = opts || {};
  const bd = {};
  let total = 0, graded = 0;
  const add = (qid, pts, max, isGraded) => {
    bd[qid] = { pts, max, graded: !!isGraded };
    total += pts;
    if (isGraded) graded += max;
  };

  // Exact team / player picks
  [['q1', POINTS.q1], ['q2', POINTS.q2], ['q4', POINTS.q4], ['q5', POINTS.q5],
   ['q6', POINTS.q6], ['q7', POINTS.q7],
   ['q17_player', POINTS.q17], ['q18_player', POINTS.q18], ['q19_player', POINTS.q19],
   ['q20_player', POINTS.q20], ['q21_player', POINTS.q21], ['q22_player', POINTS.q22]].forEach(([qid, max]) => {
    const real = key[qid];
    const graded_ = real != null && real !== '';
    add(qid, graded_ && answers[qid] === real ? max : 0, max, graded_);
  });

  // Q3 — two losing semifinalists (order-agnostic, 6 each)
  {
    const realSet = [key.q3a, key.q3b].filter(Boolean);
    const graded_ = realSet.length > 0;
    let pts = 0;
    if (graded_) {
      [answers.q3a, answers.q3b].filter(Boolean).forEach(p => { if (realSet.includes(p)) pts += POINTS.q3; });
    }
    add('q3', Math.min(pts, POINTS.q3 * 2), POINTS.q3 * 2, graded_);
  }

  // Q10 — yes/no
  {
    const real = key.q10, graded_ = real != null && real !== '';
    add('q10', graded_ && answers.q10 === real ? POINTS.q10 : 0, POINTS.q10, graded_);
  }

  // Bands
  ['q9', 'q11', 'q12', 'q13', 'q14', 'q15', 'q16'].forEach(qid => {
    const real = key[qid], graded_ = real != null && real !== '';
    add(qid, graded_ ? scoreBand(qid, answers[qid], real) : 0, POINTS[qid], graded_);
  });

  // Q8 — group ranking (per group: +2 per team in real top-2, +2 perfect order; max 6)
  {
    const realGroups = key.q8 || {};
    const letters = Object.keys(realGroups);
    const graded_ = letters.length > 0;
    let pts = 0;
    letters.forEach(L => {
      const real = realGroups[L], mine = (answers.q8 || {})[L];
      if (!Array.isArray(real) || !Array.isArray(mine)) return;
      const realTop2 = [real[0], real[1]];
      [mine[0], mine[1]].forEach(team => { if (realTop2.includes(team)) pts += 2; });
      if (mine.length === 4 && real.length === 4 && mine.every((t, i) => t === real[i])) pts += 2;
    });
    add('q8', pts, POINTS.q8, graded_);
  }

  // ---- Default-group rebalance --------------------------------------------
  // Entries that never touched the drag-rankings are not penalized on q8: it's
  // scored 0 and marked skipped, and their remaining points are scaled up so a
  // perfect non-q8 sheet still reaches FULL_MAX. Per-question breakdown stays
  // RAW (honest); only the rolled-up total/graded are scaled. The flag + scale
  // are returned so the UI can disclose the asterisk.
  let defaultGroup = false, rebalanceScale = 1;
  if (opts.defaultGroup) {
    defaultGroup = true;
    rebalanceScale = DEFAULT_GROUP_SCALE;
    const q8 = bd.q8 || { pts: 0, max: 0, graded: false };
    total  -= q8.pts;                       // remove q8 from the rolled-up total
    if (q8.graded) graded -= q8.max;         // and from the graded denominator
    bd.q8 = { pts: 0, max: 0, graded: false, skipped: true };
    total  = Math.min(total * rebalanceScale, FULL_MAX);
    graded = graded * rebalanceScale;        // keeps mid-tournament % fair
  }

  // ---- Locked vs. pending split -------------------------------------------
  // "Locked" = points already decided (this question is graded in the key).
  // Everything else is still in play. The two-bucket (group/knockout) split
  // mirrors the spec; `lockedGroup` settles after the group stage.
  let lockedTotal = 0, lockedGroup = 0, lockedKO = 0, pendingMax = 0;
  Object.entries(bd).forEach(([qid, b]) => {
    const isGroup = GROUP_QS.includes(qid);
    if (b.skipped) return;
    if (b.graded) {
      const pts = defaultGroup ? b.pts * rebalanceScale : b.pts;
      lockedTotal += pts;
      if (isGroup) lockedGroup += pts; else lockedKO += pts;
    } else {
      pendingMax += defaultGroup ? b.max * rebalanceScale : b.max;
    }
  });

  return {
    total, max: FULL_MAX, graded, breakdown: bd,
    defaultGroup, rebalanceScale,
    lockedTotal, lockedGroup, lockedKO, pendingMax,
  };
}

// First Round-of-32 kickoff. An entry submitted AFTER this couldn't pick the games
// already played, so it's a "late" entry and gets the semifinal compensation below.
const FIRST_R32_KICKOFF = Date.parse('2026-06-28T19:00:00Z'); // Sun Jun 28, 3:00 PM ET — first R32 kickoff (Canada v South Africa). Submit after = late = SF comp.
function isLateBracket(createdAtISO) {
  const t = Date.parse(createdAtISO || '');
  return !isNaN(t) && t > FIRST_R32_KICKOFF;
}

// Score the knockout bracket — a bonus ON TOP of the 251-point main entry (not
// rebalanced). `picks` = answers.bracket { matchId: winningTeam }. `struct` =
// bracket.json. `results` = { matchId: actualWinner } (filled as knockouts play).
// Each match: you earn its round's points if your pick equals the real winner.
// opts.lateSfBonus: extra points per SEMIFINAL match for late entrants (who couldn't
// pick the early games) — Fernando's +1-per-SF fairness rule.
function scoreBracket(picks, struct, results, opts) {
  picks = picks || {}; results = results || {}; opts = opts || {};
  const sfBonus = opts.lateSfBonus || 0;
  const out = { pts: 0, max: 0, graded: false, byRound: {} };
  if (!struct || !struct.rounds) return out;
  struct.rounds.forEach(rd => {
    const ptsPer = rd.points + (rd.key === 'SF' ? sfBonus : 0);
    const r = { pts: 0, max: 0, correct: 0, decided: 0, points: ptsPer };
    rd.matches.forEach(mid => {
      const id = String(mid);
      r.max += ptsPer; out.max += ptsPer;
      const real = results[id];
      if (real != null && real !== '') {
        out.graded = true; r.decided++;
        if (picks[id] === real) { r.pts += ptsPer; r.correct++; out.pts += ptsPer; }
      }
    });
    out.byRound[rd.key] = r;
  });
  return out;
}

// True if the answer key has at least one real (graded) outcome.
function keyHasData(key) {
  if (!key) return false;
  const a = key.answers || key;
  if (a.q8 && Object.keys(a.q8).length) return true;
  return ['q1','q2','q3a','q4','q5','q6','q7','q9','q10','q11','q12','q13','q14','q15','q16',
          'q17_player','q18_player','q19_player','q20_player','q21_player','q22_player']
          .some(k => a[k] != null && a[k] !== '');
}

// CommonJS export for the Node-side eval CLI; no-op in the browser (where these
// names are already globals on window).
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    POINTS, FULL_MAX, NON_Q8_MAX, DEFAULT_GROUP_SCALE, GROUP_QS,
    isDefaultGroupOrder, scoreEntry, scoreBracket, isLateBracket, FIRST_R32_KICKOFF, keyHasData, scoreBand, bandIndexFor, bandRange,
  };
}
