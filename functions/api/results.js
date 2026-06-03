// GET /api/results — all entries for the leaderboard/dashboard.
// PRIVACY: never returns full name or email — only the public display_name + answers.
import { json } from "./_utils.js";

export async function onRequestGet({ request, env }) {
  if (!env.DB) return json({ ok: false, error: "no_database_bound" }, 500);

  // Optional read protection: if RESULTS_TOKEN secret is set, require ?token=... to match.
  if (env.RESULTS_TOKEN) {
    const token = new URL(request.url).searchParams.get("token");
    if (token !== env.RESULTS_TOKEN) return json({ ok: false, error: "unauthorized" }, 401);
  }

  const { results } = await env.DB.prepare(
    `SELECT created_at, slug, display_name, country, lang, payload
       FROM submissions
      ORDER BY created_at ASC`
  ).all();

  const submissions = (results || []).map((r) => {
    let answers = {};
    try { answers = JSON.parse(r.payload); } catch {}
    const hidden = !!answers.hidden;      // stored inside the payload (no column needed)
    delete answers.email;                 // belt-and-suspenders
    delete answers.hidden;                // don't expose the flag inside answers
    return {
      created_at: r.created_at,
      slug: r.slug,
      display_name: r.display_name,
      country: r.country,
      lang: r.lang,
      hidden,
      answers,
    };
  });

  return json({ ok: true, count: submissions.length, submissions });
}
