"""Thin, polite client for the Wikidata Action API.

Why not WDQS/SPARQL: the query service is frequently degraded and drops to
"1 request per minute" under load, which makes a 30-group fetch take half an
hour and fail halfway. The Action API is a separate service and is fine with a
steady ~1 req/sec as long as you send a real User-Agent.

Every response is cached to data/wd_cache.json keyed by the request params, so
re-running a build costs zero network. Delete that file to force a refresh.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://www.wikidata.org/w/api.php"
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(HERE, "..", "data", "wd_cache.json")

# Wikidata's rate limiter is much friendlier when it can identify the client.
UA = ("kpopdle/0.1 (https://github.com/galpartuk/kpopdle; hobby daily guessing "
      "game) python-urllib")

_cache = None
_last_call = [0.0]
MIN_INTERVAL = 1.1  # seconds between live requests


def _load():
    global _cache
    if _cache is None:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, encoding="utf-8") as f:
                _cache = json.load(f)
        else:
            _cache = {}
    return _cache


def save():
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(_load(), f, ensure_ascii=False)


def call(params, _retries=6):
    """GET the Action API with caching, pacing and 429 backoff."""
    cache = _load()
    params = dict(params, format="json")
    key = urllib.parse.urlencode(sorted(params.items()))
    if key in cache:
        return cache[key]

    delay = 2.0
    for attempt in range(_retries):
        wait = MIN_INTERVAL - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params),
                                     headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                data = json.loads(r.read().decode("utf-8"))
            _last_call[0] = time.time()
            cache[key] = data
            if len(cache) % 20 == 0:
                save()
            return data
        except urllib.error.HTTPError as e:
            _last_call[0] = time.time()
            if e.code in (429, 503) and attempt < _retries - 1:
                print(f"    [{e.code}] backing off {delay:.0f}s "
                      f"(attempt {attempt + 1}/{_retries})")
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            _last_call[0] = time.time()
            if attempt < _retries - 1:
                print(f"    [net] {e} — retry in {delay:.0f}s")
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise
    raise RuntimeError("unreachable")


def search(term, limit=10):
    d = call({"action": "wbsearchentities", "search": term, "language": "en",
              "uselang": "en", "type": "item", "limit": limit})
    return d.get("search", [])


def get_entities(qids, props="claims|labels|aliases|sitelinks"):
    """Batch wbgetentities. Wikidata caps ids at 50 per call."""
    out = {}
    qids = list(dict.fromkeys(qids))
    for i in range(0, len(qids), 45):
        chunk = qids[i:i + 45]
        d = call({"action": "wbgetentities", "ids": "|".join(chunk),
                  "props": props, "languages": "en|ko|ja",
                  "sitefilter": "enwiki"})
        out.update(d.get("entities", {}))
    return out


# ---- claim helpers -------------------------------------------------------

def claims(ent, prop):
    return ent.get("claims", {}).get(prop, [])


def values(ent, prop):
    """Datavalues of a property, preferred ranks first, deprecated dropped."""
    out = []
    for c in claims(ent, prop):
        if c.get("rank") == "deprecated":
            continue
        dv = c.get("mainsnak", {}).get("datavalue")
        if dv:
            out.append(dv.get("value"))
    return out


def first(ent, prop, default=None):
    v = values(ent, prop)
    return v[0] if v else default


def label(ent, lang="en"):
    return ent.get("labels", {}).get(lang, {}).get("value")


def qualifier(claim, prop):
    for q in claim.get("qualifiers", {}).get(prop, []):
        dv = q.get("datavalue")
        if dv:
            return dv.get("value")
    return None


def wtime(v):
    """Wikidata time value -> 'YYYY-MM-DD' (may carry 00 for unknown parts)."""
    if not v:
        return None
    t = v.get("time") if isinstance(v, dict) else None
    return t[1:11] if t else None
