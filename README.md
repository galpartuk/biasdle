# BIASDLE

**Play: https://galpartuk.github.io/biasdle/**

A daily guessing game about K-pop girl groups, in the shape of
[dragonballdle](https://github.com/galpartuk/dragonballdle) and
[digimondle](https://github.com/galpartuk/digimondle). Named for the fandom
word: your *bias* is your favourite member.

Four puzzles, each with a Daily and an Endless mode:

| Mode | You guess | Feedback | Guesses |
|---|---|---|---|
| **Idol** 아이돌 | a specific member (`Wonyoung`, `Sana`) | 8-column grid | 8 |
| **Group** 그룹 | a girl group (`ITZY`) | 6-column grid | 8 |
| **Face** 얼굴 | who the photocard shows | the card slides out of its sleeve | 6 |
| **Song** 노래 | the title track playing | 1s → 2 → 4 → 7 → 11 → 16 | 6 |

Everything ships in one self-contained `index.html` (~361 KB). Portraits and
audio are the only things fetched at runtime.

**Content:** 217 members across 31 groups, 269 title tracks, 3rd–5th generation.

Three colour themes (Bubblegum, Soda, Arena), a volume slider on Song mode, and
filters that narrow Endless by generation, fame tier or group — with TWICE and
LE SSERAFIM pinned as quick picks. Selections are additive: press both and you
get both. Filters never touch Daily; everyone gets the same puzzle.

---

## Where the data comes from

The part worth reading before changing anything.

| Field | Source | Trust |
|---|---|---|
| group name, label, debut date, generation, status, tier | `build/roster.py`, hand-typed | **mine to get wrong** |
| which members are in a group | Wikidata `P527` | good, occasionally incomplete |
| birth date, citizenship, portrait | Wikidata `P569` / `P27` / `P18` | good |
| stage names | Wikidata `P742`, else derived, else `build/overrides.py` | needed 39 hand fixes |
| song titles | `build/songs.py`, hand-typed | self-verifying, see below |
| song → audio | Deezer public API | 273/274 resolved |

**Member lists are deliberately not hand-authored.** Typing ~220 member names
from memory is how you invent people who were never in the group. `roster.py`
holds only group-level facts — the things one person can actually verify — and
the roster comes from the API.

**Song titles are hand-authored, and that is safe** because `fetch_previews.py`
must find a real track by the right artist before a song enters the game. An
invented title cannot survive the fetch; it lands in the `NOT FOUND` section of
the build report instead.

### Wikidata is editable by anyone, and it shows

Danielle of NewJeans arrived with the label
`"Danielle Marsh la más diva de todo new jeans perras"` — live vandalism.
`overrides.py` pins her name and `web/test_logic.js` asserts no vandalised
string reaches the payload. If you re-run the fetch, **read the report**.

### Known gaps

- **Kep1er is missing 2 members** (Mashiro, Yeseo) — Wikidata's `P527` list is
  incomplete. The Members column counts the roster we ship, not the Wikipedia
  number, so the arrows stay honest, but a purist will notice.
- **5 tripleS members are dropped** for having no birth date on Wikidata. Birth
  year is a scored column and a blank cell in a Loldle grid reads as a hint.
- **Rocket Punch's "BIM BAM BUM" is missing** — not in Deezer's catalogue.
- **Height is not a column.** Wikidata has it for about 1 member in 40.
- **Position/role is not a column.** `P106` exists for 227/228 members but says
  "singer" for almost everyone and "rapper" for only 30, which would make the
  column actively misleading. Same reasoning that killed the Form column in
  digimondle — no vague partial credit.

---

## Comparison rules

Green = exact. Amber = close, in a way that is stated rather than vibes-based.

| Column | Amber means |
|---|---|
| Group | never — right or wrong |
| Company | different label, **same parent conglomerate** (Source Music and ADOR are both HYBE) |
| From | citizenships overlap without matching (dual nationals) |
| Gen | never — tolerance is 0 on purpose; adjacent generations are not "close" |
| Members | within 1 |
| Debut | within 2 years |
| Born | within 2 years |
| Status | never |

Arrows on numeric columns point from your guess toward the answer.

**Generation** boundaries are fandom convention, pinned per group in
`roster.py`: gen 3 = 2014–2018 debuts, gen 4 = 2019–2022, gen 5 = 2023+.

**Status** for a member is `Current member` / `Former member` /
`Disbanded group`, from the `P582` end-time qualifier on the group's `P527`
claim, with corrections in `overrides.py`.

---

## The daily schedule is weighted on purpose

Drawn uniformly, the daily answer is picked per *member*, which hands tripleS
(24 members) five times the airtime of LE SSERAFIM (5) and makes the game feel
like it is about groups nobody asked for.

So each group carries a `tier` in `roster.py` — 1 = a casual listener names
them unprompted, 2 = known to anyone who follows K-pop, 3 = deep cut — and the
year is apportioned by tier, normalised per group so member count doesn't
decide it. Over 365 days:

| | groups | days | per group |
|---|---|---|---|
| tier 1 | 8 | ~155 | ~19 |
| tier 2 | 17 | ~180 | ~10 |
| tier 3 | 6 | ~30 | ~5 |

**Daily is the shop window; Endless plays the whole pool.** There is no
guarantee that every member appears in a given year — reserving one slot each
would eat 217 of the 365 days and there'd be nothing left to weight with.
Repeats are always at least 14 days apart, and every group appears at some
point.

Tier is an editorial weight on scheduling only. It never affects grading.

---

## Audio: why Deezer

The original Heardle was shut down by Spotify, so the game never hosts, mirrors
or proxies a recording — it points an `<audio>` element at a public 30-second
preview URL.

iTunes was the first choice and is now a cache-only fallback. It throttles hard:
the same 274-song list got to 76 in fifty minutes with the 403 backoff still
growing. Deezer did 273 in under ten minutes, needs no key, and sends CORS.

### Preview URLs expire — resolve them at play time

This one cost a bug report. Deezer signs every preview URL with a short expiry:

    ...88f9f423.mp3?hdnea=exp=1786531003~acl=...~hmac=0b28cc61...

They die inside the hour. A URL captured at build time answers **403** by the
time anyone opens the page, and `<audio>` reports that as a generic play()
rejection — which the game used to mislabel "Tap play once to allow audio",
advice that cannot possibly help.

The **track id is stable**, so `srcFor()` fetches a live URL when the player
needs one. `api.deezer.com` sends no `Access-Control-Allow-Origin`, so `fetch()`
is not an option; it does support **JSONP** (`?output=jsonp&callback=`), which
is not subject to CORS at all. `song.preview` in the payload is now only a
last-resort fallback for when the network is down.

iTunes URLs do *not* expire — they are plain unsigned CDN paths, and one
fetched two hours earlier still answered 200. That would remove the runtime
lookup entirely, but iTunes still throttles search hard enough (three requests
then a connection reset) that resolving 274 songs through it is not viable.

Two more things worth knowing:

- **Previews usually start partway into the track**, often near the chorus,
  not at 0:00 like the original Heardle. The first second is more recognisable
  than a true intro clip would be.
- **Playback could not be verified in the automated browser.** Chrome defers
  media loading in a hidden tab, and this tab is always hidden — even a WAV
  generated in-page never leaves `readyState 0`. The preview URLs themselves
  were verified (200, `audio/mpeg`, ~480 KB, range requests answered). Test
  sound in a real browser window.

YouTube embeds were considered and rejected: there is no key-free search API,
so 274 video IDs would have to come from memory — exactly the hallucination
risk this build is designed around — and some videos block embedding anyway.

---

## Design

The visual system is built out of **photocards**: the thing girl-group fans
actually collect, trade, sleeve and carry. `web/theme.css` has the full token
set.

- The answer arrives as a photocard — ivory stock, foil-stamped name plate,
  prism holo that tracks the pointer. It is the only loud element on the page.
- **Face mode** is a card in a frosted PVC sleeve, sliding out bottom-up: you
  get the outfit and hair first and the eyes last. A uniform blur hides the same
  amount of everything; a sleeve hands over a real band of the photo per guess.
- Hangul appears as micro-type throughout — it is real content (the group's
  Korean name, from `roster.py`), not decoration.
- A **group** card is landscape (85:55). Cropping nine people into a portrait
  photocard cuts half of them out of frame; album inserts are shaped this way
  for the same reason.

### Photos

Portraits come from Wikidata `P18`, which is whatever an editor picked for an
infobox: press shots, airport departures, red carpets. `build/fetch_photos.py`
adds **stage photography** on top, from Commons.

`P373` gives each subject a Commons category and CirrusSearch's `deepcat:`
expands the whole tree server-side — a `categorymembers` crawl misses a level,
because Commons nests these as `X` / `X by year` / `X in 2019` / `X at
Coachella 2019`. Classification reads filename, the file's own categories and
its description; filenames alone say nothing when the convention is Korean and
date-prefixed (`170923 마마무 04.jpg`). Ranking is by **aspect ratio**, which is
the signal that actually matters: a stage keyword tells you the file is from a
stage *event*, orientation tells you whether the face is big enough to
recognise.

| | with stage photos |
|---|---|
| groups | 29 / 31 |
| members | 126 / 217 |

Up to 12 per subject, so a repeat shows a different shot. Daily indexes by day
so everyone sees the same photo; Endless varies.

**The gap is not random.** It falls on the rookie and HYBE rosters — tripleS,
Billlie, Weeekly, PURPLE KISS, NMIXX and Kep1er are almost entirely uncovered,
and NewJeans has one usable group photo. Commons simply has no performance
photos of them, and relaxing the filter to fill the gap just readmits fansigns
and arrivals, which is the problem being solved.

Everything falls back through `onerror`: stage photo → P18 portrait → the next
stage photo. Filename lists rot as Commons renames and deletes files; P18 is
maintained by editors.

Licences are CC BY / CC BY-SA / CC0 / PD throughout — the same obligations the
P18 images already carried.

### Themes

Three, switchable from the swatches in the header and remembered per browser.
Every value that differs between them is a CSS variable, and a test asserts each
theme defines all of them — a theme missing one silently inherits whatever the
previous theme left behind.

Light themes need more than inverted colours. Prism foil on `color-dodge` blows
a pale photocard out to flat white, so light themes blend with `overlay`; the
sleeve frost has to brighten rather than darken; and the corner radii open up,
because "cute" is carried by roundness as much as by hue.

---

## Build

```bash
python build/resolve_groups.py    # roster names -> verified Wikidata QIDs
python build/fetch_members.py     # QIDs -> members + birth/nationality/portrait
python build/fetch_previews.py    # songs.py -> Deezer track ids + preview urls
python build/fetch_photos.py      # Commons stage photos (optional, ~20 min)
python build/build.py             # merge + overrides + theme -> index.html
node   web/test_logic.js          # 252 assertions against the built file
```

Every fetch caches to `data/`, so re-running costs no network. Delete
`data/wd_cache.json` or `data/deezer_cache.json` to force a refresh.

On Windows set `PYTHONIOENCODING=utf-8` or the console dies on the first Hangul
character.

### Gotchas that cost time already

- **Wikidata's SPARQL endpoint is not usable here.** It drops to 1 request per
  minute under load. Everything uses the Action API instead.
- **Don't trust remembered QIDs.** An early `resolve_groups.py` had `Q13383457`
  as "girl group"; it is a species of ant. Every type QID in that file was
  looked up, not recalled.
- **A failed API call must never be cached as an empty result.** The first
  iTunes run cached 15 rate-limit failures as "song not found", silently
  dropping BOOMBAYAH and Feel Special.
- **`\bjapanese ver\b` does not match "Japanese Version".** The word boundary
  fails mid-word, and five Japanese re-recordings walked into the game. The
  version filter is blunt on purpose now.
- **A title match must be a prefix, not a substring.** LE SSERAFIM's "HOT"
  matched "1-800-hot-n-fun" and Dreamcatcher's "What" matched "What Does It
  Mean?".
- **`schedule()` used to hang forever on an empty pool.** Guarded now.
- **ASCII is not the same as Latin script.** Filtering names on `ord(c) < 128`
  dropped Rosé and quietly shrank BLACKPINK to 3 members, corrupting the
  Members column for the whole group.
- **Two CSS rules cannot share one pseudo-element.** `.pc::after` and
  `.holo::after` are the same box; the later rule simply replaces the earlier.
- **Don't build a CSS selector regex out of a template literal.** `` `\[data-theme="x"\]` ``
  loses its backslashes and becomes a character *class*, which matches somewhere
  else entirely. A test written that way reported all three themes as broken.
  Scan to the braces instead.
- **A group card kept showing one member.** `deepcat` descends into member
  categories, and filtering on categories alone let through
  `...concert 03 Yeji.jpg` and `...승희 (10).jpg`, which name a member only in
  the filename. Fold hyphens too, or our `Miyeon` misses `Cho Mi-yeon`.
- **Group images had to be asked for separately.** `fetch_members.py` reads P18
  for members only, so Group mode shipped with no art at all until
  `resolve_groups.py` started capturing the group's own P18.

---

## Testing

`node web/test_logic.js` extracts the real script out of the built `index.html`
and runs it against a stub DOM. It checks data integrity, that every member
grades all-green against herself, the amber rules, search behaviour (including
typing `rose` for `Rosé`), schedule coverage and weighting, and the audio
reveal ladder.

Browser automation is not a dependable check here — the tab is always hidden,
which breaks anything involving media, and synthetic clicks miss often enough
to be misleading. Use the test file.

---

A fan project. Not affiliated with any label. Portraits are Wikimedia Commons;
song previews are streamed from Deezer, not redistributed.
