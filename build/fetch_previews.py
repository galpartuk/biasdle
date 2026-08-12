"""Resolve every hand-authored song to a playable 30-second preview.

Primary source is **Deezer's public API**: no key, CORS-enabled, and — unlike
the iTunes Search API — it does not throttle a few hundred requests into
oblivion. The iTunes run for this same song list got to 76/274 in fifty minutes
and the 403 backoff was still growing, so iTunes is demoted to a cache-only
fallback for anything Deezer cannot find.

Either way the game only ever stores a preview URL and points an <audio> element
at it. We never host, mirror or proxy a recording.

A candidate has to survive the same checks regardless of source:
  * artist matches one of the group's known spellings
  * title matches after normalisation
  * live / instrumental / remix / karaoke / language-rerecord versions rejected
  * ties broken by popularity, which reliably surfaces the canonical original
    over a compilation re-release

Anything that fails is dropped and printed, so a song title I invented cannot
quietly reach the game.

Writes data/songs_resolved.json.
Run: PYTHONIOENCODING=utf-8 python build/fetch_previews.py
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from songs import ITUNES_ARTIST, SONGS  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
CACHE = os.path.join(DATA, "deezer_cache.json")
ITUNES_CACHE = os.path.join(DATA, "itunes_cache.json")
OUT = os.path.join(DATA, "songs_resolved.json")

UA = {"User-Agent": "kpopdle/0.1 (hobby daily guessing game)"}
MIN_INTERVAL = 0.35
_last = [0.0]

# "ver" has to tolerate ver / ver. / vers / version. An earlier pattern here
# used \bjapanese ver\b, which does NOT match "Japanese Version" — the word
# boundary fails mid-word — and that one slip let the Japanese re-recordings of
# Power Up, MORE & MORE, Cupid, Senorita and Uh-Oh into the game.
BAD_VERSION = re.compile(
    r"\b(?:live|instrumental|inst\.|remix|karaoke|acoustic|sped\s?up|slowed|"
    r"a\s?cappella|acappella|rearranged|orchestra|cover|tribute|reprise|"
    r"edit|remaster(?:ed)?|re-?record(?:ing|ed)?|mr)\b"
    # Any "ver" / "ver." / "version" tag, whoever it names. Kept deliberately
    # blunt: it has to catch "(Japanese Version)", "-JP Version",
    # "(i-dle ver.)" and "(HUH YUNJIN ver.)" alike. Note there is no trailing
    # \b — an earlier attempt put one after the escaped dot, where it can never
    # match, and "(HUH YUNJIN ver.)" sailed straight through.
    r"|\bver(?:s|sion)?\b", re.I)

# A found title may legitimately carry a parenthetical the asked-for title
# omits — "HANN (Alone)", "BUNGEE (Fall in Love)", "PITAPAT (DKDK)". What it may
# NOT do is merely *contain* the asked title, which is how LE SSERAFIM's "HOT"
# matched "1-800-hot-n-fun" and Dreamcatcher's "What" matched "What Does It
# Mean?". Anything trailing the title must open like a suffix.
SUFFIX_OK = re.compile(r"^\s*$|^\s*[(\[\-–—:~/&]")

_cache = None


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


def norm(s):
    """Fold case, accents and punctuation so 'Décalcomanie' == 'decalcomanie'."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9가-힣]", "", s.lower())


def deezer(query):
    c = cache()
    if query in c:
        return c[query]
    url = ("https://api.deezer.com/search?q=" + urllib.parse.quote(query)
           + "&limit=20")
    delay = 4.0
    for attempt in range(4):
        gap = MIN_INTERVAL - (time.time() - _last[0])
        if gap > 0:
            time.sleep(gap)
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                data = json.loads(r.read().decode("utf-8"))
            _last[0] = time.time()
            hits = data.get("data", [])
            c[query] = hits
            if len(c) % 20 == 0:
                save_cache()
            return hits
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                json.JSONDecodeError) as e:
            _last[0] = time.time()
            print(f"    retry ({e}) in {delay:.0f}s")
            time.sleep(delay)
            delay *= 2
    # Never cached — an empty list here means the API would not answer, not
    # that the song is missing. Caching it would drop a real track for good.
    print(f"    GAVE UP on {query!r} — rerun to retry")
    return []


def acceptable(rname, aname, want_t, want_a, raw_title):
    """Shared validation for a candidate from any source."""
    na = norm(aname)
    if not any(na == w or w in na for w in want_a):
        return None
    nt = norm(rname)
    if nt == want_t:
        return 0
    if not nt.startswith(want_t):
        return None
    # Locate where the asked-for title ends in the *original* string so the
    # suffix test reads real punctuation, not the normalised form.
    idx = len(raw_title)
    if not rname.lower().startswith(raw_title.lower()):
        idx = max(0, len(rname) - (len(nt) - len(want_t)))
    extra = rname[idx:]
    if not SUFFIX_OK.match(extra) or BAD_VERSION.search(extra):
        return None
    return 1


def from_deezer(group, title):
    artists = ITUNES_ARTIST.get(group, [group])
    want_t, want_a = norm(title), {norm(a) for a in artists}

    # Try queries in widening order and keep going until one yields a candidate
    # that actually passes validation. Stopping at the first query that merely
    # returns *rows* was dropping real songs: the strict query for
    # "How You Like That" returns only the Japanese re-record, which we reject,
    # and the Korean original never got looked for.
    queries = [f'artist:"{a}" track:"{title}"' for a in artists[:3]]
    queries += [f"{a} {title}" for a in artists[:2]]
    queries.append(title)

    scored = []
    hits = []
    for q in queries:
        hits = deezer(q)
        scored = score_hits(hits, want_t, want_a, title)
        if scored:
            break
    if not scored:
        return None
    # An exact-title hit beats a suffixed one outright, so a re-recording or a
    # (Japanese Version) can never win on popularity alone.
    if any(x[0] == 0 for x in scored):
        scored = [x for x in scored if x[0] == 0]
    scored.sort(key=lambda x: (x[0], x[1]))
    h = scored[0][2]
    alb = h.get("album") or {}
    return dict(
        source="deezer", title=title, group=group,
        found_title=h.get("title"), artist=(h.get("artist") or {}).get("name"),
        track_id=h.get("id"), preview=h.get("preview"),
        artwork=alb.get("cover_big") or alb.get("cover_medium"),
        album=alb.get("title"), released="",
        duration_ms=(h.get("duration") or 0) * 1000)


def score_hits(hits, want_t, want_a, title):
    scored = []
    for h in hits:
        if not h.get("preview"):
            continue
        rname = h.get("title_short") or h.get("title") or ""
        full = h.get("title") or rname
        aname = (h.get("artist") or {}).get("name", "")
        score = acceptable(rname, aname, want_t, want_a, title)
        if score is None or BAD_VERSION.search(full):
            continue
        # rank is Deezer's popularity number; the canonical release outranks
        # compilation and re-release copies of the same recording.
        scored.append((score, -(h.get("rank") or 0), h))
    return scored


def from_itunes_cache(group, title):
    """Cache-only fallback. Deliberately never hits the network — the iTunes
    endpoint is what we moved away from."""
    if not os.path.exists(ITUNES_CACHE):
        return None
    global _it
    try:
        _it
    except NameError:
        _it = json.load(open(ITUNES_CACHE, encoding="utf-8"))
    artists = ITUNES_ARTIST.get(group, [group])
    want_t, want_a = norm(title), {norm(a) for a in artists}
    results = []
    for a in artists[:2]:
        results += _it.get(f"{a} {title}", [])
    scored = []
    for r in results:
        if not r.get("previewUrl"):
            continue
        rname = r.get("trackName", "")
        score = acceptable(rname, r.get("artistName", ""), want_t, want_a, title)
        if score is None or BAD_VERSION.search(r.get("collectionName", "")):
            continue
        scored.append((score, r.get("releaseDate") or "9999", r))
    if not scored:
        return None
    scored.sort(key=lambda x: (x[0], x[1]))
    r = scored[0][2]
    return dict(
        source="itunes", title=title, group=group,
        found_title=r.get("trackName"), artist=r.get("artistName"),
        track_id=r.get("trackId"), preview=r.get("previewUrl"),
        artwork=(r.get("artworkUrl100") or "").replace("100x100", "500x500"),
        album=r.get("collectionName"), released=(r.get("releaseDate") or "")[:10],
        duration_ms=r.get("trackTimeMillis"))


def main():
    out, failed, inexact = [], [], []
    total = sum(len(v) for v in SONGS.values())
    i = 0
    for group, titles in SONGS.items():
        for title in titles:
            i += 1
            rec = from_deezer(group, title) or from_itunes_cache(group, title)
            if not rec:
                failed.append((group, title))
                print(f"[{i}/{total}] MISS  {group} — {title}")
                continue
            out.append(rec)
            if norm(rec["found_title"]) != norm(title):
                inexact.append(f"{group}: asked {title!r} -> got "
                               f"{rec['found_title']!r} ({rec['source']})")
            print(f"[{i}/{total}] ok    {group} — {rec['found_title']} "
                  f"[{rec['source']}]")
    save_cache()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    src = {}
    for r in out:
        src[r["source"]] = src.get(r["source"], 0) + 1
    print(f"\n===== resolved {len(out)}/{total} songs -> {OUT}")
    print(f"      by source: {src}")
    if inexact:
        print(f"\n## title differs from the request ({len(inexact)}) — check "
              f"these are the right recording")
        for x in inexact:
            print("   ", x)
    if failed:
        print(f"\n## NOT FOUND ({len(failed)}) — wrong title, or no such song")
        for g, t in failed:
            print(f"    {g} — {t}")


if __name__ == "__main__":
    main()
