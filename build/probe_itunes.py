"""Probe: can the iTunes Search API give us a stable 30s preview for K-pop title tracks?

Checks a handful of songs across generations and prints trackId / previewUrl / artwork.
Run: python build/probe_itunes.py
"""
import json
import time
import urllib.parse
import urllib.request

TESTS = [
    ("TWICE", "What is Love?"),
    ("BLACKPINK", "DDU-DU DDU-DU"),
    ("IVE", "I AM"),
    ("NewJeans", "Ditto"),
    ("aespa", "Next Level"),
    ("LE SSERAFIM", "ANTIFRAGILE"),
    ("Red Velvet", "Psycho"),
    ("ITZY", "WANNABE"),
    ("(G)I-DLE", "TOMBOY"),
    ("STAYC", "ASAP"),
    ("Kep1er", "WA DA DA"),
    ("ILLIT", "Magnetic"),
]

UA = {"User-Agent": "Mozilla/5.0 (kpopdle-probe)"}


def search(artist, track):
    term = urllib.parse.quote(f"{artist} {track}")
    url = (
        f"https://itunes.apple.com/search?term={term}"
        "&media=music&entity=song&limit=5&country=US"
    )
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


for artist, track in TESTS:
    try:
        data = search(artist, track)
        hits = data.get("results", [])
        if not hits:
            print(f"MISS   {artist} - {track}")
            continue
        h = hits[0]
        print(
            f"OK     {artist} - {track}\n"
            f"       -> trackId={h.get('trackId')} "
            f"artist={h.get('artistName')!r} name={h.get('trackName')!r}\n"
            f"       -> preview={'YES' if h.get('previewUrl') else 'NO'} "
            f"art={'YES' if h.get('artworkUrl100') else 'NO'} "
            f"len={h.get('trackTimeMillis')}"
        )
    except Exception as e:  # noqa: BLE001
        print(f"ERROR  {artist} - {track}: {e}")
    time.sleep(0.4)
