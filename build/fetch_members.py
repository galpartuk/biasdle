"""Pull the member list for every resolved group, with the facts the game needs.

Per member we want:
  stage name   P742 (pseudonym) if present, else derived from the label
  birth date   P569
  nationality  P27 (country of citizenship) -> demonym
  portrait     P18 (Commons file) -> Special:FilePath URL at runtime
  former?      P527 claim qualifier P582 (end time) on the *group* side

Sanity checks that get reported rather than silently swallowed:
  - P21 (sex or gender) should be female; anything else is flagged
  - a member with no birth date is flagged (birth-year is a grid column)
  - a member with no portrait is flagged (Image mode needs one)

Writes data/members_raw.json + a coverage report.
Run: PYTHONIOENCODING=utf-8 python build/fetch_members.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wdapi  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
GROUPS_IN = os.path.join(DATA, "groups_resolved.json")
OUT = os.path.join(DATA, "members_raw.json")

FEMALE = {"Q6581072": "female", "Q1052281": "trans woman",
          "Q48270": "non-binary"}

# P27 country QID -> the label the grid shows.
NATIONALITY = {
    "Q884": "South Korean", "Q17": "Japanese", "Q148": "Chinese",
    "Q865": "Taiwanese", "Q869": "Thai", "Q30": "American",
    "Q408": "Australian", "Q881": "Vietnamese", "Q16": "Canadian",
    "Q145": "British", "Q8646": "Hong Konger", "Q334": "Singaporean",
    "Q928": "Filipino", "Q252": "Indonesian", "Q717": "Venezuelan",
    "Q39": "Swiss", "Q142": "French", "Q29": "Spanish", "Q155": "Brazilian",
    "Q833": "Malaysian", "Q183": "German", "Q664": "New Zealander",
    "Q843": "Pakistani", "Q668": "Indian", "Q902": "Bangladeshi",
    "Q800": "Costa Rican", "Q96": "Mexican", "Q414": "Argentine",
}

# Korean romanised labels are "Family Given" ("Park Ji-hyo"); Japanese ones on
# Wikidata are inconsistent ("Minatozaki Sana" but also "Mina Myoi"). The stage
# name is what players type, so guessing it from the label is a fallback only —
# every derived name lands in the review report for a human to confirm.
KOREAN_SURNAMES = {
    "kim", "lee", "park", "choi", "jung", "jeong", "kang", "cho", "jo", "yoon",
    "yun", "jang", "lim", "im", "han", "oh", "seo", "shin", "kwon", "hwang",
    "ahn", "an", "song", "yoo", "yu", "hong", "jeon", "jun", "ko", "go", "moon",
    "mun", "son", "yang", "bae", "baek", "paek", "heo", "heo", "nam", "no",
    "roh", "ha", "gwak", "kwak", "sung", "seong", "cha", "joo", "ju", "woo",
    "u", "min", "chu", "chun", "jin", "ryu", "ryoo", "pyo", "gu", "koo", "ku",
    "myung", "myeong", "byun", "byeon", "gil", "kil", "won", "wi", "yeo",
}


def derive_stage_name(label_en, pseudonyms):
    if pseudonyms:
        # Prefer the shortest pseudonym: stage names are short by design.
        return sorted(pseudonyms, key=len)[0], "P742"
    if not label_en:
        return None, "none"
    parts = label_en.replace("-", " ").split()
    if len(parts) >= 2 and parts[0].lower().strip(",") in KOREAN_SURNAMES:
        # "Park Ji-hyo" -> "Jihyo"; keep the hyphen out, players don't type it.
        rest = label_en.split(None, 1)[1]
        return rest.replace("-", "").replace(" ", ""), "surname-strip"
    return label_en, "label"


def main():
    with open(GROUPS_IN, encoding="utf-8") as f:
        groups = json.load(f)
    groups = [g for g in groups if g.get("wd")]

    # 1) group entities -> P527 claims (member QID + optional end time)
    gents = wdapi.get_entities([g["wd"] for g in groups], props="claims|labels")
    membership = {}   # member qid -> list of (group, former, since, until)
    order = []
    for g in groups:
        ent = gents.get(g["wd"], {})
        for c in wdapi.claims(ent, "P527"):
            if c.get("rank") == "deprecated":
                continue
            dv = c.get("mainsnak", {}).get("datavalue")
            if not dv or not isinstance(dv.get("value"), dict):
                continue
            mq = dv["value"].get("id")
            if not mq:
                continue
            until = wdapi.wtime(wdapi.qualifier(c, "P582"))
            since = wdapi.wtime(wdapi.qualifier(c, "P580"))
            membership.setdefault(mq, []).append(
                dict(group=g["name"], former=bool(until), since=since,
                     until=until))
            if mq not in order:
                order.append(mq)

    print(f"{len(order)} distinct member QIDs across {len(groups)} groups")

    # 2) member entities
    ments = wdapi.get_entities(order, props="claims|labels|aliases|sitelinks")
    wdapi.save()

    out = []
    flags = {"no_birth": [], "no_image": [], "not_female": [],
             "no_nationality": [], "derived_name": [], "multi_group": []}

    for mq in order:
        e = ments.get(mq)
        if not e:
            continue
        lbl = wdapi.label(e)
        pseudo = [v for v in wdapi.values(e, "P742") if isinstance(v, str)]
        stage, how = derive_stage_name(lbl, pseudo)

        birth = wdapi.wtime(wdapi.first(e, "P569"))
        gender = [v["id"] for v in wdapi.values(e, "P21")
                  if isinstance(v, dict) and "id" in v]
        cits = [v["id"] for v in wdapi.values(e, "P27")
                if isinstance(v, dict) and "id" in v]
        nat = next((NATIONALITY[c] for c in cits if c in NATIONALITY), None)
        img = next((v for v in wdapi.values(e, "P18") if isinstance(v, str)),
                   None)
        enwiki = (e.get("sitelinks", {}).get("enwiki") or {}).get("title")
        aliases = [a["value"] for a in e.get("aliases", {}).get("en", [])]

        groups_of = membership.get(mq, [])
        rec = dict(qid=mq, label=lbl, stage=stage, stage_src=how, birth=birth,
                   nationality=nat, citizenships=cits, image=img,
                   enwiki=enwiki, aliases=aliases, groups=groups_of,
                   pseudonyms=pseudo)
        out.append(rec)

        who = f"{stage or lbl} ({groups_of[0]['group'] if groups_of else '?'})"
        if not birth:
            flags["no_birth"].append(who)
        if not img:
            flags["no_image"].append(who)
        if gender and not any(gq in FEMALE for gq in gender):
            flags["not_female"].append(f"{who} P21={gender}")
        if not nat:
            flags["no_nationality"].append(f"{who} P27={cits}")
        if how != "P742":
            flags["derived_name"].append(f"{who} <- {lbl!r} [{how}]")
        if len(groups_of) > 1:
            flags["multi_group"].append(
                f"{stage}: {[x['group'] for x in groups_of]}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    n = len(out)
    print(f"\nwrote {n} members -> {OUT}\n")
    print("--- COVERAGE ---")
    print(f"birth date  {n - len(flags['no_birth']):>3}/{n}")
    print(f"portrait    {n - len(flags['no_image']):>3}/{n}")
    print(f"nationality {n - len(flags['no_nationality']):>3}/{n}")
    print(f"stage name from P742 {n - len(flags['derived_name']):>3}/{n}")
    for k, v in flags.items():
        if v:
            print(f"\n## {k} ({len(v)})")
            for x in v[:40]:
                print("   ", x)
            if len(v) > 40:
                print(f"    ... +{len(v) - 40} more")


if __name__ == "__main__":
    main()
