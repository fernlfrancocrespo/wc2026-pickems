#!/usr/bin/env python
"""
build_email_cards.py — per-participant assets for the "update your bracket" email:
  • out/email_cards/<rank>_<handle>.png   the "how you're doing" graphic
  • out/email_packets/<rank>_<handle>.txt  ready-to-paste subject + body (EN or PT)
  • out/email_cards/_mailmerge.csv         name, email, subject, link, card file

Pipeline:  node run-eval.js --project --json   (writes data/private/board.json)
           python build_email_cards.py
out/ is git-ignored (carries names/emails). Fill TUTORIAL_* below before sending.
"""
import csv
import json
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
CARDS = ROOT / "out" / "email_cards"
PACKETS = ROOT / "out" / "email_packets"
CARDS.mkdir(parents=True, exist_ok=True)
PACKETS.mkdir(parents=True, exist_ok=True)

# ── EDIT THESE before sending ────────────────────────────────────────────────
TUTORIAL_EN = "https://www.loom.com/share/062fbc8f2660461983e4ddeb6caad3b3"
TUTORIAL_PT = "https://www.loom.com/share/736fa3c047754feda9b3bcfa16731fa0"
# Who gets the Portuguese email. Everyone submitted in English, so we key PT off the
# Family tag (your Brazilian family). Add/remove tags, or list specific emails.
PT_TAGS = {"Family"}
PT_EMAILS = set()   # e.g. {"someone@email.com"}  — lowercased
SUBJECT_EN = "{first} — it's time to fill out your bracket"
SUBJECT_PT = "{first} — hora de preencher sua chave"
TOP_N = 15   # ranks 1..15 get the "in contention" email; the rest get the "anyone can win" email
# ─────────────────────────────────────────────────────────────────────────────

def highlights(conf, lang):
    """A phrase listing the confirmed things they got right (or '')."""
    gw = conf.get("gw") or {}
    en, pt = [], []
    if conf.get("q9") == "hit": en.append("the group-stage goal total"); pt.append("o total de gols da fase de grupos")
    if conf.get("q10") == "hit": en.append("the hat-trick call"); pt.append("o palpite do hat-trick")
    if gw.get("got"): en.append(f"{gw['got']} of {gw['of']} group winners"); pt.append(f"{gw['got']} de {gw['of']} vencedores de grupo")
    items = pt if lang == "pt" else en
    if not items: return ""
    joined = items[0] if len(items) == 1 else (", ".join(items[:-1]) + (" and " if lang != "pt" else " e ") + items[-1])
    return (f"Você já acertou {joined} — muito bem! " if lang == "pt"
            else f"You've already nailed {joined} — nice work! ")

def make_body(lang, first, tier, rank, total, inplay, conf, link, tutorial, n):
    hl = highlights(conf, lang)   # "" if nothing confirmed yet
    if lang == "pt":
        intro = "Obrigado por jogar no nosso bolão da Copa 2026 — a fase de grupos chegou ao fim!"
        if tier == "contend":   lead = f"E você está na briga: {rank}º de {n}, com {total} pontos. {hl}"
        elif tier == "field":   lead = f"E você está bem no jogo, com {total} pontos. {hl}"
        elif tier == "rising":  lead = f"Você está com {total} pontos até aqui. {hl}"
        else:                   lead = (hl or "Você está no placar e a diversão está só começando.")
        push = ("Agora a chave do mata-mata está aberta, com {inplay} pontos ainda em jogo — dá pra subir (ou defender). Preencha sua chave antes do apito dos 16 avos:"
                if tier in ("contend", "field") else
                "E o melhor: ainda há {inplay} pontos em jogo no mata-mata — mais que suficiente pra uma grande arrancada. Preencha sua chave antes do apito dos 16 avos:")
        deadline = ("PRAZOS — duas formas de enviar:\n"
                    "  • Até as 15h (ET, horário de Brasília 16h) de HOJE, domingo 28/06, antes do apito do primeiro jogo do mata-mata (Canadá x África do Sul). Esse é o prazo principal.\n"
                    "  • Não viu a tempo? Você tem até as 13h (ET) de segunda 29/06. Você perde só aquele jogo de domingo, e a gente compensa com pontos extras nas semifinais — sem pânico.")
        return (f"Oi {first},\n\n{intro}\n\n{lead}\n\n{push.format(inplay=inplay)}\n\n{link}\n\n{deadline}\n\n"
                f"Primeira vez? Este tutorial rápido (2 min) te ajuda: {tutorial}\n\n"
                f"Boa sorte!\n— Fernando\n\nP.S. O card em anexo mostra como você está indo até agora.")
    intro = "Thanks for playing our World Cup 2026 pick-'ems — the group stage is in the books!"
    if tier == "contend":   lead = f"And you're right in the mix: #{rank} of {n}, with {total} points. {hl}"
    elif tier == "field":   lead = f"And you're well in it, sitting on {total} points. {hl}"
    elif tier == "rising":  lead = f"You're on {total} points so far. {hl}"
    else:                   lead = (hl or "You're on the board and the fun's just getting started.")
    push = ("The knockout bracket is open now, with {inplay} points still up for grabs — plenty to climb or defend. Lock in your bracket before the Round of 32 kicks off:"
            if tier in ("contend", "field") else
            "And here's the fun part — there are {inplay} points still up for grabs in the knockouts, more than enough to make a real run. Fill out your bracket before the Round of 32 kicks off:")
    deadline = ("DEADLINES — two ways to get it in:\n"
                "  • By 3:00 PM ET TODAY, Sunday Jun 28, before the first knockout game (Canada vs South Africa) kicks off. This is the main deadline.\n"
                "  • Didn't see this in time? You have until 1:00 PM ET Monday Jun 29. You'll only miss that one Sunday match, and we'll give you bonus semifinal points to make up for it — so no panic.")
    return (f"Hi {first},\n\n{intro}\n\n{lead}\n\n{push.format(inplay=inplay)}\n\n{link}\n\n{deadline}\n\n"
            f"New to it? Here's a quick 2-minute walkthrough: {tutorial}\n\n"
            f"Good luck!\n— Fernando\n\nP.S. The attached card shows how you're doing so far.")

NAVY=(13,27,42); CARD=(26,45,64); TRACK=(15,34,53); LINE=(70,90,112)
GOLD=(201,168,76); GOLDL=(232,198,106); WHITE=(255,255,255)
GREY=(107,128,153); GREYL=(184,197,208); GREEN=(34,197,94); REDL=(232,133,127)
TAGCLR={"SDC":(125,211,252),"Lastinger":(252,165,165),"Family":(201,168,76)}
W,H = 1040, 664

CARD_TXT = {
  "en": {"eyebrow":"WORLD CUP 2026 · PICK-'EMS","how":"HOW YOU'RE DOING","of":"of {n}",
    "ahead":"ahead of {p}% of the field","points":"POINTS","nailed":"Look at everything you nailed!",
    "strong":"A strong group stage so far!","grabs":"STILL UP FOR GRABS","confirmed":"CONFIRMED — GROUP STAGE",
    "locked":"{p} pts locked in","goals":"Group-stage goals","hat":"Hat-trick call","order":"Group order  +{a}/{b}",
    "inplay_h":"STILL IN PLAY","inplay_pts":"{p} pts","ongoing1":"Champion, awards & your",
    "ongoing2":"knockout bracket — open now.","field":"THE FIELD","players":"{n} players · {a}–{b} pts",
    "wideopen":"The knockout bracket is wide open — plenty of room to climb.","scorecard":"full scorecard →"},
  "pt": {"eyebrow":"COPA DO MUNDO 2026 · BOLÃO","how":"COMO VOCÊ ESTÁ INDO","of":"de {n}",
    "ahead":"à frente de {p}% do bolão","points":"PONTOS","nailed":"Veja tudo o que você acertou!",
    "strong":"Uma boa fase de grupos!","grabs":"AINDA EM JOGO","confirmed":"CONFIRMADO — FASE DE GRUPOS",
    "locked":"{p} pts garantidos","goals":"Gols da fase de grupos","hat":"Palpite de hat-trick","order":"Ordem dos grupos  +{a}/{b}",
    "inplay_h":"AINDA EM JOGO","inplay_pts":"{p} pts","ongoing1":"Campeão, prêmios e sua",
    "ongoing2":"chave do mata-mata — já aberta.","field":"O BOLÃO","players":"{n} jogadores · {a}–{b} pts",
    "wideopen":"A chave do mata-mata está aberta — muito espaço pra subir.","scorecard":"placar completo →"},
}

def font(sz, bold=True):
    p = "C:/Windows/Fonts/" + ("arialbd.ttf" if bold else "arial.ttf")
    try: return ImageFont.truetype(p, sz)
    except Exception: return ImageFont.load_default()

def mark(d, x, y, state):  # drawn check / dash / x (Arial lacks ✓✗ glyphs)
    clr = {"hit":GREEN,"part":GOLD,"miss":REDL}.get(state, GREY)
    if state == "hit":    d.line([(x,y+7),(x+5,y+13),(x+15,y)], fill=clr, width=3, joint="curve")
    elif state == "miss": d.line([(x,y),(x+13,y+13)], fill=clr, width=3); d.line([(x+13,y),(x,y+13)], fill=clr, width=3)
    else:                 d.line([(x,y+7),(x+14,y+7)], fill=clr, width=3)

def main():
    # clear stale outputs (rank prefixes shift as standings change → orphans)
    for p in list(CARDS.glob("*.png")) + list(PACKETS.glob("*.txt")): p.unlink()
    board = json.loads((ROOT/"data/private/board.json").read_text(encoding="utf-8"))
    entries = board["entries"]
    raw = json.loads((ROOT/"data/private/_raw_export.json").read_text(encoding="utf-8"))[0]["results"]
    by_slug = {r["slug"]: r for r in raw}
    totals = [e["total"] for e in entries]
    mn, mx = min(totals), max(totals); N = len(entries)
    rows = []

    for e in entries:
        rank, total = e["rank"], round(e["total"])
        handle = e.get("handle") or "anon"; slug = e.get("slug") or ""
        tag = e.get("tag"); conf = e.get("conf") or {}
        rr = by_slug.get(slug, {}); fullname = rr.get("name") or handle
        lang = (rr.get("lang") or "en").lower()
        groupPts = round(e.get("lockedGroup", 0)); inplay = round(e.get("pendingMax", 0))
        below = sum(1 for t in totals if t < e["total"]); ahead = round(below/(N-1)*100) if N>1 else 100

        # Tier by percentile (dynamic). Top half sees rank + field; bottom half is
        # celebration only (no rank, no field); bottom 10% is pure celebration.
        tier = "contend" if rank <= 15 else ("field" if rank <= N/2 else ("cheer" if rank > N*0.9 else "rising"))
        show_field = tier in ("contend", "field")
        safe=re.sub(r"[^A-Za-z0-9_-]","",handle) or "anon"; base=f"{rank:02d}_{safe}"

        # Render BOTH an English and a Portuguese card — Fernando picks per recipient.
        for clang in ("en", "pt"):
            L = CARD_TXT[clang]
            img = Image.new("RGB",(W,H),NAVY); d = ImageDraw.Draw(img)
            d.rectangle([0,0,W,6], fill=GOLD)
            d.text((50,40), L["eyebrow"], font=font(20,False), fill=GREY)
            d.text((W-50,40), L["how"], font=font(22), fill=GOLD, anchor="ra")
            d.text((50,78), fullname, font=font(46), fill=WHITE)
            if tag:
                tc=TAGCLR.get(tag,GOLD); tw=d.textlength(tag.upper(),font=font(17))
                d.rounded_rectangle([50,142,50+tw+24,172], radius=15, outline=tc, width=2)
                d.text((62,144), tag.upper(), font=font(17), fill=tc)
            if show_field:
                d.text((50,192), f"#{rank}", font=font(118), fill=GOLD)
                rl=d.textlength(f"#{rank}",font=font(118))
                d.text((60+rl,272), L["of"].format(n=N), font=font(28,False), fill=GREYL)
                d.text((60+rl,306), L["ahead"].format(p=ahead), font=font(22,False), fill=GREEN if ahead>=50 else GREY)
                d.text((W-50,210), str(total), font=font(104), fill=WHITE, anchor="ra")
                d.text((W-50,322), L["points"], font=font(22), fill=GREY, anchor="ra")
            else:
                d.text((50,192), str(total), font=font(118), fill=GOLD)
                tl=d.textlength(str(total),font=font(118))
                d.text((60+tl,272), L["points"], font=font(28,False), fill=GREYL)
                d.text((60+tl,306), L["nailed"] if tier=="cheer" else L["strong"], font=font(22), fill=GREEN)
                d.text((W-50,210), f"+{inplay}", font=font(104), fill=WHITE, anchor="ra")
                d.text((W-50,322), L["grabs"], font=font(20), fill=GOLD, anchor="ra")
            # confirmed vs ongoing
            y=366; d.line([50,y,W-50,y], fill=LINE, width=1); midx=W//2
            d.text((50,y+14), L["confirmed"], font=font(18), fill=GREEN)
            d.text((50,y+40), L["locked"].format(p=groupPts), font=font(30), fill=WHITE)
            yy=y+84
            def conf_row(lbl, st):
                nonlocal yy
                if st is None: return
                mark(d, 50, yy+2, st); d.text((82,yy), lbl, font=font(20,False), fill=GREYL); yy+=30
            conf_row(L["goals"], conf.get("q9"))
            conf_row(L["hat"], conf.get("q10"))
            if conf.get("q8"):
                mark(d,50,yy+2,"part" if conf["q8"]["pts"]<conf["q8"]["max"] else "hit")
                d.text((82,yy), L["order"].format(a=conf['q8']['pts'],b=conf['q8']['max']), font=font(20,False), fill=GREYL); yy+=30
            d.text((midx+20,y+14), L["inplay_h"], font=font(18), fill=GOLD)
            d.text((midx+20,y+40), L["inplay_pts"].format(p=inplay), font=font(30), fill=WHITE)
            d.text((midx+20,y+86), L["ongoing1"], font=font(20,False), fill=GREYL)
            d.text((midx+20,y+112), L["ongoing2"], font=font(20,False), fill=GREYL)
            if show_field:
                Y=H-66; d.text((50,Y-24), L["field"], font=font(16), fill=GREY)
                d.text((W-50,Y-26), L["players"].format(n=N,a=round(mn),b=round(mx)), font=font(16,False), fill=GREY, anchor="ra")
                d.rounded_rectangle([50,Y,W-50,Y+12], radius=6, fill=TRACK); span=(mx-mn) or 1
                for t in totals:
                    x=50+(t-mn)/span*(W-100); d.line([x,Y,x,Y+12], fill=LINE, width=2)
                myx=50+(e["total"]-mn)/span*(W-100)
                d.polygon([(myx-8,Y-14),(myx+8,Y-14),(myx,Y-4)], fill=GOLD); d.line([myx,Y-6,myx,Y+18], fill=GOLD, width=4)
            else:
                d.text((W//2, H-78), L["wideopen"], font=font(19,False), fill=GREYL, anchor="ma")
            d.text((50,H-40), f"wc2026-pickems.com/p/{slug}", font=font(19,False), fill=GREY)
            d.text((W-50,H-40), L["scorecard"], font=font(19), fill=GOLD, anchor="ra")
            img.save(CARDS/f"{base}_{clang}.png")

        first=(fullname.split() or ["there"])[0]
        token=rr.get("edit_token","")
        link=f"https://wc2026-pickems.com/p/{slug}?k={token}" if token else f"https://wc2026-pickems.com/p/{slug}"
        # Both languages built for everyone — Fernando makes the language call at send
        # time. `suggest` is just a hint based on chosen lang / Family tag / PT_EMAILS.
        suggest = "pt" if ((lang == "pt") or (tag in PT_TAGS) or ((rr.get("email") or "").lower() in PT_EMAILS)) else "en"
        subj_en=SUBJECT_EN.format(first=first); subj_pt=SUBJECT_PT.format(first=first)
        body_en=make_body("en", first, tier, rank, total, inplay, conf, link, TUTORIAL_EN, N)
        body_pt=make_body("pt", first, tier, rank, total, inplay, conf, link, TUTORIAL_PT, N)
        # One packet per person holding BOTH languages, suggested one first.
        order = (("pt", subj_pt, body_pt, "en", subj_en, body_en) if suggest == "pt"
                 else ("en", subj_en, body_en, "pt", subj_pt, body_pt))
        l1,s1,b1,l2,s2,b2 = order
        packet = (
            f"TO: {rr.get('email','')}\nSUGGESTED LANG: {suggest}\n\n"
            f"{'='*60}\n[{l1.upper()}]  (suggested)\nSUBJECT: {s1}\nATTACH: email_cards/{base}_{l1}.png\n{'='*60}\n\n{b1}\n\n\n"
            f"{'='*60}\n[{l2.upper()}]\nSUBJECT: {s2}\nATTACH: email_cards/{base}_{l2}.png\n{'='*60}\n\n{b2}\n")
        (PACKETS/f"{base}.txt").write_text(packet, encoding="utf-8")
        rows.append({"rank":rank,"name":fullname,"email":rr.get("email",""),"suggested_lang":suggest,"tag":tag or "",
                     "total":total,"tier":tier,
                     "subject_en":subj_en,"body_en":body_en,"card_en":f"{base}_en.png",
                     "subject_pt":subj_pt,"body_pt":body_pt,"card_pt":f"{base}_pt.png","link":link})

    with open(CARDS/"_mailmerge.csv","w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=["rank","name","email","suggested_lang","tag","total","tier",
                                       "subject_en","body_en","card_en","subject_pt","body_pt","card_pt","link"])
        w.writeheader(); [w.writerow(r) for r in sorted(rows,key=lambda r:r["rank"])]
    print(f"wrote {len(rows)*2} cards (en+pt, out/email_cards) + {len(rows)} packets (out/email_packets) + _mailmerge.csv")
    print(f"  ! set TUTORIAL_EN / TUTORIAL_PT at the top of this script before sending.")

if __name__ == "__main__":
    main()
