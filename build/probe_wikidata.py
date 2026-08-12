"""Probe: does Wikidata know K-pop girl group members well enough to seed the roster?

Uses the Wikidata **Action API** (wbsearchentities / wbgetentities), not WDQS/SPARQL —
the query service is rate-limited to 1 req/min during outages and is not dependable.

Flow: group name -> QID -> P527 (has part: member) -> batch-fetch members ->
report coverage of P569 birth, P2048 height, P27 citizenship, P18 image.

Run: python build/probe_wikidata.py
"""
import json
import time
import urllib.parse
import urllib.request

API = "https://www.wikidata.org/w/api.php"
UA = {"User-Agent": "kpopdle-probe/0.1 (hobby daily guessing game)"}

GROUPS = [
    "TWICE", "BLACKPINK", "IVE", "NewJeans", "aespa", "LE SSERAFIM",
    "ITZY", "Red Velvet", "(G)I-DLE", "STAYC", "Girls' Generation", "MAMAMOO",
]


def get(params):
    params = dict(params, format="json")
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def find_qid(name):
    d = get({"action": "wbsearchentities", "search": name, "language": "en",
             "type": "item", "limit": 8})
    for hit in d.get("search", []):
        desc = (hit.get("description") or "").lower()
        if any(k in desc for k in ("girl group", "group", "band", "musical")):
            return hit["id"], hit.get("description", "")
    if d.get("search"):
        h = d["search"][0]
        return h["id"], h.get("description", "")
    return None, None


def entities(qids):
    out = {}
    for i in range(0, len(qids), 45):
        chunk = qids[i:i + 45]
        d = get({"action": "wbgetentities", "ids": "|".join(chunk),
                 "props": "claims|labels", "languages": "en|ko"})
        out.update(d.get("entities", {}))
        time.sleep(0.3)
    return out


def claim_vals(ent, prop):
    return [c["mainsnak"].get("datavalue", {}).get("value")
            for c in ent.get("claims", {}).get(prop, [])
            if c["mainsnak"].get("datavalue")]


tot = {"n": 0, "birth": 0, "height": 0, "country": 0, "img": 0}
for gname in GROUPS:
    qid, desc = find_qid(gname)
    if not qid:
        print(f"\n=== {gname}: NOT FOUND")
        continue
    gent = entities([qid])[qid]
    member_qids = [v["id"] for v in claim_vals(gent, "P527")
                   if isinstance(v, dict) and "id" in v]
    print(f"\n=== {gname} ({qid} — {desc}) -> {len(member_qids)} P527 members")
    if not member_qids:
        continue
    ments = entities(member_qids)
    for mq in member_qids:
        m = ments.get(mq, {})
        lbl = m.get("labels", {}).get("en", {}).get("value", mq)
        birth = claim_vals(m, "P569")
        b = birth[0]["time"][1:11] if birth else ""
        h = claim_vals(m, "P2048")
        hv = h[0]["amount"].lstrip("+") if h else ""
        c = claim_vals(m, "P27")
        img = claim_vals(m, "P18")
        print(f"   {lbl:<22} birth={b:<11} h={hv:<6} cit={'Y' if c else '-'} "
              f"img={'Y' if img else '-'}")
        tot["n"] += 1
        tot["birth"] += bool(b)
        tot["height"] += bool(hv)
        tot["country"] += bool(c)
        tot["img"] += bool(img)
    time.sleep(0.3)

print("\n--- COVERAGE ---")
n = max(tot["n"], 1)
for k in ("birth", "height", "country", "img"):
    print(f"{k:<8} {tot[k]:>3}/{tot['n']}  ({100*tot[k]//n}%)")
