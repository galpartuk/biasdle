"""Merge fetched data + hand corrections into the game payload, then render.

    roster.py  (groups, hand)          \
    groups_resolved.json (Wikidata)     >-- build.py --> data/game_data.json
    members_raw.json     (Wikidata)     /                web/template.html
    overrides.py (corrections, hand)   /                        |
    songs_resolved.json  (iTunes)     /                         v
                                                            index.html

The build refuses to emit a payload with a hole in a scored column: every member
in the answer pool must have group, company, nationality, generation, group
size, debut year, birth year and status, or it is dropped and reported. A blank
cell in a Loldle-style grid is worse than a missing entry — it reads as a hint.

Run: PYTHONIOENCODING=utf-8 python build/build.py
"""
import hashlib
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")

import overrides  # noqa: E402
from roster import PARENT  # noqa: E402

SCHEDULE_DAYS = 365
EPOCH = "2026-01-01"          # day 0 of the daily schedule


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def is_latin(s):
    """True for names a player can type on an English keyboard.

    Latin script, not ASCII: "Rose" is spelled Rosé and dropping her would
    silently shrink BLACKPINK to three members and corrupt the Members column.
    Hangul/Kana/Han labels are what we actually want to reject here.
    """
    if not s:
        return False
    stripped = "".join(c for c in unicodedata.normalize("NFKD", s)
                       if not unicodedata.combining(c))
    letters = [c for c in stripped if c.isalpha()]
    return bool(letters) and all(ord(c) < 128 for c in letters)


def slug(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


HANGUL = re.compile(r"^[가-힣ㄱ-ㆎ ]+$")


def hangul_of(group):
    """The group's Korean name, taken from roster aka strings.

    Shown as a typographic accent next to the Latin name. It is real content —
    what the group is actually called in Korean — not decoration, so it comes
    from the roster rather than being transliterated at render time.
    """
    for a in group.get("aka") or []:
        if HANGUL.match(a):
            return a
    return None


def searchable(*parts):
    """Lowercased, punctuation-free forms the search box should accept."""
    out = set()
    for p in parts:
        if not p:
            continue
        p = str(p)
        out.add(p.lower())
        out.add(re.sub(r"[^a-z0-9가-힣]", "", p.lower()))
        out.add(re.sub(r"[^a-z0-9가-힣 ]", " ", p.lower()).strip())
    return sorted(x for x in out if x)


# --------------------------------------------------------------------------
# members
# --------------------------------------------------------------------------
def build_members(groups_by_name, raw):
    stage_fix, unmatched = overrides.build_stage_map(raw)
    if unmatched:
        print("!! overrides._FIXES rows that did not match exactly one member:")
        for row in unmatched:
            print("   ", row)

    members, dropped = [], []
    for m in raw:
        if not m["groups"]:
            dropped.append((m.get("label"), "no group membership"))
            continue
        mem = m["groups"][0]
        g = groups_by_name.get(mem["group"])
        if not g:
            dropped.append((m.get("label"), f"unknown group {mem['group']}"))
            continue

        # Stage name: explicit override > ASCII pseudonym > label-derived.
        # The ASCII rule matters because P742 is often Hangul ("웬디"), which no
        # player is going to type into an English search box.
        name = stage_fix.get(m["qid"])
        if not name:
            name = m["stage"] if is_latin(m["stage"]) else None
        if not name:
            name = m["label"] if is_latin(m["label"]) else None
        if not name:
            dropped.append((m.get("label"), "no latin-script name"))
            continue

        if not m["birth"] or not m["birth"][:4].isdigit() \
                or m["birth"][:4] == "0000":
            dropped.append((name, overrides.EXCLUDE_REASON))
            continue

        nat = overrides.NATIONALITY.get((g["name"], name))
        if not nat:
            nat = [m["nationality"]] if m["nationality"] else []
        if not nat:
            dropped.append((name, "no nationality"))
            continue

        former = bool(mem.get("former"))
        if (g["name"], name) in overrides.NOT_FORMER:
            former = False
        if (g["name"], name) in overrides.FORCE_FORMER:
            former = True

        if g["status"] == "disbanded":
            status = "Disbanded group"
        elif former:
            status = "Former member"
        else:
            status = "Current member"

        members.append(dict(
            qid=m["qid"], name=name, group=g["name"],
            company=g["company"], parent=PARENT.get(g["company"], g["company"]),
            nationality=nat, gen=g["gen"],
            debut=int(g["debut"][:4]), birth=int(m["birth"][:4]),
            status=status,
            img=m["image"], enwiki=m.get("enwiki"),
            kr=hangul_of(g), tier=g.get("tier", 3),
            aliases=m.get("aliases") or [],
        ))

    # Group size is a scored column, so it must count the roster the game
    # actually knows about — not the Wikipedia number — or the arrows lie.
    sizes = {}
    for x in members:
        sizes[x["group"]] = sizes.get(x["group"], 0) + 1
    for x in members:
        x["size"] = sizes[x["group"]]

    # Disambiguate players who share a stage name across groups.
    counts = {}
    for x in members:
        counts[x["name"]] = counts.get(x["name"], 0) + 1
    for x in members:
        x["display"] = (f"{x['name']} ({x['group']})"
                        if counts[x["name"]] > 1 else x["name"])
        x["id"] = slug(f"{x['name']}-{x['group']}")
        x["search"] = searchable(x["name"], x["display"], x["group"],
                                 f"{x['group']} {x['name']}", *x["aliases"])
    return members, dropped


# --------------------------------------------------------------------------
# groups
# --------------------------------------------------------------------------
def build_groups(groups, members):
    by = {}
    for m in members:
        by.setdefault(m["group"], []).append(m)
    out = []
    for g in groups:
        mem = by.get(g["name"], [])
        if len(mem) < 2:
            continue
        foreign = sum(1 for m in mem
                      if "South Korean" not in m["nationality"])
        out.append(dict(
            id=slug(g["name"]), name=g["name"], company=g["company"],
            parent=PARENT.get(g["company"], g["company"]), gen=g["gen"],
            debut=int(g["debut"][:4]), debut_full=g["debut"],
            size=len(mem), foreign=foreign, kr=hangul_of(g),
            tier=g.get("tier", 3),
            status={"active": "Active", "disbanded": "Disbanded",
                    "inactive": "Inactive"}[g["status"]],
            search=searchable(g["name"], *(g.get("aka") or [])),
        ))
    return out


# --------------------------------------------------------------------------
# songs
# --------------------------------------------------------------------------
def build_songs(raw, groups_by_name):
    out = []
    for s in raw:
        g = groups_by_name.get(s["group"])
        if not g or not s.get("preview"):
            continue
        out.append(dict(
            id=slug(f"{s['group']}-{s['title']}"),
            group=s["group"], title=s["title"], kr=hangul_of(g),
            tier=g.get("tier", 3),
            track=s["track_id"], preview=s["preview"],
            art=s.get("artwork"), album=s.get("album"),
            # Deezer's search response carries no release date, so the result
            # card shows the release it came from instead of a bare year.
            year=(s.get("released") or "")[:4],
            search=searchable(s["title"], f"{s['group']} {s['title']}",
                              s.get("found_title")),
        ))
    return out


# --------------------------------------------------------------------------
# daily schedule
# --------------------------------------------------------------------------
TIER_WEIGHT = {1: 4, 2: 2, 3: 1}
MIN_GAP = 21            # days before the same answer may come round again


def schedule(items, salt, normalize_by_group=True):
    """Pre-rolled, popularity-weighted answer order for one year.

    Digimondle taught us not to hash the date at play time: a pure date hash
    can repeat an answer two days apart and there is no way to fix a bad roll
    without changing everyone's history. The order is rolled here instead, and
    is inspectable in the repo.

    The year is allocated purely by weight, with **no guarantee that every
    entry appears**. That is a deliberate call. With 223 members competing for
    365 days, reserving one slot each leaves only 142 to weight with, and the
    result is a Daily mode dominated by whoever has the most members — tripleS
    (24) outranking LE SSERAFIM (5) two tiers up, which is the exact problem
    the tiers exist to fix. Daily is the shop window and should be groups
    people know; **Endless plays the whole pool** and is where the deep cuts
    live.

    Weighting is also normalised per group, so a tier-1 group's total share is
    four times a tier-3 group's however many members it has.

    An earlier version piled weighted copies into one bag and took the first
    365, which left eleven groups out of the song year entirely. Counts are
    computed explicitly now, then laid out.
    """
    if not items:
        return []          # empty pool -> no schedule (never loop forever)

    def h(*parts):
        return hashlib.sha256("/".join((salt,) + parts).encode()).hexdigest()

    # Group-mode rows have no "group" key — they *are* the group.
    def gkey(x):
        return x.get("group", x["id"])

    per_group = {}
    for x in items:
        per_group[gkey(x)] = per_group.get(gkey(x), 0) + 1

    ids = [x["id"] for x in items]

    def apportion(keys, weights, days):
        """Largest-remainder split of `days` across `keys`."""
        tot = sum(weights[k] for k in keys) or 1.0
        exact = {k: days * weights[k] / tot for k in keys}
        got = {k: int(exact[k]) for k in keys}
        left = days - sum(got.values())
        for k in sorted(keys, key=lambda k: (-(exact[k] - int(exact[k])), h(k)))[:left]:
            got[k] += 1
        return got

    if normalize_by_group:
        # Two stages: days to groups, then a group's days across its members.
        # Doing it in one pass over 223 members hands the year to whoever has
        # the most members — 24 tripleS members each carrying a 0.41 remainder
        # collectively outvoted their own group's 10-day share and took 19.
        groups = sorted(per_group)
        gweight = {}
        for x in items:
            gweight[gkey(x)] = float(TIER_WEIGHT.get(x.get("tier", 3), 1))
        gdays = apportion(groups, gweight, SCHEDULE_DAYS)

        counts = {}
        for g in groups:
            mine = [x["id"] for x in items if gkey(x) == g]
            counts.update(apportion(mine, {i: 1.0 for i in mine}, gdays[g]))
    else:
        weight = {x["id"]: float(TIER_WEIGHT.get(x.get("tier", 3), 1))
                  for x in items}
        counts = apportion(ids, weight, SCHEDULE_DAYS)

    live = [i for i in ids if counts[i] > 0]
    if not live:
        return []

    # Spacing: the classic cooldown-scheduler greedy — always take whichever
    # entry has the most days left to place and is not inside the cooldown.
    # A naive "first one that fits" collapses to back-to-back repeats as soon
    # as one entry has many more slots than the rest.
    busiest = max(counts.values())
    gap = max(1, min(MIN_GAP, SCHEDULE_DAYS // busiest - 1))

    remaining = dict(counts)
    out = []
    while len(out) < SCHEDULE_DAYS:
        recent = set(out[-gap:])
        pool = [i for i in live if remaining[i] > 0 and i not in recent]
        if not pool:                       # cooldown boxed us in; relax it
            pool = [i for i in live if remaining[i] > 0]
            if not pool:
                break
        pick = max(pool, key=lambda i: (remaining[i], h(str(len(out)), i)))
        remaining[pick] -= 1
        out.append(pick)
    return out[:SCHEDULE_DAYS]


def render(payload):
    """Inline the payload into the template and write index.html.

    Single self-contained file, like dragonballdle and digimondle: no fetch at
    load time, so the page also works opened straight off the Desktop. Portraits
    and audio are the only things pulled at runtime.
    """
    tpl_path = os.path.join(ROOT, "web", "template.html")
    with open(tpl_path, encoding="utf-8") as f:
        tpl = f.read()
    css_path = os.path.join(ROOT, "web", "theme.css")
    with open(css_path, encoding="utf-8") as f:
        css = f.read()
    if "/*__CSS__*/" not in tpl:
        raise SystemExit("template.html lost its /*__CSS__*/ marker")
    tpl = tpl.replace("/*__CSS__*/", css, 1)

    marker = "/*__DATA__*/"
    if marker not in tpl:
        raise SystemExit("template.html lost its /*__DATA__*/ marker")
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # </script> inside a JSON string would close the script tag early.
    blob = blob.replace("</", "<\\/")
    head, _, tail = tpl.partition(marker)
    # Drop the inert placeholder literal that follows the marker.
    tail = re.sub(r'^\{"members".*?\}\};', ";", tail, count=1, flags=re.S)
    out = head + blob + tail
    dest = os.path.join(ROOT, "index.html")
    with open(dest, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"wrote {dest}  ({len(out)/1024:.0f} KB)")


def main():
    from roster import GROUPS as HAND_GROUPS
    resolved = load("groups_resolved.json")
    hand_by = {g["name"]: g for g in HAND_GROUPS}
    groups_meta = [dict(hand_by[g["name"]], **{k: g[k] for k in ("wd",)})
                   for g in resolved if g["name"] in hand_by]
    groups_by_name = {g["name"]: g for g in groups_meta}

    members, dropped = build_members(groups_by_name, load("members_raw.json"))
    groups = build_groups(groups_meta, members)
    known = {g["name"] for g in groups}
    members = [m for m in members if m["group"] in known]

    songs_raw = load("songs_resolved.json") \
        if os.path.exists(os.path.join(DATA, "songs_resolved.json")) else []
    songs = build_songs(songs_raw,
                        {n: groups_by_name[n] for n in known})

    payload = dict(
        members=members, groups=groups, songs=songs,
        epoch=EPOCH,
        schedules=dict(
            member=schedule(members, "member/v1"),
            group=schedule(groups, "group/v1", normalize_by_group=False),
            image=schedule([m for m in members if m["img"]], "image/v1"),
            song=schedule(songs, "song/v1", normalize_by_group=False),
        ),
    )

    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "game_data.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    render(payload)

    print(f"members : {len(members)}  (with portrait: "
          f"{sum(1 for m in members if m['img'])})")
    print(f"groups  : {len(groups)}")
    print(f"songs   : {len(songs)}")
    if dropped:
        print(f"\ndropped {len(dropped)}:")
        for name, why in dropped:
            print(f"   {name}: {why}")
    return payload


if __name__ == "__main__":
    main()
