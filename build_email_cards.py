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
TUTORIAL_EN = "https://YOUTUBE-LINK-EN"
TUTORIAL_PT = "https://YOUTUBE-LINK-PT"
SUBJECT_EN = "{first} — it's time to fill out your bracket"
SUBJECT_PT = "{first} — hora de preencher sua chave"
BODY_EN = """Hi {first},

Thank you for playing in our World Cup 2026 pick-'ems! The group stage is over, so the knockout bracket is now open — fill it out for bonus points.

Your bracket link: {link}

Attached is a snapshot of how you're doing so far. If you run into any issues, this short tutorial walks you through it: {tutorial}

Good luck,
Fernando"""
BODY_PT = """Oi {first},

Obrigado por participar do nosso bolão da Copa 2026! A fase de grupos acabou, então a chave do mata-mata já está aberta — preencha para ganhar pontos bônus.

Seu link da chave: {link}

Em anexo está um resumo de como você está indo. Se tiver qualquer dificuldade, este tutorial rápido te ajuda: {tutorial}

Boa sorte,
Fernando"""
# ─────────────────────────────────────────────────────────────────────────────

NAVY=(13,27,42); CARD=(26,45,64); TRACK=(15,34,53); LINE=(70,90,112)
GOLD=(201,168,76); GOLDL=(232,198,106); WHITE=(255,255,255)
GREY=(107,128,153); GREYL=(184,197,208); GREEN=(34,197,94); REDL=(232,133,127)
TAGCLR={"SDC":(125,211,252),"Lastinger":(252,165,165),"Family":(201,168,76)}
W,H = 1040, 664

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

        img = Image.new("RGB",(W,H),NAVY); d = ImageDraw.Draw(img)
        d.rectangle([0,0,W,6], fill=GOLD)
        d.text((50,40), "WORLD CUP 2026 · PICK-'EMS", font=font(20,False), fill=GREY)
        d.text((W-50,40), "HOW YOU'RE DOING", font=font(22), fill=GOLD, anchor="ra")
        d.text((50,78), fullname, font=font(46), fill=WHITE)
        if tag:
            tc=TAGCLR.get(tag,GOLD); tw=d.textlength(tag.upper(),font=font(17))
            d.rounded_rectangle([50,142,50+tw+24,172], radius=15, outline=tc, width=2)
            d.text((62,144), tag.upper(), font=font(17), fill=tc)
        # rank + total
        d.text((50,192), f"#{rank}", font=font(118), fill=GOLD)
        rl=d.textlength(f"#{rank}",font=font(118))
        d.text((60+rl,272), f"of {N}", font=font(28,False), fill=GREYL)
        d.text((60+rl,306), f"ahead of {ahead}% of the field", font=font(22,False), fill=GREEN if ahead>=50 else GREY)
        d.text((W-50,210), str(total), font=font(104), fill=WHITE, anchor="ra")
        d.text((W-50,322), "POINTS", font=font(22), fill=GREY, anchor="ra")

        # ── confirmed vs ongoing ─────────────────────────────────
        y=366; d.line([50,y,W-50,y], fill=LINE, width=1)
        midx=W//2
        d.text((50,y+14), "CONFIRMED — GROUP STAGE", font=font(18), fill=GREEN)
        d.text((50,y+40), f"{groupPts} pts locked in", font=font(30), fill=WHITE)
        yy=y+84
        def conf_row(lbl, st):
            nonlocal yy
            if st is None: return
            mark(d, 50, yy+2, st); d.text((82,yy), lbl, font=font(20,False), fill=GREYL); yy+=30
        conf_row("Group-stage goals", conf.get("q9"))
        conf_row("Hat-trick call", conf.get("q10"))
        if conf.get("q8"):
            mark(d,50,yy+2,"part" if conf["q8"]["pts"]<conf["q8"]["max"] else "hit")
            d.text((82,yy), f"Group order  +{conf['q8']['pts']}/{conf['q8']['max']}", font=font(20,False), fill=GREYL); yy+=30
        # ongoing
        d.text((midx+20,y+14), "STILL IN PLAY", font=font(18), fill=GOLD)
        d.text((midx+20,y+40), f"{inplay} pts", font=font(30), fill=WHITE)
        d.text((midx+20,y+86), "Champion, awards & your", font=font(20,False), fill=GREYL)
        d.text((midx+20,y+112), "knockout bracket — open now.", font=font(20,False), fill=GREYL)

        # field strip
        Y=H-66; d.text((50,Y-24), "THE FIELD", font=font(16), fill=GREY)
        d.text((W-50,Y-26), f"{N} players · {round(mn)}–{round(mx)} pts", font=font(16,False), fill=GREY, anchor="ra")
        d.rounded_rectangle([50,Y,W-50,Y+12], radius=6, fill=TRACK)
        span=(mx-mn) or 1
        for t in totals:
            x=50+(t-mn)/span*(W-100); d.line([x,Y,x,Y+12], fill=LINE, width=2)
        myx=50+(e["total"]-mn)/span*(W-100)
        d.polygon([(myx-8,Y-14),(myx+8,Y-14),(myx,Y-4)], fill=GOLD); d.line([myx,Y-6,myx,Y+18], fill=GOLD, width=4)
        d.text((50,H-40), f"wc2026-pickems.com/p/{slug}", font=font(19,False), fill=GREY)
        d.text((W-50,H-40), "full scorecard →", font=font(19), fill=GOLD, anchor="ra")

        safe=re.sub(r"[^A-Za-z0-9_-]","",handle) or "anon"; base=f"{rank:02d}_{safe}"
        img.save(CARDS/f"{base}.png")

        first=(fullname.split() or ["there"])[0]
        link=f"https://wc2026-pickems.com/p/{slug}"
        pt = lang=="pt"
        subj=(SUBJECT_PT if pt else SUBJECT_EN).format(first=first)
        body=(BODY_PT if pt else BODY_EN).format(first=first, link=link, tutorial=(TUTORIAL_PT if pt else TUTORIAL_EN))
        (PACKETS/f"{base}.txt").write_text(
            f"TO: {rr.get('email','')}\nSUBJECT: {subj}\nATTACH: email_cards/{base}.png\nLANG: {lang}\n\n{body}\n", encoding="utf-8")
        rows.append({"rank":rank,"name":fullname,"email":rr.get("email",""),"lang":lang,"tag":tag or "",
                     "total":total,"subject":subj,"card_file":f"{base}.png","link":link})

    with open(CARDS/"_mailmerge.csv","w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=["rank","name","email","lang","tag","total","subject","card_file","link"])
        w.writeheader(); [w.writerow(r) for r in sorted(rows,key=lambda r:r["rank"])]
    print(f"wrote {len(rows)} cards (out/email_cards) + {len(rows)} packets (out/email_packets) + _mailmerge.csv")
    print(f"  ⚠ set TUTORIAL_EN / TUTORIAL_PT at the top of this script before sending.")

if __name__ == "__main__":
    main()
