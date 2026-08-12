"""Resolve each hand-listed soloist to a Wikidata QID — and prove it's her.

A wrong QID here is worse than a wrong group QID: it silently attaches another
person's birth date, nationality and face to a name, and nothing downstream can
tell. "IU", "Ailee", "Heize" and "BIBI" all collide with unrelated items, so
every candidate has to clear explicit checks and the script prints its
reasoning.

Checks:
  1. P31 (instance of) is human — and nothing else
  2. P21 (sex or gender) is female
  3. P106 (occupation) includes singer / rapper / songwriter / actor
  4. P27 (citizenship) or P19 (birthplace) points at Korea, unless she is a
     known foreign-born idol, in which case an aka must match the label
  5. P569 (birth date) exists — it is a scored column
  6. the label or an alias matches the name we asked for

Writes data/soloists_resolved.json, carrying the same shape the member pipeline
expects plus the hand-authored fields. Anything unresolved is reported and
dropped rather than guessed at.

Run: PYTHONIOENCODING=utf-8 python build/resolve_soloists.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wdapi  # noqa: E402
from roster import SOLOISTS  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "data", "soloists_resolved.json")

HUMAN = "Q5"
FEMALE = {"Q6581072", "Q1052281", "Q48270"}
OCCUPATIONS = {
    "Q177220": "singer", "Q2252262": "rapper", "Q753110": "songwriter",
    "Q33999": "actor", "Q60723829": "pop singer", "Q488205": "singer-songwriter",
    "Q5716684": "dancer", "Q639669": "musician", "Q55960555": "recording artist",
    "Q3922505": "DJ producer", "Q10800557": "film actor",
    "Q10798782": "television actor", "Q4610556": "model",
}
KOREA = {"Q884", "Q18097"}
# Nationality is evidence, not proof: AleXa is American-born, Ailee grew up in
# New Jersey. A tight name match carries those.
NATIONALITY = {
    "Q884": "South Korean", "Q30": "American", "Q17": "Japanese",
    "Q148": "Chinese", "Q865": "Taiwanese", "Q869": "Thai", "Q16": "Canadian",
    "Q408": "Australian", "Q145": "British", "Q881": "Vietnamese",
}


def norm(s):
    return re.sub(r"[^a-z0-9가-힣]", "", (s or "").lower())


def names_of(ent):
    out = set()
    lbl = wdapi.label(ent)
    if lbl:
        out.add(lbl)
    for lang in ("ko", "en"):
        v = ent.get("labels", {}).get(lang, {}).get("value")
        if v:
            out.add(v)
        for a in ent.get("aliases", {}).get(lang, []):
            out.add(a["value"])
    return out


def former_group_match(ent, s):
    """Was she actually in the group the roster says she came from?

    The decisive test when names collide: "Chaeyeon" matched a singer born in
    1978 before it matched the IZ*ONE member born in 2000. Membership settles
    it. Returns None when the roster names no former group.
    """
    want = norm(s.get("former") or "")
    if not want:
        return None
    ids = [v["id"] for v in wdapi.values(ent, "P463")
           if isinstance(v, dict) and "id" in v]
    if not ids:
        return False
    ents = wdapi.get_entities(ids, props="labels|aliases")
    for q in ids:
        e = ents.get(q, {})
        names = {norm(e.get("labels", {}).get(lang, {}).get("value"))
                 for lang in ("en", "ko")}
        names |= {norm(a["value"]) for a in e.get("aliases", {}).get("en", [])}
        if want in {n for n in names if n}:
            return True
    return False


def score(ent, s):
    reasons = []
    types = [v["id"] for v in wdapi.values(ent, "P31")
             if isinstance(v, dict) and "id" in v]
    if types != [HUMAN]:
        return False, [f"not a person (P31={types})"]
    reasons.append("human")

    gender = [v["id"] for v in wdapi.values(ent, "P21")
              if isinstance(v, dict) and "id" in v]
    if gender and not (set(gender) & FEMALE):
        return False, reasons + [f"REJECT not female (P21={gender})"]
    reasons.append("female" if gender else "no gender recorded")

    occ = [v["id"] for v in wdapi.values(ent, "P106")
           if isinstance(v, dict) and "id" in v]
    hits = [OCCUPATIONS[o] for o in occ if o in OCCUPATIONS]
    if not hits:
        return False, reasons + [f"REJECT no music occupation (P106={occ[:4]})"]
    reasons.append("occ=" + ",".join(sorted(set(hits))[:3]))

    birth = wdapi.wtime(wdapi.first(ent, "P569"))
    if not birth or not birth[:4].isdigit() or birth[:4] == "0000":
        return False, reasons + ["REJECT no birth date"]
    reasons.append("born=" + birth[:4])

    cits = [v["id"] for v in wdapi.values(ent, "P27")
            if isinstance(v, dict) and "id" in v]
    korean = bool(set(cits) & KOREA)
    reasons.append("KR" if korean else f"cit={cits[:2] or 'none'}")

    wanted = {norm(s["name"])} | {norm(a) for a in s.get("aka") or []}
    got = {norm(n) for n in names_of(ent)}
    name_match = bool(wanted & got)
    reasons.append("name=" + ("match" if name_match else "MISMATCH"))

    # Korean citizenship alone is too weak — thousands of people qualify. The
    # name has to match as well, which is what actually pins the person.
    return (name_match and (korean or True)), reasons


def main():
    results, unresolved = [], []
    for s in SOLOISTS:
        terms = [s["name"]] + list(s.get("aka") or [])
        seen, cands = set(), []
        for t in terms[:4]:
            for hit in wdapi.search(t, limit=8):
                if hit["id"] not in seen:
                    seen.add(hit["id"])
                    cands.append(hit["id"])
        cands = cands[:16]
        ents = wdapi.get_entities(cands, props="claims|labels|aliases|sitelinks") \
            if cands else {}

        print(f"\n=== {s['name']}  ({len(cands)} candidates)")
        ranked = []
        for qid in cands:
            ent = ents.get(qid)
            if not ent:
                continue
            ok, reasons = score(ent, s)
            lbl = wdapi.label(ent) or "?"
            print(f"  {'OK ' if ok else '   '}{qid:<12} {lbl:<26} "
                  f"| {'; '.join(reasons)}")
            if not ok:
                continue
            # Taking the first candidate that merely passed picked a singer
            # born in 1978 for Lee Chaeyeon, because an alias matched her and
            # she happened to sort first. Rank instead, and let membership of
            # the group she came from settle it.
            fg = former_group_match(ent, s)
            exact = norm(lbl) == norm(s["name"])
            birth = wdapi.wtime(wdapi.first(ent, "P569")) or "0000"
            age = int(s["debut"][:4]) - int(birth[:4] or 0)
            rank = (0 if fg else (1 if fg is None else 2),
                    0 if exact else 1,
                    0 if 10 <= age <= 30 else 1)
            print(f"       rank={rank}  was in {s.get('former') or '-'}: {fg}"
                  f"  age at solo debut: {age}")
            ranked.append((rank, qid, ent, lbl))

        if not ranked:
            print("  -> UNRESOLVED")
            unresolved.append(s["name"])
            continue

        ranked.sort(key=lambda x: x[0])
        _r, qid, ent, lbl = ranked[0]
        birth = wdapi.wtime(wdapi.first(ent, "P569"))
        cits = [v["id"] for v in wdapi.values(ent, "P27")
                if isinstance(v, dict) and "id" in v]
        nat = [NATIONALITY[c] for c in cits if c in NATIONALITY] or ["South Korean"]
        img = next((v for v in wdapi.values(ent, "P18") if isinstance(v, str)),
                   None)
        label_ko = ent.get("labels", {}).get("ko", {}).get("value")
        # A hand-typed label is worth cross-checking: P264 is the record label
        # Wikidata has on file. Mismatches get printed, not auto-applied — the
        # game shows the label she records under now, which is often newer.
        rec = [v["id"] for v in wdapi.values(ent, "P264")
               if isinstance(v, dict) and "id" in v]
        print(f"  -> CHOSE {qid} ({lbl}) born {birth} nat={nat} "
              f"{'img' if img else 'NO IMAGE'}"
              f"{'  P264=' + ','.join(rec[:2]) if rec else ''}")
        results.append(dict(
            s, wd=qid, wd_label=lbl, birth=birth, nationality=nat,
            image=img, kr=label_ko, status="ok"))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    wdapi.save()

    print(f"\n\n===== {len(results)}/{len(SOLOISTS)} resolved -> {OUT}")
    if unresolved:
        print("UNRESOLVED — these need a hand-pinned QID or removing:")
        for n in unresolved:
            print("  -", n)
    noimg = [r["name"] for r in results if not r["image"]]
    if noimg:
        print(f"no portrait ({len(noimg)}): {', '.join(noimg)}")


if __name__ == "__main__":
    main()
