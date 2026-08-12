"""Hand-authored group-level data for kpopdle.

DELIBERATE SCOPE: this file holds only facts about *groups* — label, debut date,
generation, status. It does NOT list members. Member lists are pulled from
Wikidata (P527 "has part") by build/fetch_wikidata.py, because hand-typing ~200
member names from memory is how you end up inventing people who were never in
the group. Anything a human must assert about a *member* (stage name spelling,
position) lives in overrides.py, and only after the fetch has shown us who the
API thinks the members actually are.

Fields:
  name      display name used in-game
  company   label/agency at debut (current label noted only if it changed hands)
  debut     first official single/EP release date (YYYY-MM-DD)
  gen       K-pop "generation" — see GEN_BOUNDS below, derived-but-pinned
  status    "active" | "disbanded" | "inactive"  (inactive = no activity, no
            official disbandment announcement)
  tier      how often this group should come up as a daily answer:
            1 = a casual listener names them unprompted, 2 = known to anyone
            who follows K-pop, 3 = deep cut. Purely an editorial weight on the
            schedule — it never affects grading. Without it the daily answer is
            drawn uniformly per *member*, which hands tripleS (24 members) five
            times the airtime of LE SSERAFIM (5) and makes the game feel like
            it is about groups nobody asked for.
  wd        Wikidata QID, pinned by hand so a name search can't drift onto the
            wrong entity (there are several groups called "Alice", "Nature", ...)
  aka       extra strings the search box should accept

Generation boundaries used here (debut date):
  gen 3: 2014-01-01 .. 2018-12-31
  gen 4: 2019-01-01 .. 2022-12-31
  gen 5: 2023-01-01 ..
These are fandom convention, not science; they are pinned per-group so a group
that everyone calls 4th-gen despite a 2018 debut stays 4th-gen.
"""

GROUPS = [
    # ---------------- 3rd generation ----------------
    dict(name="MAMAMOO", company="RBW", debut="2014-06-18", gen=3,
         tier=2, status="active", wd=None, aka=["마마무"]),
    dict(name="Red Velvet", company="SM Entertainment", debut="2014-08-01",
         gen=3, tier=2, status="active", wd=None, aka=["레드벨벳", "RV"]),
    dict(name="GFRIEND", company="Source Music", debut="2015-01-15", gen=3,
         tier=2, status="disbanded", wd=None, aka=["여자친구", "GFriend", "Gfriend"]),
    dict(name="OH MY GIRL", company="WM Entertainment", debut="2015-04-21",
         gen=3, tier=2, status="active", wd=None, aka=["오마이걸", "OMG"]),
    dict(name="TWICE", company="JYP Entertainment", debut="2015-10-20", gen=3,
         tier=1, status="active", wd=None, aka=["트와이스"]),
    dict(name="WJSN", company="Starship Entertainment", debut="2016-02-25",
         gen=3, tier=3, status="inactive", wd=None,
         aka=["Cosmic Girls", "우주소녀", "Cosmic Girl"]),
    dict(name="BLACKPINK", company="YG Entertainment", debut="2016-08-08",
         gen=3, tier=1, status="active", wd=None, aka=["블랙핑크", "BP"]),
    dict(name="Dreamcatcher", company="Dreamcatcher Company",
         debut="2017-01-13", gen=3, tier=2, status="active", wd=None,
         aka=["드림캐쳐", "DC"]),
    dict(name="fromis_9", company="Pledis Entertainment", debut="2018-01-24",
         gen=3, tier=2, status="active", wd=None,
         aka=["프로미스나인", "fromis9", "fromis"]),
    dict(name="(G)I-DLE", company="Cube Entertainment", debut="2018-05-02",
         gen=3, tier=1, status="active", wd=None,
         aka=["여자아이들", "GIDLE", "G-IDLE", "i-dle", "idle"]),
    dict(name="LOONA", company="Blockberry Creative", debut="2018-08-20",
         gen=3, tier=2, status="inactive", wd=None,
         aka=["이달의 소녀", "Loona", "LOOΠΔ"]),

    # ---------------- 4th generation ----------------
    dict(name="ITZY", company="JYP Entertainment", debut="2019-02-12", gen=4,
         tier=1, status="active", wd=None, aka=["있지"]),
    dict(name="EVERGLOW", company="Yuehua Entertainment", debut="2019-03-18",
         gen=4, tier=3, status="active", wd=None, aka=["에버글로우"]),
    dict(name="Rocket Punch", company="Woollim Entertainment",
         debut="2019-08-07", gen=4, tier=3, status="inactive", wd=None,
         aka=["로켓펀치"]),
    dict(name="STAYC", company="High Up Entertainment", debut="2020-11-12",
         gen=4, tier=2, status="active", wd=None, aka=["스테이씨", "Stayc"]),
    dict(name="aespa", company="SM Entertainment", debut="2020-11-17", gen=4,
         tier=1, status="active", wd=None, aka=["에스파", "Aespa", "AESPA"]),
    dict(name="Weeekly", company="IST Entertainment", debut="2020-06-30",
         gen=4, tier=3, status="disbanded", wd=None, aka=["위클리"]),
    dict(name="PURPLE KISS", company="RBW", debut="2021-03-15", gen=4,
         tier=3, status="active", wd=None, aka=["퍼플키스", "Purple Kiss"]),
    dict(name="Billlie", company="Mystic Story", debut="2021-11-10", gen=4,
         tier=3, status="active", wd=None, aka=["빌리", "Billie"]),
    dict(name="IVE", company="Starship Entertainment", debut="2021-12-01",
         gen=4, tier=1, status="active", wd=None, aka=["아이브"]),
    dict(name="Kep1er", company="WAKEONE", debut="2022-01-03", gen=4,
         tier=2, status="disbanded", wd=None, aka=["케플러", "Kepler", "Kep1er"]),
    dict(name="NMIXX", company="JYP Entertainment", debut="2022-02-22", gen=4,
         tier=2, status="active", wd=None, aka=["엔믹스", "Nmixx"]),
    dict(name="LE SSERAFIM", company="Source Music", debut="2022-05-02",
         gen=4, tier=1, status="active", wd=None,
         aka=["르세라핌", "LESSERAFIM", "Le Sserafim"]),
    dict(name="NewJeans", company="ADOR", debut="2022-07-22", gen=4,
         tier=1, status="active", wd=None,
         aka=["뉴진스", "New Jeans", "NJZ"]),

    # ---------------- 5th generation ----------------
    dict(name="tripleS", company="MODHAUS", debut="2023-02-13", gen=5,
         tier=2, status="active", wd=None, aka=["트리플에스", "triple S", "SSS"]),
    dict(name="KISS OF LIFE", company="S2 Entertainment", debut="2023-07-05",
         gen=5, tier=2, status="active", wd=None, aka=["키스오브라이프", "KIOF"]),
    dict(name="BABYMONSTER", company="YG Entertainment", debut="2024-04-01",
         gen=5, tier=2, status="active", wd=None,
         aka=["베이비몬스터", "Baby Monster", "BAMO"]),
    dict(name="ILLIT", company="BELIFT LAB", debut="2024-03-25", gen=5,
         tier=2, status="active", wd=None, aka=["아일릿", "Illit"]),
    dict(name="MEOVV", company="THEBLACKLABEL", debut="2024-09-06", gen=5,
         tier=2, status="active", wd=None, aka=["미야오", "Meow"]),
    dict(name="izna", company="WAKEONE", debut="2024-11-25", gen=5,
         tier=2, status="active", wd=None, aka=["이즈나", "IZNA"]),
    dict(name="Hearts2Hearts", company="SM Entertainment", debut="2025-02-24",
         gen=5, tier=2, status="active", wd=None,
         aka=["하츠투하츠", "Hearts 2 Hearts", "H2H"]),
]

# Companies get normalised for the grid column so "Source Music" vs
# "Source Music (HYBE)" can't read as two different answers. The value here is
# what the player sees; the parent conglomerate is a separate, coarser column.
PARENT = {
    "Source Music": "HYBE",
    "ADOR": "HYBE",
    "BELIFT LAB": "HYBE",
    "Pledis Entertainment": "HYBE",
    "THEBLACKLABEL": "Independent",
    "WAKEONE": "CJ ENM",
    "IST Entertainment": "Kakao",
    "Starship Entertainment": "Kakao",
    "MODHAUS": "Independent",
}
