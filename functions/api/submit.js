// POST /api/submit  — record one locked-in entry into D1.
// Same-origin call from the form; returns JSON the client can read.
import { json, sha256Hex } from "./_utils.js";

const REQUIRED_TEAM = ["q1", "q2", "q3a", "q3b", "q4", "q5", "q6", "q7"];
const REQUIRED_BAND = ["q9", "q10", "q11", "q12", "q13", "q14", "q15", "q16"];
const REQUIRED_PLAYER = ["q17_player", "q18_player", "q19_player", "q20_player", "q21_player", "q22_player"];
// Group-stage answers that are FROZEN once the tournament kicks off — after the lock,
// these can never be set or changed via the API (anti-cheat for the bracket window).
const FROZEN_KEYS = [...REQUIRED_TEAM, ...REQUIRED_BAND, ...REQUIRED_PLAYER, "q8",
  "q17_team", "q18_team", "q19_team", "q20_team", "q21_team", "q22_team"];
const LOCK_TIME = Date.parse("2026-06-11T19:00:00Z"); // group-stage lock (opening kickoff)

// Short, unambiguous share code (no 0/O/1/l/I). 7 chars → ~1.3e12 space.
const SLUG_ALPHABET = "23456789abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ";
function makeSlug(len = 7) {
  const bytes = new Uint8Array(len);
  crypto.getRandomValues(bytes);
  let s = "";
  for (let i = 0; i < len; i++) s += SLUG_ALPHABET[bytes[i] % SLUG_ALPHABET.length];
  return s;
}

export async function onRequestPost({ request, env }) {
  if (!env.DB) return json({ ok: false, error: "no_database_bound" }, 500);

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: "bad_json" }, 400);
  }

  // Optional shared entry code (only enforced if the ENTRY_CODE secret is set).
  if (env.ENTRY_CODE && body.code !== env.ENTRY_CODE) {
    return json({ ok: false, error: "bad_code" }, 403);
  }

  if (!body.name || typeof body.name !== "string") {
    return json({ ok: false, error: "missing_name" }, 400);
  }

  // Strip email + code from the stored payload; email stays in its own column.
  const { email = "", code, ...rest } = body;
  const emailNorm = String(email).trim().toLowerCase();
  const postLock = Date.now() > LOCK_TIME;

  // Existing entry for this email — fetched BEFORE any delete, so we can keep the same
  // share slug across edits and freeze the locked group-stage answers.
  let prior = null;
  if (emailNorm) {
    try { prior = await env.DB.prepare("SELECT slug, payload FROM submissions WHERE lower(email) = ?").bind(emailNorm).first(); }
    catch (e) { prior = null; }
  }

  if (!postLock) {
    // Pre-kickoff: a full entry is required (client enforces this too).
    const missing = [];
    REQUIRED_TEAM.forEach((k) => { if (!body[k]) missing.push(k); });
    REQUIRED_BAND.forEach((k) => { if (!body[k]) missing.push(k); });
    REQUIRED_PLAYER.forEach((k) => { if (!body[k]) missing.push(k); });
    if (!body.q8 || Object.keys(body.q8).length < 12) missing.push("q8");
    if (missing.length) return json({ ok: false, error: "incomplete", missing }, 422);
  } else {
    // Post-kickoff (bracket window): FREEZE the group-stage answers. Edits keep the
    // prior entry's locked picks; brand-new bracket-only entrants get none (score 0
    // there). This makes it impossible to set or alter group picks after the lock.
    let priorAns = {};
    try { priorAns = prior ? JSON.parse(prior.payload) : {}; } catch (e) { priorAns = {}; }
    FROZEN_KEYS.forEach((k) => { if (priorAns[k] !== undefined) rest[k] = priorAns[k]; else delete rest[k]; });
    const hasBracket = rest.bracket && Object.keys(rest.bracket).length;
    if (!prior && !hasBracket) return json({ ok: false, error: "nothing_to_submit" }, 422);
  }

  // EDIT-BY-EMAIL: a new submission with the same email REPLACES the previous one.
  if (emailNorm) {
    try { await env.DB.prepare("DELETE FROM submissions WHERE lower(email) = ?").bind(emailNorm).run(); }
    catch (e) { /* non-fatal: fall through to insert */ }
  }

  // Intake cap — once reached, intake is "closed" until you raise MAX_SUBMISSIONS.
  const max = parseInt(env.MAX_SUBMISSIONS || "1000", 10);
  const countRow = await env.DB.prepare("SELECT COUNT(*) AS c FROM submissions").first();
  if (countRow && countRow.c >= max) {
    return json({ ok: false, error: "closed" }, 423);
  }

  const ipHash = ""; // IP capture disabled

  // `hidden` lives inside the payload JSON (rest.hidden) — no dedicated column, so this
  // works on any existing table without a migration. results.js reads it back out.
  const stmt = `INSERT INTO submissions
       (created_at, slug, name, display_name, email, country, lang, payload, ip_hash)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`;
  const fields = [
    new Date().toISOString(),
    null, // slug filled per-attempt below
    String(body.name).slice(0, 120),
    String(body.displayName || "").slice(0, 60),
    String(email).slice(0, 200),
    String(body.country || "").slice(0, 60),
    String(body.lang || "en").slice(0, 5),
    JSON.stringify(rest),
    ipHash,
  ];

  // Insert, retrying a couple of times on the (very unlikely) slug collision.
  let slug = "";
  for (let attempt = 0; attempt < 4; attempt++) {
    // Reuse the prior share slug on an edit (it's free now that we deleted the row),
    // so a person's /p/<slug> link stays stable across bracket edits.
    slug = (attempt === 0 && prior && prior.slug) ? prior.slug : makeSlug();
    fields[1] = slug;
    try {
      await env.DB.prepare(stmt).bind(...fields).run();
      return json({ ok: true, slug });
    } catch (e) {
      if (String(e).includes("UNIQUE") && attempt < 3) continue;
      return json({ ok: false, error: "db_insert_failed", detail: String(e) }, 500);
    }
  }
  return json({ ok: false, error: "slug_collision" }, 500);
}
