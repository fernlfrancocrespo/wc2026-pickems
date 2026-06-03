// GET /api/entry?slug=Xa9k2 — one entry's picks for the read-only share view.
// Returns display_name / country / lang / answers only — never name or email.
import { json } from "./_utils.js";

export async function onRequestGet({ request, env }) {
  if (!env.DB) return json({ ok: false, error: "no_database_bound" }, 500);

  const slug = new URL(request.url).searchParams.get("slug");
  if (!slug) return json({ ok: false, error: "no_slug" }, 400);

  const row = await env.DB.prepare(
    "SELECT display_name, country, lang, payload FROM submissions WHERE slug = ?"
  ).bind(slug).first();

  if (!row) return json({ ok: false, error: "not_found" }, 404);

  let answers = {};
  try { answers = JSON.parse(row.payload); } catch {}
  delete answers.email;

  return json({
    ok: true,
    entry: { display_name: row.display_name, country: row.country, lang: row.lang, answers },
  });
}
