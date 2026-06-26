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
// Secret per-entry edit token (32 hex chars) — the unguessable key in a person's link.
function makeToken() {
  const b = new Uint8Array(16);
  crypto.getRandomValues(b);
  return [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
}
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

  // token = the secret edit key from a person's emailed link; strip it from the payload.
  const { email = "", code, token, ...rest } = body;
  const emailNorm = String(email).trim().toLowerCase();
  const postLock = Date.now() > LOCK_TIME;
  const tok = (typeof token === "string" && token.length >= 16) ? token : null;

  let prior = null;          // the row being edited (and replaced)
  let storeEmail = email;    // email written to the row

  if (!postLock) {
    // Pre-kickoff: full entry required; first-time entries (edit-by-email, historical).
    const missing = [];
    REQUIRED_TEAM.forEach((k) => { if (!body[k]) missing.push(k); });
    REQUIRED_BAND.forEach((k) => { if (!body[k]) missing.push(k); });
    REQUIRED_PLAYER.forEach((k) => { if (!body[k]) missing.push(k); });
    if (!body.q8 || Object.keys(body.q8).length < 12) missing.push("q8");
    if (missing.length) return json({ ok: false, error: "incomplete", missing }, 422);
    if (emailNorm) {
      try { prior = await env.DB.prepare("SELECT slug, email, edit_token FROM submissions WHERE lower(email)=?").bind(emailNorm).first(); } catch (e) {}
    }
  } else if (tok) {
    // Post-kickoff EDIT — authorized by the secret token only (never by email).
    try { prior = await env.DB.prepare("SELECT slug, email, payload, edit_token FROM submissions WHERE edit_token=?").bind(tok).first(); } catch (e) {}
    if (!prior) return json({ ok: false, error: "bad_token" }, 403);   // invalid/fabricated link
    let priorAns = {}; try { priorAns = JSON.parse(prior.payload); } catch (e) {}
    FROZEN_KEYS.forEach((k) => { if (priorAns[k] !== undefined) rest[k] = priorAns[k]; else delete rest[k]; });
    storeEmail = prior.email || email;   // keep the owner's email; body can't change it
  } else {
    // Post-kickoff, NO token → only a brand-new bracket-only entry. Never overwrite an
    // existing entry by email (that was the hole). Group answers are dropped.
    if (emailNorm) {
      let exists = null;
      try { exists = await env.DB.prepare("SELECT 1 FROM submissions WHERE lower(email)=?").bind(emailNorm).first(); } catch (e) {}
      if (exists) return json({ ok: false, error: "use_your_link" }, 409);
    }
    if (!(rest.bracket && Object.keys(rest.bracket).length)) return json({ ok: false, error: "nothing_to_submit" }, 422);
    FROZEN_KEYS.forEach((k) => { delete rest[k]; });
  }

  // Replace the prior row (edits keep the same slug + token + email).
  if (prior) {
    try { await env.DB.prepare("DELETE FROM submissions WHERE edit_token=?").bind(prior.edit_token).run(); } catch (e) {}
  }

  // Intake cap — once reached, intake is "closed" until you raise MAX_SUBMISSIONS.
  const max = parseInt(env.MAX_SUBMISSIONS || "1000", 10);
  const countRow = await env.DB.prepare("SELECT COUNT(*) AS c FROM submissions").first();
  if (countRow && countRow.c >= max) return json({ ok: false, error: "closed" }, 423);

  const editToken = (prior && prior.edit_token) || makeToken();   // keep owner's token, else mint one
  const stmt = `INSERT INTO submissions
       (created_at, slug, name, display_name, email, country, lang, payload, ip_hash, edit_token)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`;
  const fields = [
    new Date().toISOString(), null,
    String(body.name).slice(0, 120),
    String(body.displayName || "").slice(0, 60),
    String(storeEmail).slice(0, 200),
    String(body.country || "").slice(0, 60),
    String(body.lang || "en").slice(0, 5),
    JSON.stringify(rest), "", editToken,
  ];
  let slug = "";
  for (let attempt = 0; attempt < 4; attempt++) {
    slug = (attempt === 0 && prior && prior.slug) ? prior.slug : makeSlug();  // stable /p/<slug> across edits
    fields[1] = slug;
    try {
      await env.DB.prepare(stmt).bind(...fields).run();
      return json({ ok: true, slug, token: editToken });   // token returned so a new entrant gets their edit link
    } catch (e) {
      if (String(e).includes("UNIQUE") && attempt < 3) continue;
      return json({ ok: false, error: "db_insert_failed", detail: String(e) }, 500);
    }
  }
  return json({ ok: false, error: "slug_collision" }, 500);
}
