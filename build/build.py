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


def load_photos():
    """Stage photos from build/fetch_photos.py, keyed subject -> [filename].

    Optional on purpose: the build must not depend on a 20-minute Commons
    crawl having been run. Without it everyone simply keeps their P18 portrait.
    """
    path = os.path.join(DATA, "photos.json")
    if not os.path.exists(path):
        print("(no data/photos.json — run build/fetch_photos.py for stage "
              "photos; falling back to P18 portraits)")
        return {}
    with open(path, encoding="utf-8") as f:
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
    """Match keys for the search box, **already normalised**.

    Pre-normalising here rather than in the browser matters now the song pool
    is thousands of tracks: candidates() runs on every keystroke, and folding
    three variants per entry at that point is tens of thousands of regex passes
    per character typed. The query is folded the same way, so a space in
    "won young" costs nothing.
    """
    out = set()
    for p in parts:
        if not p:
            continue
        # NFKD first, exactly like the browser's norm(): without it "Rosé"
        # folds to "ros" here and to "rose" there, and she becomes unfindable.
        t = unicodedata.normalize("NFKD", str(p).lower())
        t = "".join(c for c in t if not unicodedata.combining(c))
        out.add(re.sub(r"[^a-z0-9가-힣]", "", t))
    return sorted(x for x in out if x)


# --------------------------------------------------------------------------
# members
# --------------------------------------------------------------------------
def pick_membership(memberships, groups_by_name):
    """Which group a member belongs to, when she belongs to more than one.

    IZ*ONE's line-up overlaps heavily with IVE, LE SSERAFIM and Kep1er, and
    taking the first membership Wikidata happens to list put Sakura in IZ*ONE
    and gave her Off The Record as a label. The group she is *currently* in
    wins; a member who only ever had the disbanded one keeps it.
    """
    known = [x for x in memberships if x["group"] in groups_by_name]
    if not known:
        return None

    def rank(x):
        g = groups_by_name[x["group"]]
        return (
            0 if not x.get("former") else 1,          # still in it
            0 if g["status"] == "active" else 1,      # group still going
            -int(g["debut"][:4]),                     # the more recent one
        )
    return sorted(known, key=rank)[0]



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
        mem = pick_membership(m["groups"], groups_by_name)
        if not mem:
            dropped.append((m.get("label"), "no known group"))
            continue
        g = groups_by_name[mem["group"]]

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

        # Leaving comes first. Checking the group's fate first told a member
        # who quit in 2019 that she was "Disbanded" because the group folded in
        # 2021 — two different facts, and the wrong one was winning.
        if former:
            status = "Left"
        elif g["status"] == "disbanded":
            status = "Disbanded"
        elif g["status"] == "inactive":
            status = "Inactive"
        else:
            status = "Active"

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
        # The debut line-up, not the current one: members leave, they are
        # almost never added, so everyone we ship IS the original line-up —
        # except where overrides.ORIGINAL_SIZE says otherwise.
        x["size"] = overrides.ORIGINAL_SIZE.get(x["group"], sizes[x["group"]])

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

    photos = load_photos()
    for x in members:
        got = photos.get("member:" + x["id"])
        if got:
            x["imgs"] = got
    return members, dropped


# --------------------------------------------------------------------------
# soloists
# --------------------------------------------------------------------------
def build_soloists(members):
    """Fold soloists into the member pool.

    They share group "Soloist" and size 1 because every member column here is
    derived from a group and a soloist has none. The other six columns stay
    real, so a guess still scores properly against them. The group she came
    from rides along as `former` and is shown on the answer card only — making
    it a scored column would mean adding I.O.I, IZ*ONE, SNSD and Wonder Girls
    as full roster entries, and they are outside this game's scope.
    """
    path = os.path.join(DATA, "soloists_resolved.json")
    if not os.path.exists(path):
        print("(no data/soloists_resolved.json — run "
              "build/resolve_soloists.py to include soloists)")
        return []
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    photos = load_photos()
    out, skipped = [], []
    for r in raw:
        rec = dict(
            qid=r["wd"], name=r["name"], group="Soloist",
            company=r["company"], parent=PARENT.get(r["company"], r["company"]),
            nationality=r["nationality"], gen=r["gen"],
            debut=int(r["debut"][:4]), birth=int(r["birth"][:4]),
            status="Soloist", size=1, tier=r.get("tier", 2),
            img=r.get("image"), kr=r.get("kr"), former=r.get("former"),
            display=r["name"], id=slug(r["name"] + "-soloist"),
        )
        rec["search"] = searchable(r["name"], "soloist",
                                   *(r.get("aka") or []),
                                   *( [r["former"]] if r.get("former") else [] ))
        got = photos.get("member:" + rec["id"])
        if got:
            rec["imgs"] = got
        out.append(rec)
    return out


# --------------------------------------------------------------------------
# groups
# --------------------------------------------------------------------------
def build_groups(groups, members):
    photos = load_photos()
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
            size=overrides.ORIGINAL_SIZE.get(g["name"], len(mem)),
            foreign=foreign, kr=hangul_of(g),
            tier=g.get("tier", 3), img=g.get("image"),
            imgs=photos.get("group:" + g["name"]) or None,
            status={"active": "Active", "disbanded": "Disbanded",
                    "inactive": "Inactive"}[g["status"]],  # noqa: E501
            search=searchable(g["name"], *(g.get("aka") or [])),
        ))
    return out


# --------------------------------------------------------------------------
# songs
# --------------------------------------------------------------------------
ART_PREFIX = "https://e-cdns-images.dzcdn.net/images/cover/"
ART_SUFFIX = "/500x500-000000-80-0-0.jpg"


def build_songs(raw, groups_by_name):
    """Curated title tracks plus, if it has been fetched, the full catalogue.

    Two pools in one list. `single: 1` marks the hand-curated title tracks;
    Daily draws only from those, because a shared daily puzzle should be a song
    people have heard. Endless plays everything, B-sides included — which is
    the whole point of pulling discographies rather than typing titles.

    Catalogue tracks carry no preview URL. Deezer signs those with an hour-long
    expiry so they are resolved at play time from the track id anyway, and
    storing ~3000 of them would add half a megabyte of dead text to the page.
    """
    out, seen = [], set()

    def add(group, title, track, art, album, year, preview, single, by=None):
        g = groups_by_name.get(group)
        if not g or not track:
            return
        # The Deezer track id, not a slug of the title: a title written only in
        # Hangul slugs to nothing, so "BLACKPINK - 해바라기" collided with the
        # BLACKPINK group entry.
        sid = "t" + str(track)
        if sid in seen:
            return
        seen.add(sid)
        keys = [title, f"{group} {title}"]
        if by:
            # A solo release is filed under the group but people look for it by
            # the member's name — "yuna ice cream" has to find it.
            keys += [by, f"{by} {title}"]
        # Deliberately lean: 3,300 songs make every field expensive on a
        # phone. `id` is derivable from `track`, `kr`/`tier`/`gen` are
        # properties of the group and are looked up at runtime, and `art` is
        # stored as the cover hash rather than an 85-character URL. Together
        # that is roughly a third of the payload.
        rec = dict(
            id=sid, group=group, title=title, track=track,
            art=art, album=album, year=year,
            search=searchable(*keys),
        )
        if by:
            rec["by"] = by
        if single:
            rec["single"] = 1
        # No stored preview URL. Deezer signs them with an hour-long expiry, so
        # a build-time URL is wrong by the time anyone loads the page, and it
        # cannot serve as an offline fallback either — playing it needs the
        # network anyway. Resolved from the track id at play time.
        out.append(rec)

    for s in raw:
        if not s.get("preview"):
            continue
        # Curated rows carry a full artwork URL from the earlier pipeline;
        # keep only the hash so both sources store the same shape.
        art = s.get("artwork") or ""
        m = re.search(r"/cover/([0-9a-f]{32})/", art)
        add(s["group"], s["title"], s.get("track_id"),
            m.group(1) if m else None, s.get("album"),
            (s.get("released") or "")[:4], None, True)

    path = os.path.join(DATA, "catalogue.json")
    if not os.path.exists(path):
        print("(no data/catalogue.json — run build/fetch_catalogue.py for "
              "B-sides and album tracks)")
        return out
    with open(path, encoding="utf-8") as f:
        cat = json.load(f)
    for group, tracks in cat.items():
        for t in tracks:
            add(group, t["title"], t.get("track_id"), t.get("art_md5") or None,
                t.get("album"),
                (t.get("released") or "")[:4], None, False, t.get("by"))
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

    def weight_of(x):
        return float(TIER_WEIGHT.get(x.get("tier", 3), 1))

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

    # Floor: every distinct artist gets at least one day. Without this, adding
    # 78 solo tracks to the song pool pushed WJSN, EVERGLOW, Rocket Punch,
    # Weeekly, PURPLE KISS and Billlie out of the year entirely — their share
    # simply rounded to zero. Silence is worse than rarity.
    owner = {x["id"]: gkey(x) for x in items}
    best_of = {}
    for x in items:
        g = gkey(x)
        if g not in best_of or weight_of(x) > weight_of(best_of[g]):
            best_of[g] = x
    for g, rep in best_of.items():
        if sum(counts[i] for i in ids if owner[i] == g):
            continue
        donor = max(ids, key=lambda i: counts[i])
        if counts[donor] > 1:
            counts[donor] -= 1
            counts[rep["id"]] += 1

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
    groups_meta = [dict(hand_by[g["name"]],
                        **{k: g.get(k) for k in ("wd", "image")})
                   for g in resolved if g["name"] in hand_by]
    groups_by_name = {g["name"]: g for g in groups_meta}

    members, dropped = build_members(groups_by_name, load("members_raw.json"))
    groups = build_groups(groups_meta, members)
    solo = build_soloists(members)
    known = {g["name"] for g in groups}
    members = [m for m in members if m["group"] in known]

    # An active soloist is filed as a soloist, not as a member of the group she
    # used to be in. Kwon Eunbi, Choi Yena and Jo Yuri are soloists now; their
    # IZ*ONE bandmates who did not go solo stay IZ*ONE members who left. The
    # group's Members column is unaffected — it is the pinned debut line-up.
    solo_qids = {x["qid"] for x in solo if x.get("qid")}
    moved = [m["name"] for m in members if m.get("qid") in solo_qids]
    members = [m for m in members if m.get("qid") not in solo_qids] + solo
    if moved:
        print(f"filed as soloists rather than group members: {', '.join(moved)}")

    # Redo the shared-name disambiguation now the pools are merged: two people
    # can be called Yubin, and the player has to be able to tell which is which.
    # Case-insensitively: the soloist is "Yubin" and tripleS's is "YuBin", which
    # a player cannot tell apart in a dropdown.
    seen = {}
    for x in members:
        seen[x["name"].lower()] = seen.get(x["name"].lower(), 0) + 1
    for x in members:
        x["display"] = (f"{x['name']} ({x['group']})"
                        if seen[x["name"].lower()] > 1 else x["name"])
        x["search"] = sorted(set(x["search"]) | set(searchable(x["display"])))

    songs_raw = load("songs_resolved.json") \
        if os.path.exists(os.path.join(DATA, "songs_resolved.json")) else []
    # Soloists are not in groups_by_name but their tracks still need a
    # generation, tier and Korean name, so they join the lookup by hand.
    song_owners = {n: groups_by_name[n] for n in known}
    for x in solo:
        song_owners[x["name"]] = dict(gen=x["gen"], tier=x["tier"],
                                      aka=[x["kr"]] if x.get("kr") else [])
    songs = build_songs(songs_raw, song_owners)

    payload = dict(
        members=members, groups=groups, songs=songs,
        # Shipped so the test suite can assert the Members column exactly:
        # where a line-up is pinned the column follows the pin, everywhere else
        # it follows the roster.
        original_size=overrides.ORIGINAL_SIZE,
        epoch=EPOCH,
        schedules=dict(
            member=schedule(members, "member/v1"),
            group=schedule(groups, "group/v1", normalize_by_group=False),
            # anyone with a picture at all, portrait or stage photo
            image=schedule([m for m in members if m.get("img") or m.get("imgs")],
                           "image/v1"),
            # Daily uses the curated title tracks only. A shared daily puzzle
            # built on album cuts would be unfair; Endless has all of them.
            song=schedule([x for x in songs if x.get("single")], "song/v1",
                          normalize_by_group=False),
        ),
    )

    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "game_data.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    render(payload)

    print(f"members : {len(members)}  ({len(solo)} soloists; with portrait: "
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
