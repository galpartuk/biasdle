"""Hand corrections applied on top of the Wikidata fetch.

Everything here exists because a human read data/members_raw.json line by line
and found the API wrong. Keep the reason next to the fix — an override with no
reason is indistinguishable from a typo six months from now.

Re-run `python build/fetch_members.py` after Wikidata changes and re-read the
report; entries that stop being necessary should be deleted, not left to rot.
"""

# ---------------------------------------------------------------------------
# STAGE NAMES
# Wikidata's label is whatever an editor felt like: sometimes the stage name
# ("Solar"), sometimes the legal name ("Kang Seul-gi"), sometimes Hangul. The
# stage name is what a player types, so where the automatic derivation gets it
# wrong we pin it here as (group, wikidata label, correct stage name, why) and
# resolve to QIDs at build time — build_stage_map() shouts if a row stops
# matching exactly one person, which is the signal that upstream data moved.
_FIXES = [
    ("MAMAMOO",      "Wheein",            "Wheein",      "spacing: 'Whee In' -> one word"),
    ("OH MY GIRL",   "Yubin",             "Binnie",      "legal name Bae Yubin; stage name is Binnie"),
    ("OH MY GIRL",   "Hyun Seung-hee",    "Seunghee",    "legal name used as label"),
    ("TWICE",        "Minatozaki Sana",   "Sana",        "full Japanese name used as label"),
    ("TWICE",        "Mina Myoi",         "Mina",        "full Japanese name used as label"),
    ("TWICE",        "Chou Tzuyu",        "Tzuyu",       "full Taiwanese name used as label"),
    ("WJSN",         "Meng Mei Qi",       "Meiqi",       "full Chinese name used as label"),
    ("WJSN",         "Wu Xuan Yi",        "Xuanyi",      "full Chinese name used as label"),
    ("WJSN",         "Cheng Xiao",        "Cheng Xiao",  "stage name really is both syllables"),
    ("Dreamcatcher", "Gahyun",            "Gahyeon",     "official romanisation is Gahyeon"),
    ("LOONA",        "Kim Lip",           "Kim Lip",     "surname-strip wrongly cut this to 'Lip'"),
    ("LOONA",        "Go Won",            "Go Won",      "surname-strip wrongly cut this to 'Won'"),
    ("LOONA",        "Hyeju",             "Olivia Hye",  "legal name Son Hyeju; stage name is Olivia Hye"),
    ("EVERGLOW",     "Jo Se-rim",         "Onda",        "legal name used as label"),
    ("EVERGLOW",     "Heo Yoo-rim",       "Aisha",       "legal name used as label"),
    ("EVERGLOW",     "Han Eun-ji (Mia)",  "Mia",         "label carried both names"),
    ("EVERGLOW",     "Wang Yiren",        "Yiren",       "full Chinese name used as label"),
    ("PURPLE KISS",  "Na Go-eun",         "Goeun",       "legal name used as label"),
    ("Billlie",      "Moon Sua",          "Moon Sua",    "surname-strip wrongly cut this to 'Sua'"),
    ("LE SSERAFIM",  "Huh Yun-jin",       "Yunjin",      "legal name used as label"),
    ("LE SSERAFIM",  "Kazuha Nakamura",   "Kazuha",      "full Japanese name used as label"),
    ("LE SSERAFIM",  "Sakura Miyawaki",   "Sakura",      "full Japanese name used as label"),
    ("NewJeans",     None,                "Danielle",    "VANDALISED LABEL upstream: 'Danielle Marsh la mas diva de todo new jeans perras'"),
    ("NewJeans",     "Hanni Pham",        "Hanni",       "full name used as label"),
    ("Kep1er",       "Shen Xiaoting",     "Xiaoting",    "full Chinese name used as label"),
    ("Kep1er",       "Hikaru Ezaki",      "Hikaru",      "full Japanese name used as label"),
    ("Kep1er",       "Huening Bahiyyih",  "Bahiyyih",    "goes by Bahiyyih"),
    ("tripleS",      "Hsu Nien Tzu",      "Nien",        "full Taiwanese name used as label"),
    ("MEOVV",        "Anna Tanaka",       "Anna",        "full name used as label"),
    ("MEOVV",        "Ella Gross",        "Ella",        "full name used as label"),
]

# ---------------------------------------------------------------------------
# MEMBERSHIP STATUS
# Wikidata's P582 (end time) qualifier on the group's P527 claim is how we tell
# former members apart. It is not always right.
NOT_FORMER = {
    # The NewJeans/ADOR dispute got edited into Wikidata as departures. The
    # members never stopped being NewJeans members in any official sense.
    ("NewJeans", "Danielle"): "ADOR contract dispute, not a departure",
}

FORCE_FORMER = {
    # (group, stage): reason — for departures Wikidata hasn't recorded yet.
}

# ---------------------------------------------------------------------------
# NATIONALITY
# P27 is citizenship, which is not always the answer a player expects. Where the
# two differ the game shows every citizenship on record and marks a guess amber
# when the sets overlap without matching — see compare.py. Only outright gaps
# are patched here.
NATIONALITY = {
    ("Red Velvet", "Wendy"): ["South Korean", "Canadian"],  # P27 empty upstream
}

# ---------------------------------------------------------------------------
# ORIGINAL LINE-UP SIZE
# The Members column counts everyone we ship for a group, current and former,
# which for K-pop is the debut line-up: members leave, they are almost never
# added. Three groups break that, so the true number is pinned here — a player
# who knows Kep1er had nine should not be told seven.
ORIGINAL_SIZE = {
    "Kep1er": 9,      # Wikidata's P527 list is missing Mashiro and Yeseo
    "WJSN": 12,       # Yeonjung joined in 2016, after the 12-member debut
    "tripleS": 24,    # five members dropped here for having no birth date
    "IZ*ONE": 12,     # Sakura, Chaewon, Wonyoung and Yujin count under the
                      # groups they are in now, so we ship fewer than twelve
}

# ---------------------------------------------------------------------------
# EXCLUSIONS
# Members we cannot field a fair grid row for. Excluded from the answer pool AND
# from the guess list, so the game never shows a row with a blank column.
EXCLUDE_REASON = "no birth date on Wikidata; birth year is a scored column"


def build_stage_map(members):
    """Resolve the readable _FIXES table to {qid: stage_name}, loudly."""
    out, unmatched = {}, []
    for group, label, stage, _why in _FIXES:
        hits = [m for m in members
                if any(g["group"] == group for g in m["groups"])
                and (label is None or m["label"] == label)]
        if label is None:
            # Vandalised-label case: match on the corrected stage name being a
            # prefix of the junk label instead.
            hits = [m for m in members
                    if any(g["group"] == group for g in m["groups"])
                    and (m["label"] or "").startswith(stage)]
        if len(hits) == 1:
            out[hits[0]["qid"]] = stage
        else:
            unmatched.append((group, label, stage, len(hits)))
    return out, unmatched
