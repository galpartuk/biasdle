"""Pull whole discographies from Deezer instead of hand-typing title tracks.

songs.py caps the game at however many titles a human felt like typing, which
is why Song mode ran thin. This walks each artist's actual catalogue —
artist -> albums -> tracks — so B-sides, album cuts and Japanese releases all
come in without anyone naming them, and without any chance of inventing one.

    /search/artist  ->  /artist/{id}/albums  ->  /album/{id}/tracks

What gets thrown away, and why:

  * **Not the main artist.** Deezer lists a track under everyone on it, so a
    feature would file a Bruno Mars song under the group.
  * **Intros, outros, interludes, skits.** Real tracks, unguessable ones.
  * **Live, instrumental, remix, karaoke, sped-up, a cappella.**
  * **Same song twice.** Deduped on the normalised title, keeping the earliest
    release. This is what removes "TT (Japanese ver.)" while *keeping* Japanese
    originals such as "One More Time" — a different song has a different title.
  * **No preview.** Unplayable is unusable.

Kept tracks are ranked by Deezer's popularity and capped per artist, so the
pool leans listenable rather than being 40% interludes.

Writes data/catalogue.json. songs.py stays as the curated title-track list and
is merged in by build.py, which marks those as singles so Daily can prefer them
while Endless plays everything.

Run: PYTHONIOENCODING=utf-8 python build/fetch_catalogue.py
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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DATA = os.path.join(HERE, "..", "data")
CACHE = os.path.join(DATA, "catalogue_cache.json")
OUT = os.path.join(DATA, "catalogue.json")

from songs import ITUNES_ARTIST, SOLO_ARTIST  # noqa: E402

UA = {"User-Agent": "biasdle/0.1 (https://github.com/galpartuk/biasdle)"}
MIN_INTERVAL = 0.3
_last = [0.0]
_cache = None

# No cap. An earlier version kept the top 70 by popularity per artist, which
# quietly threw away exactly the B-sides this exists to find.
MAX_PER_ARTIST = None

# Real tracks, but not guessable ones.
JUNK = re.compile(
    r"^\s*(intro|outro|interlude|prologue|epilogue|skit|inst\.?|"
    r"instrumental|opening|ending|voice ?memo|narration)\b|"
    r"\b(intro|outro|interlude|skit|instrumental|inst\.)\s*[:\-]?\s*$", re.I)

BAD_VERSION = re.compile(
    r"\b(?:live|instrumental|inst\.|remix|karaoke|acoustic|sped\s?up|slowed|"
    r"a\s?cappella|acappella|rearranged|orchestra|cover|tribute|reprise|"
    r"remaster(?:ed)?|re-?record(?:ing|ed)?|mr|edit|mix)\b"
    r"|\bver(?:s|sion)?\b", re.I)


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


def api(path):
    c = cache()
    if path in c:
        return c[path]
    delay = 4.0
    for _ in range(4):
        gap = MIN_INTERVAL - (time.time() - _last[0])
        if gap > 0:
            time.sleep(gap)
        try:
            req = urllib.request.Request("https://api.deezer.com" + path,
                                         headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.loads(r.read().decode("utf-8"))
            _last[0] = time.time()
            c[path] = d
            if len(c) % 50 == 0:
                save_cache()
            return d
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                json.JSONDecodeError) as e:
            _last[0] = time.time()
            print(f"    retry ({e}) in {delay:.0f}s")
            time.sleep(delay)
            delay *= 2
    # Not cached: an empty answer means the API would not talk to us.
    print(f"    GAVE UP on {path}")
    return {}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9가-힣]", "", s.lower())


# A trailing tag can be parenthesised OR dash-delimited. Deezer writes both:
# "TT (Japanese ver.)" and "Decalcomanie -Japanese ver.-". Only checking the
# parenthesised form let every dash-tagged Japanese re-record into the game.
TAG = re.compile(r"\s*[\(\[].*$|\s+-\s*[^-]*-\s*$|\s+-\s+.*$")


def split_title(t):
    """(base, trailing tag). The tag is what version filters should read."""
    t = t or ""
    m = TAG.search(t)
    return (t[:m.start()], t[m.start():]) if m else (t, "")


def base_title(t):
    """Title with any trailing tag dropped, for dedupe.

    "TT (Japanese ver.)" and "TT" are one song; "One More Time" is not "TT".
    """
    return norm(split_title(t)[0])


def find_artist(names, known_titles=()):
    """Deezer artist id — the right one, not merely a name that matches.

    A name match alone is worthless. Deezer has a Romanian singer called Bibi,
    a Lithuanian act called Ive and someone called Itzy with five singles, and
    each beat the K-pop act to first place in search.

    So candidates are ordered by following, then **verified by catalogue**: at
    least one song we already know this artist released has to appear among
    their top tracks. That works where a fan-count floor does not — Wonder
    Girls' Yubin has under three thousand followers and is still the right
    Yubin.
    """
    want = {norm(n) for n in names}
    cands = []
    for n in names:
        d = api("/search/artist?q=" + urllib.parse.quote(n) + "&limit=25")
        for a in d.get("data", []):
            if norm(a.get("name")) in want:
                cands.append((-(a.get("nb_fan") or 0), a["id"], a.get("name")))
    if not cands:
        return None, None, "not found"
    cands.sort()
    wanted = {base_title(t) for t in known_titles}
    seen, ordered = set(), []
    for c in cands:
        if c[1] not in seen:
            seen.add(c[1])
            ordered.append(c)

    # A known song CONFIRMS a candidate; it does not gate them. Requiring one
    # was a worse bug than the one it fixed: /artist/top only returns the most
    # played tracks, so sixteen artists whose curated titles are not in their
    # top fifty came back empty. Following order already separates the K-pop
    # act from its namesakes; the song check just breaks ties above it.
    for fans, aid, aname in ordered[:4]:
        if not wanted:
            break
        top = api(f"/artist/{aid}/top?limit=50").get("data", [])
        titles = {base_title(t.get("title_short") or t.get("title"))
                  for t in top}
        hit = wanted & titles
        if hit:
            return aid, aname, f"{-fans} fans, confirmed by {sorted(hit)[0]!r}"

    fans, aid, aname = ordered[0]
    return aid, aname, f"{-fans} fans, unconfirmed — most followed match"


def find_member_artist(member, group, group_names):
    """A group member's own Deezer artist page, or None.

    Stage names collide constantly — there are dozens of artists called Yuna,
    Mina or Jihyo — so neither the name nor the follower count settles it. What
    does: Deezer's related-artists list. The real Yuna's page is related to
    ITZY; the other four are not.
    """
    want = {norm(group)} | {norm(n) for n in group_names}
    best = None
    for q in (member, f"{member} {group}"):
        d = api("/search/artist?q=" + urllib.parse.quote(q) + "&limit=15")
        for a in d.get("data", []):
            if norm(a.get("name")) != norm(member):
                continue
            rel = api(f"/artist/{a['id']}/related?limit=25").get("data", [])
            if not any(norm(r.get("name")) in want for r in rel):
                continue
            fans = a.get("nb_fan") or 0
            if best is None or fans > best[2]:
                best = (a["id"], a.get("name"), fans)
    return best


def albums(artist_id):
    out, url = [], f"/artist/{artist_id}/albums?limit=100"
    for _ in range(12):                    # plenty; TWICE has ~90 releases
        d = api(url)
        out += d.get("data", [])
        nxt = d.get("next")
        if not nxt:
            break
        url = nxt.replace("https://api.deezer.com", "")
    return out


def main():
    import roster
    artists = []
    for g in roster.GROUPS:
        artists.append((g["name"], ITUNES_ARTIST.get(g["name"], [g["name"]])))
    for s in roster.SOLOISTS:
        artists.append((s["name"], SOLO_ARTIST.get(s["name"], [s["name"]])))

    # Titles we already resolved for this artist, used to prove the Deezer
    # artist page is really theirs.
    import songs as songs_mod
    known = dict(songs_mod.SONGS)
    known.update(songs_mod.SOLO_SONGS)

    out, report = {}, []
    for i, (display, names) in enumerate(artists):
        aid, aname, why = find_artist(names, known.get(display, ()))
        if not aid:
            report.append((display, 0, why))
            print(f"[{i+1}/{len(artists)}] {display}: NO ARTIST — {why}")
            continue
        want_a = {norm(n) for n in names} | {norm(aname)}

        seen, keep = {}, []
        albs = albums(aid)
        for alb in albs:
            if alb.get("record_type") not in ("album", "ep", "single", None):
                continue
            tracks = api(f"/album/{alb['id']}/tracks?limit=100").get("data", [])
            for t in tracks:
                title = t.get("title_short") or t.get("title") or ""
                full = t.get("title") or title
                if not t.get("preview"):
                    continue
                # Deezer files a track under every artist on it; only the
                # credited main artist counts, or features pollute the pool.
                if norm((t.get("artist") or {}).get("name")) not in want_a:
                    continue
                if JUNK.search(title) or JUNK.search(full):
                    continue
                base, tag = split_title(title)
                _fb, ftag = split_title(full)
                if BAD_VERSION.search(tag) or BAD_VERSION.search(ftag):
                    continue
                key = norm(base)
                if not key or len(key) < 2:
                    continue
                rel = alb.get("release_date") or "9999"
                prev = seen.get(key)
                # Same song twice: keep the earliest release, which is the
                # original rather than a compilation or a re-recording.
                if prev and prev["released"] <= rel:
                    continue
                seen[key] = dict(
                    title=title, released=rel, track_id=t.get("id"),
                    rank=t.get("rank") or 0,
                    album=alb.get("title"),
                    art_md5=(alb.get("md5_image") or ""),
                    duration=t.get("duration") or 0)
        keep = sorted(seen.values(), key=lambda x: -x["rank"])
        if MAX_PER_ARTIST:
            keep = keep[:MAX_PER_ARTIST]
        keep.sort(key=lambda x: x["released"])
        out[display] = keep
        report.append((display, len(keep), f"{len(albs)} releases"))
        print(f"[{i+1}/{len(artists)}] {display}: {len(keep)} tracks "
              f"from {len(albs)} releases  [{why}]")
        save_cache()

    # ---- solo releases by members of groups ----------------------------
    # Yuna's ICE CREAM and Jihyo's ATM are real songs a K-pop player expects to
    # be asked about, and neither is in a group's discography. They are filed
    # under the group, tagged with whose solo it is.
    game_path = os.path.join(DATA, "game_data.json")
    if os.path.exists(game_path):
        with open(game_path, encoding="utf-8") as f:
            game = json.load(f)
        members = [m for m in game["members"] if m["group"] != "Soloist"]
        print(f"\nlooking for solo releases by {len(members)} group members")
        found = 0
        for j, m in enumerate(members):
            names = ITUNES_ARTIST.get(m["group"], [m["group"]])
            hit = find_member_artist(m["name"], m["group"], names)
            if not hit:
                continue
            aid, aname, fans = hit
            tracks = []
            for alb in albums(aid):
                if alb.get("record_type") not in ("album", "ep", "single", None):
                    continue
                for t in api(f"/album/{alb['id']}/tracks?limit=100").get("data", []):
                    title = t.get("title_short") or t.get("title") or ""
                    full = t.get("title") or title
                    if not t.get("preview"):
                        continue
                    if norm((t.get("artist") or {}).get("name")) != norm(aname):
                        continue
                    if JUNK.search(title) or JUNK.search(full):
                        continue
                    _b, tag = split_title(title)
                    _fb, ftag = split_title(full)
                    if BAD_VERSION.search(tag) or BAD_VERSION.search(ftag):
                        continue
                    tracks.append(dict(
                        title=title, released=alb.get("release_date") or "9999",
                        track_id=t.get("id"), rank=t.get("rank") or 0,
                        album=alb.get("title"), by=m["name"],
                        art_md5=alb.get("md5_image") or "",
                        duration=t.get("duration") or 0))
            if not tracks:
                continue
            uniq = {}
            for t in sorted(tracks, key=lambda x: -x["rank"]):
                uniq.setdefault(base_title(t["title"]), t)
            picked = list(uniq.values())
            out.setdefault(m["group"], []).extend(picked)
            found += 1
            print(f"   {m['name']} ({m['group']}): {len(picked)} solo tracks "
                  f"[{fans} fans]")
            if j % 25 == 0:
                save_cache()
        print(f"solo releases found for {found} members")

    save_cache()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    total = sum(len(v) for v in out.values())
    print(f"\n===== {total} tracks across {len(out)} artists -> {OUT}")
    thin = [f"{n} ({c})" for n, c, _ in report if c < 8]
    if thin:
        print(f"\nthin catalogues ({len(thin)}): {', '.join(thin)}")


if __name__ == "__main__":
    main()
