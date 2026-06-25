#!/usr/bin/env python
"""
build_email_cards.py — one PNG "how you're doing vs the field" card per participant,
for attaching in the status email. Also writes a mail-merge CSV (name, email, link,
card file) so the sends are copy-paste.

Pipeline:  node run-eval.js --project --json   (writes data/private/board.json)
           python build_email_cards.py
Reads:  data/private/board.json (scores+rank+slug), data/private/_raw_export.json (email)
Writes: out/email_cards/<rank>_<handle>.png  +  out/email_cards/_mailmerge.csv
        (out/ is git-ignored — cards carry names.)
"""
import csv
import json
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
OUT = ROOT / "out" / "email_cards"
OUT.mkdir(parents=True, exist_ok=True)

NAVY=(13,27,42); CARD=(26,45,64); TRACK=(15,34,53)
GOLD=(201,168,76); GOLDL=(232,198,106); WHITE=(255,255,255)
GREY=(107,128,153); GREYL=(184,197,208); GREEN=(34,197,94)
TAGCLR={"SDC":(125,211,252),"Lastinger":(252,165,165),"Family":(201,168,76)}
W,H = 1040, 560

def font(sz, bold=True):
    p = "C:/Windows/Fonts/" + ("arialbd.ttf" if bold else "arial.ttf")
    try: return ImageFont.truetype(p, sz)
    except Exception: return ImageFont.load_default()

def main():
    board = json.loads((ROOT/"data/private/board.json").read_text(encoding="utf-8"))
    entries = board["entries"]
    raw = json.loads((ROOT/"data/private/_raw_export.json").read_text(encoding="utf-8"))[0]["results"]
    email_by_slug = {r["slug"]: r.get("email","") for r in raw}
    name_by_slug  = {r["slug"]: r.get("name","") for r in raw}

    totals = [e["total"] for e in entries]
    mn, mx = min(totals), max(totals); N = len(entries)
    proj = board.get("projected")
    rows = []

    for e in entries:
        rank, total = e["rank"], e["total"]
        handle = e.get("handle") or "anon"
        slug = e.get("slug") or ""
        tag = e.get("tag")
        below = sum(1 for t in totals if t < total)
        ahead_pct = round(below/(N-1)*100) if N>1 else 100

        img = Image.new("RGB",(W,H),NAVY); d = ImageDraw.Draw(img)
        d.rectangle([0,0,W,6], fill=GOLD)                       # top accent
        # eyebrow
        d.text((50,42), "WORLD CUP 2026 · PICK-'EMS", font=font(20,False), fill=GREY)
        d.text((W-50,42), "HOW YOU'RE DOING", font=font(22), fill=GOLD, anchor="ra")
        # name
        d.text((50,82), name_by_slug.get(slug) or handle, font=font(48), fill=WHITE)
        # tag chip
        cx=50
        if tag:
            tc=TAGCLR.get(tag,GOLD); tw=d.textlength(tag.upper(),font=font(18))
            d.rounded_rectangle([cx,150,cx+tw+26,182], radius=16, outline=tc, width=2)
            d.text((cx+13,152), tag.upper(), font=font(18), fill=tc)
        # big rank + total
        d.text((50,205), f"#{rank}", font=font(140), fill=GOLD)
        rl = d.textlength(f"#{rank}", font=font(140))
        d.text((58+rl,300), f"of {N}", font=font(30,False), fill=GREYL)
        d.text((58+rl,338), f"ahead of {ahead_pct}% of the field", font=font(24,False), fill=GREEN if ahead_pct>=50 else GREY)
        d.text((W-50,225), str(round(total)), font=font(110), fill=WHITE, anchor="ra")
        d.text((W-50,345), "POINTS" + (" · projected" if proj else ""), font=font(22), fill=GREY, anchor="ra")
        d.text((W-50,378), f"{round(e.get('lockedGroup',0))} group · {round(e.get('lockedKO',0))} knockout",
               font=font(20,False), fill=GREYL, anchor="ra")

        # distribution strip
        X0,X1,Y = 50, W-50, 452
        d.text((X0,Y-30), "THE FIELD", font=font(18), fill=GREY)
        d.text((X1,Y-30), f"{N} players · {round(mn)}–{round(mx)} pts", font=font(18,False), fill=GREY, anchor="ra")
        d.rounded_rectangle([X0,Y,X1,Y+14], radius=7, fill=TRACK)
        span = (mx-mn) or 1
        for t in totals:                                        # field ticks
            x = X0 + (t-mn)/span*(X1-X0)
            d.line([x,Y,x,Y+14], fill=(70,90,112), width=2)
        myx = X0 + (total-mn)/span*(X1-X0)                      # this player's marker
        d.line([myx,Y-8,myx,Y+22], fill=GOLD, width=4)
        d.polygon([(myx-8,Y-16),(myx+8,Y-16),(myx,Y-6)], fill=GOLD)
        # footer
        d.text((50,H-42), f"wc2026-pickems.com/p/{slug}", font=font(20,False), fill=GREY)
        d.text((W-50,H-42), "full scorecard →", font=font(20), fill=GOLD, anchor="ra")

        safe = re.sub(r"[^A-Za-z0-9_-]","", handle) or "anon"
        fn = f"{rank:02d}_{safe}.png"
        img.save(OUT/fn)
        rows.append({"rank":rank,"name":name_by_slug.get(slug,""),"display_name":handle,
                     "email":email_by_slug.get(slug,""),"tag":tag or "","total":round(total),
                     "ahead_pct":ahead_pct,"card_file":fn,"link":f"https://wc2026-pickems.com/p/{slug}"})

    with open(OUT/"_mailmerge.csv","w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=["rank","name","display_name","email","tag","total","ahead_pct","card_file","link"])
        w.writeheader(); rows.sort(key=lambda r:r["rank"]); [w.writerow(r) for r in rows]
    print(f"wrote {len(rows)} cards + _mailmerge.csv to {OUT}")

if __name__ == "__main__":
    main()
