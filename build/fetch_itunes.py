"""Resolve every hand-authored song to an iTunes track with a playable preview.

Why iTunes: Apple serves a 30-second preview clip for essentially every song in
the catalogue, over CORS, with no API key and no ads. The game never hosts or
proxies audio — it stores a trackId and asks Apple for the preview at play time.
That keeps the repo small and keeps us out of the business of redistributing
other people's recordings, which is what got the original Heardle shut down.

A match has to survive:
  * artist match against the group's known iTunes spellings
  * title match after normalisation
  * rejection of live / instrumental / remix / karaoke / sped-up versions
  * preference for the earliest release (the Korean original, not the later
    Japanese re-record or the anniversary reissue)

Anything that fails is dropped and printed. A hand-authored song that doesn't
exist cannot survive this, which is the point.

Writes data/songs_resolved.json.
Run: PYTHONIOENCODING=utf-8 python build/fetch_itunes.py
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
CACHE = os.path.join(DATA, "itunes_cache.json")
OUT = os.path.join(DATA, "songs_resolved.json")

UA = {"User-Agent": "kpopdle/0.1 (hobby daily guessing game)"}

# The iTunes Search API throttles at roughly 20 calls/minute and answers with a
# 403 once you cross it. Racing it and retrying is slower than simply staying
# under the limit, so requests are paced instead.
MIN_INTERVAL = 3.4
_last = [0.0]

BAD_VERSION = re.compile(
    r"\b(live|inst\.?|instrumental|remix|karaoke|acoustic|sped up|slowed|"
    r"a cappella|acappella|rearranged|orchestra|cover|tribute|mr\b|"
    r"japanese ver|jp ver|english ver|chinese ver)\b", re.I)

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


def search(term, limit=25):
    c = cache()
    if term in c:
        return c[term]
    url = ("https://itunes.apple.com/search?term=" + urllib.parse.quote(term)
           + f"&media=music&entity=song&limit={limit}&country=US")
    delay = 20.0
    for attempt in range(6):
        gap = MIN_INTERVAL - (time.time() - _last[0])
        if gap > 0:
            time.sleep(gap)
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            _last[0] = time.time()
            c[term] = data.get("results", [])
            if len(c) % 10 == 0:
                save_cache()
            return c[term]
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                json.JSONDecodeError) as e:
            _last[0] = time.time()
            print(f"    throttled ({e}) — waiting {delay:.0f}s")
            time.sleep(delay)
            delay = min(delay * 1.6, 120)
    # Deliberately NOT cached: an empty list here means "the API would not talk
    # to us", not "no such song". Caching it would permanently drop a real track
    # and the build report would call it a bad title.
    print(f"    GAVE UP on {term!r} — rerun to retry")
    return []


def pick(group, title):
    artists = ITUNES_ARTIST.get(group, [group])
    want_t = norm(title)
    want_a = {norm(a) for a in artists}

    results = []
    for a in artists[:2]:
        results += search(f"{a} {title}")
    # Deduplicate by trackId, keep first sighting.
    seen, cands = set(), []
    for r in results:
        tid = r.get("trackId")
        if tid and tid not in seen:
            seen.add(tid)
            cands.append(r)

    scored = []
    for r in cands:
        if not r.get("previewUrl"):
            continue
        rname, aname = r.get("trackName", ""), r.get("artistName", "")
        # Artist must match one of the known spellings, or contain it as a
        # standalone token (handles "TWICE" inside "TWICE & Friends").
        na = norm(aname)
        if not any(na == w or w in na for w in want_a):
            continue
        nt = norm(rname)
        if nt == want_t:
            score = 0
        elif nt.startswith(want_t) or want_t in nt:
            score = 1
        else:
            continue
        # A bad-version tag in the *extra* part of the title disqualifies it.
        extra = rname[len(title):] if len(rname) > len(title) else ""
        if BAD_VERSION.search(extra) or BAD_VERSION.search(
                r.get("collectionName", "")):
            continue
        rel = r.get("releaseDate") or "9999"
        scored.append((score, rel, r))

    if not scored:
        return None, "no match"
    scored.sort(key=lambda x: (x[0], x[1]))  # exact title first, then earliest
    return scored[0][2], "ok"


def main():
    out, failed, inexact = [], [], []
    total = sum(len(v) for v in SONGS.values())
    i = 0
    for group, titles in SONGS.items():
        for title in titles:
            i += 1
            r, why = pick(group, title)
            if not r:
                failed.append((group, title, why))
                print(f"[{i}/{total}] MISS  {group} — {title}")
                continue
            art = (r.get("artworkUrl100") or "").replace("100x100", "300x300")
            rec = dict(group=group, title=title,
                       itunes_title=r.get("trackName"),
                       artist=r.get("artistName"),
                       track_id=r.get("trackId"),
                       preview=r.get("previewUrl"),
                       artwork=art,
                       album=r.get("collectionName"),
                       released=(r.get("releaseDate") or "")[:10],
                       duration_ms=r.get("trackTimeMillis"))
            out.append(rec)
            if norm(r.get("trackName", "")) != norm(title):
                inexact.append(
                    f"{group}: asked {title!r} -> got {r.get('trackName')!r}")
            print(f"[{i}/{total}] ok    {group} — {r.get('trackName')} "
                  f"({rec['released'][:4]})")
    save_cache()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print(f"\n===== resolved {len(out)}/{total} songs -> {OUT}")
    if inexact:
        print(f"\n## title differs from what we asked for ({len(inexact)}) "
              f"— check these are the right recording")
        for x in inexact:
            print("   ", x)
    if failed:
        print(f"\n## NOT FOUND ({len(failed)}) — wrong title, or the song does "
              f"not exist")
        for g, t, w in failed:
            print(f"    {g} — {t}  ({w})")


if __name__ == "__main__":
    main()
