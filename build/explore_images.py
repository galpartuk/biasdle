"""Probe: can Wikimedia Commons give us STAGE photos, and several per member?

Read-only research script. Writes nothing into the repo except its own cache
under data/ is deliberately avoided -- everything lands in CACHE_DIR (scratch).

What it does
  1. Reads data/game_data.json (31 groups, 217 members) and members_raw.json.
  2. Asks Wikidata for each subject's Commons category (P373) / commonswiki
     sitelink.
  3. Crawls that category on Commons (list=categormembers, recursive, depth 2)
     for files.
  4. Scores every filename: stage keywords vs. non-stage keywords.
  5. Pulls imageinfo (size, mime, licence) for the survivors.
  6. Reports coverage + a distribution of "how many stage photos per subject".

Usage:
    python build/explore_images.py cats      # resolve commons categories
    python build/explore_images.py crawl     # crawl categories -> files
    python build/explore_images.py score     # classify + coverage report
    python build/explore_images.py info      # imageinfo/licence on a sample
    python build/explore_images.py sample    # print URLs to eyeball
    python build/explore_images.py search    # CirrusSearch fallback probe
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
DATA = os.path.join(HERE, "..", "data")
CACHE_DIR = os.environ.get(
    "KPOPDLE_SCRATCH",
    os.path.join(os.environ.get("TEMP", "/tmp"), "kpopdle_img_probe"))
os.makedirs(CACHE_DIR, exist_ok=True)

UA = ("kpopdle-image-probe/0.1 (https://github.com/galpartuk/kpopdle; "
      "hobby daily guessing game) python-urllib")
COMMONS = "https://commons.wikimedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/w/api.php"

MIN_INTERVAL = 0.35
_last = [0.0]
_caches = {}


def cache(name):
    if name not in _caches:
        p = os.path.join(CACHE_DIR, name + ".json")
        _caches[name] = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    return _caches[name]


def save(name):
    p = os.path.join(CACHE_DIR, name + ".json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(_caches[name], f, ensure_ascii=False)


def api(endpoint, params, cname="api", retries=5):
    c = cache(cname)
    params = dict(params, format="json", formatversion="2")
    key = endpoint[8:20] + "|" + urllib.parse.urlencode(sorted(params.items()))
    if key in c:
        return c[key]
    delay = 2.0
    for attempt in range(retries):
        wait = MIN_INTERVAL - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(
            endpoint + "?" + urllib.parse.urlencode(params),
            headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                d = json.loads(r.read().decode("utf-8"))
            _last[0] = time.time()
            c[key] = d
            if len(c) % 40 == 0:
                save(cname)
            return d
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            _last[0] = time.time()
            if attempt == retries - 1:
                raise
            print(f"    [net] {e} -> retry in {delay:.0f}s")
            time.sleep(delay)
            delay = min(delay * 2, 30)
    raise RuntimeError("unreachable")


def load_game():
    g = json.load(open(os.path.join(DATA, "game_data.json"), encoding="utf-8"))
    raw = json.load(open(os.path.join(DATA, "members_raw.json"), encoding="utf-8"))
    by_qid = {m["qid"]: m for m in raw}
    return g, by_qid


# --------------------------------------------------------------- 1. categories

def cmd_cats():
    game, raw = load_game()
    subs = []
    for gr in game["groups"]:
        # group qid lives in groups_resolved.json
        subs.append(("group", gr["id"], gr["name"], None))
    res = json.load(open(os.path.join(DATA, "groups_resolved.json"), encoding="utf-8"))
    qid_of_group = {g["name"]: g["wd"] for g in res}
    subjects = []
    for gr in game["groups"]:
        subjects.append({"kind": "group", "id": gr["id"], "name": gr["name"],
                         "qid": qid_of_group.get(gr["name"])})
    for m in game["members"]:
        subjects.append({"kind": "member", "id": m["id"], "name": m["name"],
                         "group": m["group"], "qid": m["qid"],
                         "enwiki": m.get("enwiki")})

    qids = [s["qid"] for s in subjects if s["qid"]]
    ents = {}
    for i in range(0, len(qids), 45):
        d = api(WIKIDATA, {"action": "wbgetentities",
                           "ids": "|".join(qids[i:i + 45]),
                           "props": "claims|sitelinks|labels",
                           "languages": "en",
                           "sitefilter": "commonswiki|enwiki"}, "wd")
        ents.update(d.get("entities", {}))
    save("wd")

    for s in subjects:
        e = ents.get(s["qid"] or "", {})
        cat = None
        for c in e.get("claims", {}).get("P373", []):
            dv = c.get("mainsnak", {}).get("datavalue")
            if dv:
                cat = dv["value"]
                break
        sl = e.get("sitelinks", {}).get("commonswiki", {}).get("title")
        if not cat and sl and sl.startswith("Category:"):
            cat = sl[9:]
        # topic's main category P910
        if not cat:
            for c in e.get("claims", {}).get("P910", []):
                dv = c.get("mainsnak", {}).get("datavalue")
                if dv:
                    s["p910"] = dv["value"]["id"]
        s["cat"] = cat
        s["commonswiki"] = sl

    # resolve P910 targets -> their commons category
    p910 = [s["p910"] for s in subjects if s.get("p910")]
    if p910:
        ents2 = {}
        for i in range(0, len(p910), 45):
            d = api(WIKIDATA, {"action": "wbgetentities",
                               "ids": "|".join(p910[i:i + 45]),
                               "props": "claims|sitelinks|labels",
                               "languages": "en",
                               "sitefilter": "commonswiki"}, "wd")
            ents2.update(d.get("entities", {}))
        save("wd")
        for s in subjects:
            if s.get("cat") or not s.get("p910"):
                continue
            e = ents2.get(s["p910"], {})
            sl = e.get("sitelinks", {}).get("commonswiki", {}).get("title")
            if sl and sl.startswith("Category:"):
                s["cat"] = sl[9:]

    out = os.path.join(CACHE_DIR, "subjects.json")
    json.dump(subjects, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ng = sum(1 for s in subjects if s["kind"] == "group" and s.get("cat"))
    nm = sum(1 for s in subjects if s["kind"] == "member" and s.get("cat"))
    print(f"groups with a Commons category : {ng}/31")
    print(f"members with a Commons category: {nm}/217")
    for s in subjects:
        if not s.get("cat"):
            print("  MISS", s["kind"], s["name"], s.get("group", ""))


# ------------------------------------------------------------------- 2. crawl

def cat_files(cat, depth=2, seen=None, budget=None):
    """Files in a category tree, breadth-first, capped."""
    seen = seen if seen is not None else set()
    files, subcats = [], []
    cont = {}
    for _ in range(8):  # up to 4000 members
        p = {"action": "query", "list": "categorymembers",
             "cmtitle": "Category:" + cat, "cmlimit": "500",
             "cmtype": "file|subcat"}
        p.update(cont)
        d = api(COMMONS, p, "cm")
        for m in d.get("query", {}).get("categorymembers", []):
            t = m["title"]
            if t.startswith("File:"):
                files.append(t[5:])
            elif t.startswith("Category:"):
                subcats.append(t[9:])
        cont = d.get("continue", {})
        if not cont:
            break
    if depth > 0:
        for sc in subcats:
            if sc in seen:
                continue
            seen.add(sc)
            if budget is not None and len(seen) > budget:
                break
            files.extend(cat_files(sc, depth - 1, seen, budget))
    return files


def cmd_crawl():
    subjects = json.load(open(os.path.join(CACHE_DIR, "subjects.json"), encoding="utf-8"))
    out_path = os.path.join(CACHE_DIR, "files.json")
    out = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
    todo = [s for s in subjects if s.get("cat") and s["id"] not in out]
    print(f"{len(todo)} subjects to crawl")
    for i, s in enumerate(todo):
        try:
            fs = cat_files(s["cat"], depth=2, seen=set(), budget=60)
        except Exception as e:
            print("  ERR", s["name"], e)
            continue
        out[s["id"]] = sorted(set(fs))
        print(f"[{i+1}/{len(todo)}] {s['kind']:6} {s['name'][:28]:28} "
              f"{s['cat'][:40]:40} {len(out[s['id']])} files")
        if i % 10 == 0:
            json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
            save("cm")
    json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
    save("cm")


# ------------------------------------------------------------------- 3. score

STAGE = [
    r"music bank", r"m ?countdown", r"엠카운트다운", r"뮤직뱅크", r"inkigayo", r"인기가요",
    r"show ?champion", r"쇼챔피언", r"music core", r"쇼!? ?음악중심", r"음악중심",
    r"the show", r"더쇼", r"simply k-?pop",
    r"concert", r"콘서트", r"tour", r"투어", r"stage", r"무대",
    r"showcase", r"쇼케이스", r"performance", r"performing", r"perform",
    r"festival", r"페스티벌", r"축제", r"live", r"라이브", r"gig",
    r"kcon", r"dream concert", r"드림콘서트", r"gayo daejun", r"가요대전",
    r"gayo daejeon", r"song festival", r"encore", r"앵콜", r"rehearsal",
    r"soundcheck", r"summer sonic", r"lollapalooza", r"coachella",
    r"waterbomb", r"워터밤", r"guerrilla", r"게릴라", r"busking", r"버스킹",
    r"fan ?meeting", r"팬미팅", r"world tour", r"comeback show",
]
NOT_STAGE = [
    r"airport", r"공항", r"red ?carpet", r"레드카펫", r"press", r"기자",
    r"photo ?call", r"포토콜", r"interview", r"인터뷰", r"fan ?sign", r"팬사인",
    r"signing", r"사인회", r"poster", r"포스터", r"logo", r"banner", r"billboard",
    r"advertis", r"광고", r"cf\b", r"wax", r"figure", r"statue", r"album cover",
    r"cd\b", r"lightstick", r"응원봉", r"cafe", r"카페", r"birthday", r"생일",
    r"subway", r"지하철", r"bus ?stop", r"screenshot", r"logo", r"wordmark",
    r"map\b", r"chart", r"graph", r"timeline", r"discography", r"signature",
    r"autograph", r"awards? red", r"arrival", r"departure", r"entering",
    r"leaving", r"going to", r"heading", r"on the way", r"출국", r"입국",
    r"conference", r"showroom", r"store", r"pop-?up", r"팝업", r"venue",
    r"crowd", r"관객", r"audience", r"empty", r"stadium exterior", r"stage set",
    r"placard", r"slogan", r"merch",
]
BAD_EXT = (".svg", ".ogg", ".ogv", ".webm", ".pdf", ".mid", ".wav", ".mp3",
           ".oga", ".flac", ".tif", ".tiff", ".gif", ".xcf", ".djvu")

STAGE_RE = re.compile("|".join(STAGE), re.I)
NOT_RE = re.compile("|".join(NOT_STAGE), re.I)


def classify(fn):
    low = fn.lower()
    if low.endswith(BAD_EXT):
        return "nonphoto"
    if NOT_RE.search(low):
        return "no"
    if STAGE_RE.search(low):
        return "stage"
    return "unknown"


def cmd_score():
    subjects = json.load(open(os.path.join(CACHE_DIR, "subjects.json"), encoding="utf-8"))
    files = json.load(open(os.path.join(CACHE_DIR, "files.json"), encoding="utf-8"))
    game, _ = load_game()
    rows = []
    for s in subjects:
        fs = files.get(s["id"], [])
        st = [f for f in fs if classify(f) == "stage"]
        rows.append(dict(s, n_all=len(fs), n_stage=len(st), stage=st))
    json.dump(rows, open(os.path.join(CACHE_DIR, "scored.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=1)

    for kind, total in (("group", 31), ("member", 217)):
        sub = [r for r in rows if r["kind"] == kind]
        for thr in (1, 2, 3, 5, 10):
            n = sum(1 for r in sub if r["n_stage"] >= thr)
            print(f"{kind:6} with >= {thr:2} stage photos: {n:3}/{total} "
                  f"({100*n/total:.0f}%)")
        print(f"{kind:6} with 0: "
              f"{[r['name'] for r in sub if r['n_stage'] == 0][:40]}")
        print()


def cmd_sample():
    rows = json.load(open(os.path.join(CACHE_DIR, "scored.json"), encoding="utf-8"))
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    import random
    random.seed(7)
    pool = [r for r in rows if r["n_stage"]]
    for r in random.sample(pool, min(n, len(pool))):
        f = random.choice(r["stage"])
        print(f"{r['kind']:6} {r['name'][:24]:24} {f}")
        print("        https://commons.wikimedia.org/wiki/Special:FilePath/"
              + urllib.parse.quote(f.replace(" ", "_")) + "?width=600")


# -------------------------------------------------------------- 4. imageinfo

def cmd_info():
    """imageinfo (size/mime/licence) for every stage candidate."""
    rows = json.load(open(os.path.join(CACHE_DIR, "scored.json"), encoding="utf-8"))
    want = sorted({f for r in rows for f in r["stage"]})
    print(len(want), "distinct candidate files")
    out_path = os.path.join(CACHE_DIR, "imageinfo.json")
    out = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
    todo = [f for f in want if f not in out]
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        d = api(COMMONS, {"action": "query",
                          "titles": "|".join("File:" + c for c in chunk),
                          "prop": "imageinfo",
                          "iiprop": "url|size|mime|extmetadata",
                          "iiextmetadatafilter":
                              "LicenseShortName|License|Artist|UsageTerms|"
                              "Restrictions|ImageDescription|DateTimeOriginal"},
                 "ii")
        for p in d.get("query", {}).get("pages", []):
            ii = (p.get("imageinfo") or [{}])[0]
            em = ii.get("extmetadata", {})
            out[p["title"][5:]] = {
                "w": ii.get("width"), "h": ii.get("height"),
                "mime": ii.get("mime"),
                "lic": (em.get("LicenseShortName") or {}).get("value"),
                "terms": (em.get("UsageTerms") or {}).get("value"),
                "restrict": (em.get("Restrictions") or {}).get("value"),
                "desc": (em.get("ImageDescription") or {}).get("value", "")[:200],
                "date": (em.get("DateTimeOriginal") or {}).get("value", "")[:40],
            }
        print(f"  {min(i+50, len(todo))}/{len(todo)}")
        json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
        save("ii")
    from collections import Counter
    print(Counter(v["lic"] for v in out.values()).most_common(20))
    print("with restrictions:",
          Counter(v["restrict"] for v in out.values() if v["restrict"]).most_common())


# ------------------------------------------------- 4b. metadata for ALL files
# Most Korean-uploaded Commons photos are named "190518 마마무 (1).jpg" -- the
# filename carries no keyword at all. The event lives in the file's CATEGORIES
# and description instead, so classification has to read those.

def cmd_meta():
    files = json.load(open(os.path.join(CACHE_DIR, "files.json"), encoding="utf-8"))
    want = sorted({f for v in files.values() for f in v
                   if not f.lower().endswith(BAD_EXT)})
    print(len(want), "distinct files")
    out_path = os.path.join(CACHE_DIR, "meta.json")
    out = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
    todo = [f for f in want if f not in out]
    print(len(todo), "to fetch")
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        d = api(COMMONS, {"action": "query",
                          "titles": "|".join("File:" + c for c in chunk),
                          "prop": "imageinfo|categories",
                          "cllimit": "max", "clshow": "!hidden",
                          "iiprop": "size|mime|extmetadata",
                          "iiextmetadatafilter":
                              "LicenseShortName|UsageTerms|Restrictions|"
                              "ImageDescription|DateTimeOriginal|Categories"},
                 "meta")
        for p in d.get("query", {}).get("pages", []):
            ii = (p.get("imageinfo") or [{}])[0]
            em = ii.get("extmetadata", {})
            out[p["title"][5:]] = {
                "w": ii.get("width"), "h": ii.get("height"),
                "mime": ii.get("mime"),
                "lic": (em.get("LicenseShortName") or {}).get("value"),
                "restrict": (em.get("Restrictions") or {}).get("value"),
                "desc": re.sub(r"<[^>]+>", " ",
                               (em.get("ImageDescription") or {}).get("value", ""))[:400],
                "cats": [c["title"][9:] for c in p.get("categories", [])],
            }
        if (i // 50) % 10 == 0:
            print(f"  {min(i+50, len(todo))}/{len(todo)}")
            json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
            save("meta")
    json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
    save("meta")
    print("meta rows:", len(out))


def classify2(fn, meta):
    """Classify using filename + categories + description."""
    if fn.lower().endswith(BAD_EXT):
        return "nonphoto"
    m = meta.get(fn) or {}
    if m.get("mime") and not m["mime"].startswith("image/"):
        return "nonphoto"
    if m.get("mime") in ("image/svg+xml",):
        return "nonphoto"
    w, h = m.get("w") or 0, m.get("h") or 0
    if w and h and (w < 500 or h < 500):
        return "small"
    blob = " ".join([fn] + m.get("cats", []) + [m.get("desc", "")])
    if STAGE_RE.search(blob):
        if NOT_RE.search(fn.lower()):
            return "no"
        return "stage"
    if NOT_RE.search(blob):
        return "no"
    return "unknown"


def cmd_score2():
    subjects = json.load(open(os.path.join(CACHE_DIR, "subjects.json"), encoding="utf-8"))
    files = json.load(open(os.path.join(CACHE_DIR, "files.json"), encoding="utf-8"))
    meta = json.load(open(os.path.join(CACHE_DIR, "meta.json"), encoding="utf-8"))
    from collections import Counter
    tally = Counter()
    rows = []
    for s in subjects:
        fs = files.get(s["id"], [])
        buckets = {}
        for f in fs:
            c = classify2(f, meta)
            tally[c] += 1
            buckets.setdefault(c, []).append(f)
        rows.append(dict(s, n_all=len(fs), n_stage=len(buckets.get("stage", [])),
                         stage=buckets.get("stage", []),
                         unknown=buckets.get("unknown", [])))
    json.dump(rows, open(os.path.join(CACHE_DIR, "scored.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=1)
    print("file classes:", tally.most_common())
    for kind, total in (("group", 31), ("member", 217)):
        sub = [r for r in rows if r["kind"] == kind]
        for thr in (1, 2, 3, 5, 10):
            n = sum(1 for r in sub if r["n_stage"] >= thr)
            print(f"{kind:6} >= {thr:2} stage: {n:3}/{total} ({100*n/total:3.0f}%)")
        zero = [r["name"] + "/" + r.get("group", "") for r in sub if r["n_stage"] == 0]
        print(f"{kind:6} zero ({len(zero)}): {zero[:60]}")
        print()


# ----------------------------------------------------------- 5. search probe

def cmd_search():
    """CirrusSearch fallback: file-namespace search per subject."""
    subjects = json.load(open(os.path.join(CACHE_DIR, "subjects.json"), encoding="utf-8"))
    only = [s for s in subjects if s["kind"] == (sys.argv[2] if len(sys.argv) > 2 else "member")]
    out_path = os.path.join(CACHE_DIR, "search.json")
    out = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
    q_tail = ('("Music Bank" OR "Inkigayo" OR "M Countdown" OR "Show Champion" '
              'OR concert OR stage OR showcase OR performing OR "Music Core" '
              'OR festival OR "fan meeting" OR "The Show")')
    todo = [s for s in only if s["id"] not in out]
    for i, s in enumerate(todo):
        name = s["name"]
        term = f'"{name}" {q_tail}'
        if s["kind"] == "member":
            term = f'"{name}" "{s.get("group","")}" {q_tail}'
        d = api(COMMONS, {"action": "query", "list": "search",
                          "srsearch": term, "srnamespace": "6",
                          "srlimit": "50"}, "srch")
        hits = [h["title"][5:] for h in d.get("query", {}).get("search", [])]
        out[s["id"]] = hits
        print(f"[{i+1}/{len(todo)}] {name[:26]:26} {len(hits)}")
        if i % 10 == 0:
            json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
            save("srch")
    json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
    save("srch")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "cats"
    globals()["cmd_" + cmd]()
