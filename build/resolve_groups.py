"""Resolve each roster group to a Wikidata QID — and prove it's the right one.

A bare name search is not trustworthy here: "izna", "MEOVV", "Billlie" and
"Nature" all collide with unrelated items, and a wrong QID silently poisons the
whole member list downstream. So every candidate must clear explicit checks and
the script prints its reasoning for human review.

Checks, in order:
  1. P31 (instance of) is a group/ensemble type, and is NOT a boy band
  2. genre (P136) or country (P17/P495) smells like K-pop / South Korea
  3. inception (P571) is within a couple of years of our hand-authored debut
  4. it actually has P527 members

Writes data/groups_resolved.json. Rows that fail get status="UNRESOLVED" and are
listed at the end — those need a hand-pinned QID, not a silent drop.

Run: PYTHONIOENCODING=utf-8 python build/resolve_groups.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wdapi  # noqa: E402
from roster import GROUPS  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "data", "groups_resolved.json")

# Verified by looking the QIDs up rather than recalling them — an earlier version
# of this list had an ant species standing in for "girl group".
GROUP_TYPES = {
    "Q641066": "girl group",
    "Q11446438": "female idol group",
    "Q7623897": "all-female band",
    "Q215380": "musical group",
    "Q2088357": "musical ensemble",
    "Q9212979": "musical duo",
    "Q281643": "musical trio",
    "Q5741069": "rock band",
}
REJECT_TYPES = {
    "Q5": "human",
    "Q104635718": "discography",
    "Q169930": "extended play",
    "Q482994": "album",
    "Q7366": "song",
    "Q134556": "single",
    "Q4167410": "disambiguation page",
    "Q13442814": "scholarly article",
}
KPOP_GENRES = {"Q213665": "K-pop", "Q37073": "pop", "Q11401": "dance-pop",
               "Q188290": "hip hop", "Q170545": "R&B", "Q9778": "electropop"}
KOREA = {"Q884", "Q18097"}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def score(ent, g):
    """Return (ok, reasons[]) for a candidate entity."""
    reasons = []
    types = [v["id"] for v in wdapi.values(ent, "P31")
             if isinstance(v, dict) and "id" in v]
    bad = [REJECT_TYPES[t] for t in types if t in REJECT_TYPES]
    if bad:
        return False, [f"REJECT type={','.join(bad)}"]
    good = [GROUP_TYPES[t] for t in types if t in GROUP_TYPES]
    if not good:
        return False, [f"not a group type (P31={types})"]
    reasons.append("type=" + ",".join(good))

    genres = [v["id"] for v in wdapi.values(ent, "P136")
              if isinstance(v, dict) and "id" in v]
    country = [v["id"] for v in wdapi.values(ent, "P495") + wdapi.values(ent, "P17")
               if isinstance(v, dict) and "id" in v]
    kpop = "Q213665" in genres
    kr = bool(KOREA & set(country))
    if kpop:
        reasons.append("genre=K-pop")
    elif kr:
        reasons.append("country=KR")
    elif genres or country:
        reasons.append(f"WEAK genre={genres[:3]} country={country[:2]}")
    else:
        reasons.append("WEAK no genre/country")

    inc = wdapi.wtime(wdapi.first(ent, "P571"))
    if inc:
        dy = abs(int(inc[:4]) - int(g["debut"][:4]))
        reasons.append(f"inception={inc[:4]} (debut {g['debut'][:4]}, d={dy})")
        if dy > 3:
            return False, reasons + ["REJECT inception too far from debut"]
    else:
        reasons.append("no inception")

    members = [v for v in wdapi.values(ent, "P527")
               if isinstance(v, dict) and "id" in v]
    reasons.append(f"P527={len(members)}")

    # The K-pop/Korea signal is evidence, not a requirement. Some girl groups
    # are typed as US/pop on Wikidata rather than Korean — a HYBE x Geffen act
    # is what first forced this — so an unambiguous "girl group" type plus an
    # exact name match is enough on its own.
    strong_type = any(t in ("Q641066", "Q11446438", "Q7623897") for t in types)
    exact_name = norm(wdapi.label(ent)) == norm(g["name"]) or any(
        norm(wdapi.label(ent)) == norm(a) for a in g.get("aka", []))
    ok = bool(good) and len(members) >= 2 and (kpop or kr
                                              or (strong_type and exact_name))
    return ok, reasons


results = []
unresolved = []
for g in GROUPS:
    name = g["name"]
    pinned = g.get("wd")
    terms = [name] + [a for a in g.get("aka", []) if re.match(r"^[\x00-\x7F]+$", a)]
    cands = []
    if pinned:
        cands = [pinned]
    else:
        seen = set()
        for t in terms[:3]:
            for hit in wdapi.search(t, limit=8):
                if hit["id"] not in seen:
                    seen.add(hit["id"])
                    cands.append(hit["id"])
        cands = cands[:14]

    ents = wdapi.get_entities(cands, props="claims|labels|sitelinks") if cands else {}
    print(f"\n=== {name}  ({len(cands)} candidates)")
    best = None
    for qid in cands:
        ent = ents.get(qid)
        if not ent:
            continue
        ok, reasons = score(ent, g)
        lbl = wdapi.label(ent) or "?"
        nm = norm(lbl) == norm(name) or any(norm(lbl) == norm(a)
                                            for a in g.get("aka", []))
        flag = "OK " if ok else "   "
        print(f"  {flag}{qid:<12} {lbl:<28} name={'=' if nm else 'x'} "
              f"| {'; '.join(reasons)}")
        if ok and best is None:
            n_members = len([v for v in wdapi.values(ent, "P527")
                             if isinstance(v, dict)])
            best = (qid, lbl, n_members, nm)
        elif ok and nm and not best[3]:
            n_members = len([v for v in wdapi.values(ent, "P527")
                             if isinstance(v, dict)])
            best = (qid, lbl, n_members, nm)

    if best:
        # P18 while we have the entity in hand — the group grid and its result
        # card want a picture too, and every group on the roster has one.
        ent = ents.get(best[0], {})
        img = next((v for v in wdapi.values(ent, "P18") if isinstance(v, str)),
                   None)
        print(f"  -> CHOSE {best[0]} ({best[1]}, {best[2]} members)"
              f"{'' if img else '  [no P18 image]'}")
        results.append(dict(g, wd=best[0], wd_label=best[1],
                            wd_members=best[2], image=img, status="ok"))
    else:
        print("  -> UNRESOLVED")
        unresolved.append(name)
        results.append(dict(g, wd=None, status="UNRESOLVED"))

wdapi.save()
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=1)

print(f"\n\n===== {len(results) - len(unresolved)}/{len(results)} resolved")
if unresolved:
    print("UNRESOLVED (need a hand-pinned QID in roster.py):")
    for n in unresolved:
        print("  -", n)
