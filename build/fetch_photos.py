"""Collect live-performance photos for every member and group.

The portraits from Wikidata P18 are press shots, airport departures and red
carpets — accurate, and dull. Commons also holds thousands of CC-licensed
*stage* photos taken by fans at music shows and concerts; they are simply not
what P18 points at. This script finds them.

Pipeline, and why each step is the way it is:

  1. **P373 -> Commons category.** 31/31 groups and most members have one.
  2. **deepcat search, not a category crawl.** Commons nests these as
     `X` -> `X by year` -> `X in 2019` -> `X at Coachella 2019`, so walking
     `list=categorymembers` misses a level and takes ~40s per group.
     CirrusSearch's `deepcat:"X"` expands the whole tree server-side.
  3. **Classify on filename + the file's own categories + description.**
     Filenames alone are useless here: the dominant convention is Korean and
     date-prefixed (`170923 마마무 04.jpg`), which says nothing.
  4. **Rank by orientation.** A stage keyword tells you the file is from a stage
     EVENT, not that the photo is usable. The discriminator that actually works
     is aspect: portrait crops are fansite close-ups of one person, wide
     landscape frames are whole-stage shots where the face is 12 pixels tall.

Writes data/photos.json as {subject id: [filename, ...]}, ranked, capped.
`img` (P18) stays in the payload untouched as the fallback: filename lists rot
as Commons renames and deletes, and about 40% of members have no stage photo at
all.

Run: PYTHONIOENCODING=utf-8 python build/fetch_photos.py
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DATA = os.path.join(HERE, "..", "data")
CACHE = os.path.join(DATA, "photo_cache.json")
OUT = os.path.join(DATA, "photos.json")

COMMONS = "https://commons.wikimedia.org/w/api.php"
UA = ("biasdle/0.1 (https://github.com/galpartuk/biasdle; hobby daily guessing "
      "game) python-urllib")
MIN_INTERVAL = 0.4
_last = [0.0]
_cache = None

MAX_PER_SUBJECT = 12
PORTRAIT_MIN = 1.15     # taller than this is a crop of a person
PORTRAIT_MAX = 2.0      # taller than this is a full-body strip, face unusable
GROUP_MIN_W = 900       # a group shot has to be wide enough to hold everyone


# ---------------------------------------------------------------------------
# classification vocabulary
#
# Every Latin token is \b-anchored. Learned the hard way while this was being
# researched: an unanchored r"elle\b" (the magazine) matches "Gis-elle" and
# silently vetoes every photo of aespa's Giselle.
# ---------------------------------------------------------------------------
STAGE = [
    r"music bank", r"m ?countdown", r"엠카운트다운", r"뮤직뱅크", r"inkigayo", r"인기가요",
    r"show ?champion", r"쇼챔피언", r"music core", r"음악중심", r"\bthe show\b", r"더쇼",
    r"simply k-?pop", r"\bconcert", r"콘서트", r"\btour\b", r"투어", r"\bstage\b", r"무대",
    r"showcase", r"쇼케이스", r"perform", r"festival", r"페스티벌", r"축제",
    r"\blive\b", r"라이브", r"\bgig\b", r"kcon\b", r"dream concert", r"드림콘서트",
    r"gayo daejun", r"가요대전", r"gayo daejeon", r"song festival", r"encore", r"앵콜",
    r"rehearsal", r"soundcheck", r"summer sonic", r"lollapalooza", r"coachella",
    r"waterbomb", r"워터밤", r"guerrilla", r"게릴라", r"busking", r"버스킹",
    r"fan ?meeting", r"팬미팅", r"world tour", r"comeback show", r"\bsinging\b",
]
NOT_STAGE = [
    r"\bairport\b", r"공항", r"red ?carpet", r"레드카펫", r"\bpress\b", r"기자",
    r"photo ?call", r"포토콜", r"\binterview", r"인터뷰", r"fan ?sign", r"팬사인",
    r"\bsigning\b", r"사인회", r"\bposter\b", r"포스터", r"\blogo", r"\bbanner\b",
    r"\bbillboard\b", r"advertis", r"광고", r"\bcf\b", r"\bwax\b", r"\bstatue\b",
    r"album cover", r"lightstick", r"응원봉", r"\bcafe\b", r"카페", r"birthday", r"생일",
    r"\bsubway\b", r"지하철", r"bus ?stop", r"screenshot", r"wordmark",
    r"\bmap\b", r"\bchart\b", r"\bgraph\b", r"timeline", r"discography",
    r"signature", r"autograph", r"\barrival\b", r"\bdeparture\b", r"\bentering\b",
    r"\bleaving\b", r"going to", r"heading to", r"on the way", r"출국", r"입국",
    # 출근(길) = "on the way to work": the walk INTO the Music Bank building,
    # which is the airport photo of music shows. 퇴근 is the walk out.
    r"출근", r"퇴근", r"등교",
    r"press conference", r"\bshowroom\b", r"pop-?up", r"팝업", r"\bplacard\b",
    r"\bslogan\b", r"\bmerch\b",
    # An event name is not a stage: a "Dream Concert" file is as likely to be
    # the photo wall outside it as the performance.
    r"photo ?wall", r"포토월", r"포토타임", r"photo ?time", r"화보", r"매거진",
    r"\bmagazine\b", r"\bvogue\b", r"\belle\b", r"marie ?claire", r"harper's",
    r"cosmopolitan", r"\bdazed\b", r"\ballure\b", r"\besquire\b", r"\bw korea\b",
    r"photoshoot", r"photo shoot", r"\bambassador\b", r"\bendorse",
    r"fashion week", r"\bdior\b", r"\bchanel\b", r"\bgucci\b", r"\bprada\b",
    r"\bbulgari\b", r"\bcartier\b", r"\btiffany\b", r"\bolens\b",
    r"idols in advertising",
]
BAD_EXT = (".svg", ".ogg", ".ogv", ".webm", ".pdf", ".mid", ".wav", ".mp3",
           ".oga", ".flac", ".tif", ".tiff", ".gif", ".xcf", ".djvu")
STAGE_RE = re.compile("|".join(STAGE), re.I)
NOT_RE = re.compile("|".join(NOT_STAGE), re.I)


# ---------------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------------
def cache():
    global _cache
    if _cache is None:
        _cache = json.load(open(CACHE, encoding="utf-8")) \
            if os.path.exists(CACHE) else {}
    return _cache


def save_cache():
    os.makedirs(DATA, exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache(), f, ensure_ascii=False)


def api(endpoint, params, retries=5):
    params = dict(params, format="json", formatversion="2")
    key = endpoint + "?" + urllib.parse.urlencode(sorted(params.items()))
    c = cache()
    if key in c:
        return c[key]
    delay = 3.0
    for attempt in range(retries):
        gap = MIN_INTERVAL - (time.time() - _last[0])
        if gap > 0:
            time.sleep(gap)
        try:
            req = urllib.request.Request(
                endpoint + "?" + urllib.parse.urlencode(params),
                headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode("utf-8"))
            _last[0] = time.time()
            c[key] = d
            if len(c) % 40 == 0:
                save_cache()
            return d
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                json.JSONDecodeError) as e:
            _last[0] = time.time()
            print(f"    retry ({e}) in {delay:.0f}s")
            time.sleep(delay)
            delay = min(delay * 2, 60)
    # Deliberately not cached: an empty answer here means the API would not
    # talk to us, not that the subject has no photos.
    print(f"    GAVE UP on {params.get('srsearch') or params.get('ids') or key[:60]}")
    return {}


# ---------------------------------------------------------------------------
# 1. subjects -> Commons category (Wikidata P373)
# ---------------------------------------------------------------------------
def commons_cats(subjects):
    import wdapi
    qids = [s["qid"] for s in subjects if s.get("qid")]
    ents = wdapi.get_entities(qids, props="claims")
    wdapi.save()
    out = {}
    for s in subjects:
        e = ents.get(s.get("qid") or "", {})
        cat = next((v for v in wdapi.values(e, "P373") if isinstance(v, str)),
                   None)
        if cat:
            out[s["id"]] = cat
    return out


# ---------------------------------------------------------------------------
# 2. deepcat search
# ---------------------------------------------------------------------------
def deep_files(cat, cap=400):
    files, offset = [], 0
    while len(files) < cap:
        d = api(COMMONS, {"action": "query", "list": "search",
                          "srsearch": f'deepcat:"{cat}"',
                          "srnamespace": "6", "srlimit": "max",
                          "sroffset": str(offset)})
        hits = d.get("query", {}).get("search", [])
        if not hits:
            break
        files += [h["title"][5:] for h in hits]
        cont = d.get("continue", {}).get("sroffset")
        if cont is None:
            break
        offset = cont
    return files[:cap]


# ---------------------------------------------------------------------------
# 3. file metadata
# ---------------------------------------------------------------------------
def file_meta(names):
    out = {}
    todo = sorted(set(n for n in names if not n.lower().endswith(BAD_EXT)))
    # Korean filenames percent-encode to ~9 bytes a character, so 50 titles can
    # blow past the URL length limit and earn a 414. Batch by encoded length.
    batches, cur, curlen = [], [], 0
    for n in todo:
        ln = len(urllib.parse.quote("File:" + n)) + 3
        if cur and (curlen + ln > 4500 or len(cur) >= 45):
            batches.append(cur)
            cur, curlen = [], 0
        cur.append(n)
        curlen += ln
    if cur:
        batches.append(cur)

    for i, chunk in enumerate(batches):
        d = api(COMMONS, {
            "action": "query",
            "titles": "|".join("File:" + c for c in chunk),
            "prop": "imageinfo|categories", "cllimit": "max",
            "clshow": "!hidden", "iiprop": "size|mime|extmetadata",
            "iiextmetadatafilter": "LicenseShortName|ImageDescription"})
        for p in d.get("query", {}).get("pages", []):
            ii = (p.get("imageinfo") or [{}])[0]
            # A file with no extmetadata comes back as an empty *list*, not an
            # empty dict, and .get() on it raises. Roughly 1 file in 2000.
            em = ii.get("extmetadata")
            if not isinstance(em, dict):
                em = {}
            out[p["title"][5:]] = {
                "w": ii.get("width"), "h": ii.get("height"),
                "mime": ii.get("mime"),
                "lic": (em.get("LicenseShortName") or {}).get("value"),
                "desc": re.sub(r"<[^>]+>", " ",
                               (em.get("ImageDescription") or {}).get("value", ""))[:400],
                "cats": [c["title"][9:] for c in p.get("categories", [])],
            }
        if i % 15 == 0:
            print(f"    meta {i * 45}/{len(todo)}")
            save_cache()
    return out


# ---------------------------------------------------------------------------
# 4. classify + rank
# ---------------------------------------------------------------------------
def is_stage(fn, m):
    if fn.lower().endswith(BAD_EXT):
        return False
    mime = m.get("mime") or ""
    if mime and not mime.startswith("image/"):
        return False
    if mime == "image/svg+xml":
        return False
    w, h = m.get("w") or 0, m.get("h") or 0
    if w < 400 or h < 400:
        return False
    # Veto on filename + categories only. Descriptions are long free text and
    # often mention the photographer's other work, so a NOT hit there is not
    # evidence about this picture.
    veto = " ".join([fn] + (m.get("cats") or []))
    if NOT_RE.search(veto):
        return False
    return bool(STAGE_RE.search(veto + " " + (m.get("desc") or "")))


def flat(t):
    """Drop the separators romanisations disagree about.

    Our roster says "Miyeon"; Commons files say "Cho Mi-yeon". Without this the
    solo-shot filter misses every hyphenated credit and a group card ends up
    showing one member.
    """
    return re.sub(r"[-_.·\s]+", "", t)


def rank_key(fn, meta):
    m = meta.get(fn, {})
    w, h = m.get("w") or 1, m.get("h") or 1
    return (-(h / w), -(m.get("h") or 0))


def main():
    groups = json.load(open(os.path.join(DATA, "groups_resolved.json"),
                            encoding="utf-8"))
    members = json.load(open(os.path.join(DATA, "members_raw.json"),
                             encoding="utf-8"))
    game = json.load(open(os.path.join(DATA, "game_data.json"),
                          encoding="utf-8"))
    live_groups = {g["name"] for g in game["groups"]}

    subjects = []
    for g in groups:
        if g.get("wd") and g["name"] in live_groups:
            subjects.append(dict(id="group:" + g["name"], kind="group",
                                 name=g["name"], qid=g["wd"]))
    by_qid = {m["qid"]: m for m in members}
    for m in game["members"]:
        raw = by_qid.get(m["qid"])
        if raw:
            subjects.append(dict(id="member:" + m["id"], kind="member",
                                 name=m["name"], group=m["group"],
                                 qid=m["qid"]))
    print(f"{len(subjects)} subjects "
          f"({sum(1 for s in subjects if s['kind']=='group')} groups)")

    print("resolving Commons categories (P373)...")
    cats = commons_cats(subjects)
    print(f"  {len(cats)}/{len(subjects)} have one")

    print("deepcat search...")
    files = {}
    for i, s in enumerate(subjects):
        cat = cats.get(s["id"])
        if not cat:
            continue
        files[s["id"]] = deep_files(cat)
        if i % 20 == 0:
            print(f"  {i}/{len(subjects)}  {s['name']}: {len(files[s['id']])}")
            save_cache()
    save_cache()
    allfiles = sorted({f for v in files.values() for f in v})
    print(f"  {len(allfiles)} distinct files")

    print("fetching file metadata...")
    meta = file_meta(allfiles)
    save_cache()
    print(f"  {len(meta)} rows")

    # Names that mark a photo as one member's, so a group card does not end up
    # showing a solo shot — deepcat descends into member categories too.
    # Checking categories alone is not enough: "20240501 ITZY Amsterdam concert
    # 03 Yeji.jpg" and "170418 열린음악회 승희 (10).jpg" both sat in the group
    # category and named a member only in the filename. Korean labels come from
    # Wikidata so Hangul filenames are covered too.
    import wdapi
    member_qids = [s["qid"] for s in subjects if s["kind"] == "member"]
    ko_ents = wdapi.get_entities(member_qids, props="labels")
    wdapi.save()
    solo_tokens = set()
    for s in subjects:
        if s["kind"] != "member":
            continue
        solo_tokens.add(s["name"])
        ko = (ko_ents.get(s["qid"], {}).get("labels", {})
              .get("ko", {}) or {}).get("value")
        if ko and len(ko) >= 2:
            solo_tokens.add(ko)
            # Korean labels are usually surname + given name (현승희), while a
            # filename credits the given name alone (승희). Add the tail.
            if len(ko) >= 3:
                solo_tokens.add(ko[-2:])
    solo_tokens = {t for t in solo_tokens if len(t) >= 2}
    solo_re = re.compile("|".join(re.escape(flat(t))
                                  for t in sorted(solo_tokens)), re.I)

    out, stats = {}, {"group": 0, "member": 0}
    for s in subjects:
        cand = [f for f in files.get(s["id"], []) if is_stage(f, meta.get(f, {}))]
        if s["kind"] == "member":
            cand = [f for f in cand
                    if PORTRAIT_MIN <= ((meta[f]["h"] or 1) / (meta[f]["w"] or 1))
                    <= PORTRAIT_MAX and (meta[f]["h"] or 0) >= 700]
        else:
            def solo(f):
                blob = flat(f + " " + " ".join(meta[f].get("cats") or []))
                return bool(solo_re.search(blob))
            cand = [f for f in cand
                    if (meta[f]["w"] or 0) >= GROUP_MIN_W and not solo(f)]
        cand.sort(key=lambda f: rank_key(f, meta))
        if cand:
            out[s["id"]] = cand[:MAX_PER_SUBJECT]
            stats[s["kind"]] += 1

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    ng = sum(1 for s in subjects if s["kind"] == "group")
    nm = len(subjects) - ng
    print(f"\n===== wrote {OUT}")
    print(f"groups  with a stage photo: {stats['group']}/{ng}")
    print(f"members with a stage photo: {stats['member']}/{nm}")
    print(f"total photos: {sum(len(v) for v in out.values())}")

    missing = [s["name"] + " (" + s.get("group", "") + ")"
               for s in subjects if s["kind"] == "member" and s["id"] not in out]
    if missing:
        print(f"\nno stage photo for {len(missing)} members — these keep their "
              f"P18 portrait:")
        print("   " + ", ".join(missing[:60]))


if __name__ == "__main__":
    main()
