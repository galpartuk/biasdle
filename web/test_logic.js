/* Runs the real game logic out of index.html against a stub DOM.
 *
 * The Chrome extension froze repeatedly while building digimondle, so browser
 * automation is not a dependable check here either. This exercises the parts
 * that can actually be wrong — grading, search, the daily schedule, the audio
 * reveal ladder — against the shipped data, not a fixture.
 *
 * Run: node web/test_logic.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const HTML = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
// index.html is written on Windows, so the newlines are CRLF.
const script = /<script>\s*"use strict";([\s\S]*?)<\/script>/.exec(HTML);
if (!script) { console.error("could not find the game script"); process.exit(1); }

/* --- the thinnest DOM that lets the module body run --------------------- */
const noop = () => {};
const stubEl = () => new Proxy({
  style: {},
  classList: {add: noop, remove: noop, toggle: noop, contains: () => false},
  dataset: {}, hidden: false, value: "", textContent: "", innerHTML: "",
  disabled: false, placeholder: "",
  setAttribute: noop, getAttribute: () => null, removeAttribute: noop,
  addEventListener: noop, removeEventListener: noop, appendChild: noop,
  remove: noop, select: noop, focus: noop, scrollIntoView: noop,
  showModal: noop, close: noop, closest: () => null,
  querySelector: () => stubEl(), querySelectorAll: () => [],
}, {get: (t, k) => (k in t ? t[k] : undefined), set: (t, k, v) => (t[k] = v, true)});

const sandbox = {
  console, setTimeout, clearTimeout, setInterval, clearInterval,
  module: {exports: {}},
  localStorage: (() => {
    let s = {};
    return {getItem: k => (k in s ? s[k] : null),
            setItem: (k, v) => { s[k] = String(v); },
            removeItem: k => { delete s[k]; }, clear: () => { s = {}; }};
  })(),
  navigator: {},
  Audio: function () { return {play: () => Promise.resolve(), pause: noop,
                               currentTime: 0, addEventListener: noop}; },
  document: {
    querySelector: () => stubEl(), querySelectorAll: () => [],
    getElementById: () => stubEl(),
    createElement: () => stubEl(), addEventListener: noop,
    documentElement: stubEl(),
    body: {appendChild: noop},
  },
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext('"use strict";' + script[1], sandbox, {filename: "game.js"});
const G = sandbox.module.exports;
if (!G || !G.DATA) { console.error("game script did not export"); process.exit(1); }

/* --- tiny assert harness ------------------------------------------------ */
let pass = 0, fail = 0;
const failures = [];
function ok(cond, msg) {
  if (cond) { pass++; } else { fail++; failures.push(msg); }
}
function eq(a, b, msg) {
  ok(JSON.stringify(a) === JSON.stringify(b),
     `${msg}\n     expected ${JSON.stringify(b)}\n     got      ${JSON.stringify(a)}`);
}
function section(t) { console.log("\n— " + t); }

const {DATA, S, MODES, MEMBER_COLS, GROUP_COLS, grade, gNum, gSet, gCompany,
       norm, candidates, dailyAnswer, unlockedSeconds, STEPS} = G;
const member = n => DATA.members.find(m => m.name === n);
const group = n => DATA.groups.find(g => g.name === n);

/* ====================================================================== */
section("data integrity");
ok(DATA.members.length > 150, `expected 150+ members, got ${DATA.members.length}`);
ok(DATA.groups.length >= 25, `expected 25+ groups, got ${DATA.groups.length}`);

const ids = new Set();
let dupIds = 0;
DATA.members.concat(DATA.groups, DATA.songs).forEach(x => {
  if (ids.has(x.id)) dupIds++; else ids.add(x.id);
});
eq(dupIds, 0, "no duplicate ids across pools");

const REQ = ["group", "company", "parent", "nationality", "gen", "size",
             "debut", "birth", "status", "display", "search"];
const holes = DATA.members.filter(m => REQ.some(
  k => m[k] === undefined || m[k] === null || m[k] === ""));
eq(holes.map(m => m.name), [], "every member has all scored columns");

const badNat = DATA.members.filter(m => !Array.isArray(m.nationality) || !m.nationality.length);
eq(badNat.map(m => m.name), [], "nationality is always a non-empty array");

const badYear = DATA.members.filter(m => !(m.birth > 1980 && m.birth < 2015));
eq(badYear.map(m => `${m.name}:${m.birth}`), [], "birth years are plausible");

/* Soloists carry their SOLO debut, which is deliberately allowed to predate
   the gen-3 floor the group roster uses — see the soloists section. */
const badDebut = DATA.members.filter(
  m => m.group !== "Soloist" && !(m.debut >= 2014 && m.debut <= 2026));
eq(badDebut.map(m => `${m.name}:${m.debut}`), [], "group debut years inside gen 3-5");
const badSolo = DATA.members.filter(
  m => m.group === "Soloist" && !(m.debut >= 2000 && m.debut <= 2026));
eq(badSolo.map(m => `${m.name}:${m.debut}`), [], "solo debut years are plausible");

/* Size must equal the number of members actually shipped for that group,
   otherwise the Members column's arrows point the wrong way. */
const counted = {};
DATA.members.forEach(m => { counted[m.group] = (counted[m.group] || 0) + 1; });
/* "Soloist" is a label, not a group: its size is 1 per person by definition,
   not a headcount of everyone who happens to be solo. */
const pins = DATA.original_size || {};
const sizeWrong = DATA.members
  .filter(m => m.group !== "Soloist")
  .filter(m => m.size !== (pins[m.group] != null ? pins[m.group]
                                                 : counted[m.group]))
  .map(m => `${m.group}: column ${m.size}, expected ` +
            `${pins[m.group] != null ? pins[m.group] : counted[m.group]}`);
eq([...new Set(sizeWrong)], [], "member size column matches the debut line-up");

/* Members is the DEBUT line-up, which is not always the number of rows we
   ship: Wikidata's Kep1er list is short, WJSN gained a member after debut, and
   IZ*ONE's overlapping members count under the groups they are in now. Those
   are pinned in overrides.ORIGINAL_SIZE, so the column may legitimately exceed
   the pool — it must never be SMALLER, which would mean a missing pin. */
const LINEUP = DATA.original_size || {};
const gSizeWrong = DATA.groups
  .filter(g => g.size !== (LINEUP[g.name] != null ? LINEUP[g.name]
                                                  : (counted[g.name] || 0)))
  .map(g => `${g.name}: column ${g.size}, pinned ${LINEUP[g.name]}, ` +
            `pool ${counted[g.name]}`);
eq(gSizeWrong, [],
   "Members is the pinned debut line-up where pinned, else the roster count");
ok(Object.keys(LINEUP).length >= 3,
   `line-up pins are shipped (${Object.keys(LINEUP).join(", ")})`);
const memberSizeDisagrees = DATA.members
  .filter(m => m.group !== "Soloist")
  .filter(m => m.size !== (DATA.groups.find(g => g.name === m.group) || {}).size)
  .map(m => `${m.name} (${m.group})`);
eq([...new Set(memberSizeDisagrees)], [],
   "a member's Members column matches her group's");

/* ====================================================================== */
section("known facts (spot-check against the real world)");
const spot = [
  ["Nayeon", "TWICE", "JYP Entertainment", 1995, "South Korean"],
  ["Tzuyu", "TWICE", "JYP Entertainment", 1999, "Taiwanese"],
  ["Jisoo", "BLACKPINK", "YG Entertainment", 1995, "South Korean"],
  ["Lisa", "BLACKPINK", "YG Entertainment", 1997, "Thai"],
  ["Wonyoung", "IVE", "Starship Entertainment", 2004, "South Korean"],
  ["Karina", "aespa", "SM Entertainment", 2000, "South Korean"],
  ["Sakura", "LE SSERAFIM", "Source Music", 1998, "Japanese"],
  ["Hanni", "NewJeans", "ADOR", 2004, "Australian"],
];
spot.forEach(([n, g, c, y, nat]) => {
  const m = member(n);
  ok(m, `member "${n}" exists`);
  if (!m) return;
  eq([m.group, m.company, m.birth], [g, c, y], `${n}: group/label/birth year`);
  ok(m.nationality.includes(nat), `${n}: nationality includes ${nat}`);
});

/* Stage names the override table had to fix — regression guard. */
[["Sana", "TWICE"], ["Mina", "TWICE"], ["Binnie", "OH MY GIRL"],
 ["Seunghee", "OH MY GIRL"], ["Olivia Hye", "LOONA"], ["Onda", "EVERGLOW"], ["Aisha", "EVERGLOW"], ["Yunjin", "LE SSERAFIM"],
 ["Kazuha", "LE SSERAFIM"], ["Danielle", "NewJeans"], ["Wendy", "Red Velvet"],
 ["Rose", "BLACKPINK"], ["Moon Sua", "Billlie"], ["Kim Lip", "LOONA"],
].forEach(([n, g]) => {
  const m = DATA.members.find(x => norm(x.name) === norm(n) && x.group === g);
  ok(m, `override kept "${n}" (${g}) findable under that stage name`);
});

/* The vandalised Wikidata label must not have reached the payload. */
const vandal = DATA.members.filter(m => /diva|perras/i.test(m.name + m.display));
eq(vandal.map(m => m.name), [], "no vandalised label leaked into the game");

/* Hangul-only names would be untypeable in the search box. */
const unTypeable = DATA.members.filter(m => !/[a-z]/i.test(m.name));
eq(unTypeable.map(m => m.name), [], "every member name has latin letters");

/* ====================================================================== */
section("grading");
const A = member("Wonyoung");      // IVE, Starship, 2004, gen 4
ok(A, "fixture member present");

eq(grade(member("Yujin"), A, MEMBER_COLS[0]).r, "hit",
   "same group -> hit on Group");
eq(grade(member("Nayeon"), A, MEMBER_COLS[0]).r, "miss",
   "different group -> miss on Group");

/* company: same conglomerate, different label -> near */
const hybeA = member("Sakura");     // Source Music (HYBE)
const hybeB = member("Danielle");   // ADOR (HYBE)
eq(gCompany(hybeA, hybeB).r, "near", "Source Music vs ADOR -> near (both HYBE)");
eq(gCompany(hybeA, hybeA).r, "hit", "same label -> hit");
eq(gCompany(member("Nayeon"), member("Jisoo")).r, "miss", "JYP vs YG -> miss");

/* numbers: direction and tolerance */
const born = MEMBER_COLS.find(c => c.k === "birth");
eq(gNum(2000, 2004, born), {r: "miss", dir: "up"}, "older guess -> arrow up");
eq(gNum(2008, 2004, born), {r: "miss", dir: "down"}, "younger guess -> arrow down");
eq(gNum(2003, 2004, born).r, "near", "1 year off is inside the +/-2 band");
eq(gNum(2006, 2004, born).r, "near", "2 years off is still inside the band");
eq(gNum(2007, 2004, born).r, "miss", "3 years off falls outside the band");
eq(gNum(2004, 2004, born), {r: "hit"}, "exact -> hit, no arrow");

const gen = MEMBER_COLS.find(c => c.k === "gen");
eq(gen.tol, 0, "generation has no tolerance band — it is right or wrong");
eq(gNum(3, 4, gen).r, "miss", "adjacent generations are not 'near'");

/* sets */
eq(gSet(["South Korean"], ["South Korean"]).r, "hit", "identical set -> hit");
eq(gSet(["South Korean", "Canadian"], ["South Korean"]).r, "near",
   "overlapping set -> near");
eq(gSet(["Japanese"], ["South Korean"]).r, "miss", "disjoint set -> miss");

/* a member always scores a perfect row against herself */
DATA.members.slice(0, 40).forEach(m => {
  const bad = MEMBER_COLS.filter(c => grade(m, m, c).r !== "hit").map(c => c.k);
  eq(bad, [], `${m.name} grades all-green against herself`);
});
DATA.groups.forEach(g => {
  const bad = GROUP_COLS.filter(c => grade(g, g, c).r !== "hit").map(c => c.k);
  eq(bad, [], `group ${g.name} grades all-green against itself`);
});

/* ====================================================================== */
section("search");
S.mode = "member"; S.guesses = [];
const findsIt = (q, name) => {
  const c = candidates(q);
  ok(c.some(x => x.name === name),
     `"${q}" finds ${name} (top: ${c.slice(0, 3).map(x => x.name).join(", ") || "none"})`);
};
findsIt("wony", "Wonyoung");
findsIt("won young", "Wonyoung");
findsIt("twice", "Nayeon");            // group name pulls up its members
findsIt("ive won", "Wonyoung");
findsIt("karina", "Karina");
// Her name carries an accent; typing plain ASCII has to still reach her.
ok(candidates("rose").some(x => norm(x.name) === "rose"),
   'search for "rose" reaches Rose without the accent');
eq(candidates("zzzzzz").length, 0, "nonsense query returns nothing");

/* already-guessed entries drop out of the list */
S.guesses = [member("Wonyoung")];
ok(!candidates("wony").some(x => x.name === "Wonyoung"),
   "a guessed member is removed from suggestions");
S.guesses = [];

S.mode = "group";
ok(candidates("black").some(x => x.name === "BLACKPINK"), "group search works");
ok(candidates("cosmic").some(x => x.name === "WJSN"), "group aka search works");
S.mode = "member";

/* ====================================================================== */
section("daily schedule");
["member", "group", "image", "song"].forEach(mode => {
  const sched = DATA.schedules[mode] || [];
  const pool = MODES[mode].pool();
  if (!pool.length) { console.log(`   (skipped ${mode} — empty pool)`); return; }
  ok(sched.length === 365, `${mode}: 365-day schedule (got ${sched.length})`);
  const poolIds = new Set(pool.map(x => x.id));
  const stray = sched.filter(id => !poolIds.has(id));
  eq([...new Set(stray)], [], `${mode}: every scheduled id exists in the pool`);

  /* The year is apportioned by popularity, so an answer CAN come round twice —
     but never soon enough for a player to notice a rerun. */
  const seenAt = new Map();
  let minGap = Infinity;
  sched.forEach((id, i) => {
    if (seenAt.has(id)) minGap = Math.min(minGap, i - seenAt.get(id));
    seenAt.set(id, i);
  });
  ok(minGap >= 14,
     `${mode}: repeats are at least 14 days apart (closest is ${minGap})`);

  /* Every group has to show up at some point in the year — weighting the
     Daily toward the big names must not silence a group completely. */
  const groupsIn = new Set(sched.map(id => {
    const it = pool.find(x => x.id === id);
    return it ? (it.group || it.name) : null;
  }));
  eq(DATA.groups.filter(g => !groupsIn.has(g.name)).map(g => g.name), [],
     `${mode}: every group appears somewhere in the year`);

  for (const d of [0, 1, 5, 100, 364]) {
    ok(dailyAnswer(mode, d), `${mode}: day ${d} resolves to an answer`);
  }
  /* Negative day index (player's clock is behind the epoch) must not crash. */
  ok(dailyAnswer(mode, -3), `${mode}: negative day index still resolves`);
});

/* image mode must never schedule someone with no portrait */
const imgPool = new Set(MODES.image.pool().map(m => m.id));
eq((DATA.schedules.image || []).filter(id => !imgPool.has(id)), [],
   "image schedule only contains members who have a portrait");

/* The whole point of the tiers: a group everyone can name gets meaningfully
   more of the year than a deep cut. Checked as an aggregate so one group's
   rounding can't fail the suite. */
["member", "group", "image", "song"].forEach(mode => {
  const pool = MODES[mode].pool();
  const tierOf = {};
  DATA.groups.forEach(g => { tierOf[g.name] = g.tier; });
  const days = {1: 0, 2: 0, 3: 0};
  (DATA.schedules[mode] || []).forEach(id => {
    const it = pool.find(x => x.id === id);
    if (it) days[tierOf[it.group || it.name]]++;
  });
  const perGroup = t => days[t] / DATA.groups.filter(g => g.tier === t).length;
  ok(perGroup(1) > perGroup(2) && perGroup(2) > perGroup(3),
     `${mode}: tier 1 outranks tier 2 outranks tier 3 per group ` +
     `(${perGroup(1).toFixed(1)} / ${perGroup(2).toFixed(1)} / ${perGroup(3).toFixed(1)} days)`);
  /* Song mode cannot reach 2.5x. The daily song pool is the curated title
     tracks, and the 21-day no-repeat rule caps any one artist at about 17
     days a year — tier 1 is already at that ceiling, so the ratio is bounded
     by the spacing rule rather than by the weights. */
  const floor = mode === "song" ? 1.5 : 2.5;
  ok(perGroup(1) >= perGroup(3) * floor,
     `${mode}: a tier-1 group gets at least ${floor}x a tier-3 group's days ` +
     `(${(perGroup(1) / perGroup(3)).toFixed(2)}x)`);
});

/* ====================================================================== */
section("audio reveal ladder");
S.mode = "song";
S.done = false;
const ladder = [];
for (let i = 0; i < 6; i++) { S.guesses = new Array(i).fill(null); ladder.push(unlockedSeconds()); }
eq(ladder, STEPS, "each miss unlocks the next step");
eq(STEPS, [1, 2, 4, 7, 11, 16], "ladder is 1/2/4/7/11/16 seconds");
S.guesses = new Array(20).fill(null);
ok(unlockedSeconds() <= 30, "unlocked time never exceeds the 30s preview");
S.done = true;
eq(unlockedSeconds(), 30, "solving unlocks the whole preview");
S.done = false; S.guesses = [];

if (DATA.songs.length) {
  /* Catalogue tracks deliberately carry no preview URL — Deezer signs those
     with an hour-long expiry, so they are resolved at play time from the track
     id. What every track must have is that id. */
  eq(DATA.songs.filter(s => !s.track).map(s => s.title), [],
     "every song has a Deezer track id");
  const badHost = DATA.songs.filter(s => s.preview && !/^https:\/\//.test(s.preview));
  eq(badHost.map(s => s.title), [], "stored preview urls, where present, are https");
} else {
  console.log("   (no songs in payload yet — audio pool checks skipped)");
}

/* ====================================================================== */
section("themes");
const {THEMES, defaultFilters, passes, endlessPool, groupByName, PINNED,
       SLEEVE_COVER, SLEEVE_FROST, SLEEVE_SAT} = G;
eq(THEMES, ["bubblegum", "soda", "arena"], "three themes, light one first");

/* Every theme must define every variable the stylesheet reads, or a switch
   silently falls back to whatever the previous theme left behind. */
const CSS = /<style>([\s\S]*?)<\/style>/.exec(HTML)[1];
const used = [...new Set([...CSS.matchAll(/var\((--[a-z0-9-]+)/g)].map(m => m[1]))];
/* Read a rule body by scanning to its braces rather than by building a regex
   from a selector string. Escaping [ ] { } through a template literal is a
   trap: `\[data-theme="soda"\]` in a template literal loses its backslashes and
   becomes a character CLASS, which happily matches somewhere else entirely and
   reported all three themes as broken. */
function ruleBody(selectorFragment) {
  const at = CSS.indexOf(selectorFragment);
  if (at < 0) return null;
  const open = CSS.indexOf("{", at);
  const close = CSS.indexOf("}", open);
  return (open < 0 || close < 0) ? null : CSS.slice(open + 1, close);
}
// --cover, --frost, --sat, --hx, --hy are set per element from JS, not per theme
const PER_ELEMENT = new Set(["--cover", "--frost", "--sat", "--hx", "--hy"]);
THEMES.forEach(t => {
  const body = ruleBody(`[data-theme="${t}"]`);
  ok(body, `theme "${t}" has a variable block`);
  if (!body) return;
  const defined = new Set([...body.matchAll(/(--[a-z0-9-]+)\s*:/g)].map(m => m[1]));
  const missing = used.filter(v => !defined.has(v) && !PER_ELEMENT.has(v));
  eq(missing, [], `theme "${t}" defines every variable the CSS reads`);
});

/* A light theme with color-dodge foil turns the photocard into a white slab. */
const bubble = ruleBody('[data-theme="bubblegum"]');
const arena = ruleBody('[data-theme="arena"]');
ok(/--holo-blend:\s*overlay/.test(bubble), "light theme blends foil with overlay");
ok(/--holo-blend:\s*color-dodge/.test(arena), "dark theme keeps color-dodge");
ok(/--sleeve-bright:\s*1\./.test(bubble), "light theme brightens the sleeve frost");
ok(/--sleeve-bright:\s*\./.test(arena), "dark theme darkens it");

/* ====================================================================== */
section("face reveal is gentler than it was");
eq(SLEEVE_COVER.length, 6, "one sleeve position per guess");
eq(SLEEVE_FROST.length, 6, "one frost level per guess");
eq(SLEEVE_SAT.length, 6, "one saturation level per guess");
ok(SLEEVE_FROST[0] <= 10,
   `opening blur is gentle (${SLEEVE_FROST[0]}px, was 13px flat)`);
ok(SLEEVE_FROST.every((v, i, a) => i === 0 || v < a[i - 1]),
   "frost eases off monotonically");
ok(SLEEVE_FROST[0] - SLEEVE_FROST[5] <= 6,
   "and only eases off a little — the sleeve sliding out is still the main reveal");
ok(SLEEVE_COVER.every((v, i, a) => i === 0 || v < a[i - 1]),
   "the sleeve only ever retracts");
ok(SLEEVE_SAT.every((v, i, a) => i === 0 || v > a[i - 1]),
   "colour comes back as it retracts");

/* ====================================================================== */
section("endless filters");
DATA.groups.forEach(g => { groupByName[g.name] = g; });
// Mirror init(): a soloist owns her own tracks, so she needs an entry too.
DATA.members.filter(m => m.group === "Soloist").forEach(m => {
  groupByName[m.name] = {name: m.name, gen: m.gen, tier: m.tier,
                         status: "Active", kr: m.kr, soloist: true};
});
S.mode = "song"; S.play = "endless";
const f = defaultFilters();
S.filters = f;
const wholePool = MODES.song.pool().length;
eq(endlessPool().length, wholePool, "defaults exclude nothing");

const groupsIn = () => [...new Set(endlessPool().map(x => x.group))].sort();

/* The two the user asked for by name, and the additive behaviour. */
eq(PINNED, ["TWICE", "LE SSERAFIM"], "TWICE and LE SSERAFIM are the quick picks");
PINNED.forEach(n => ok(DATA.groups.some(g => g.name === n),
                       `quick pick "${n}" is a real group`));

S.filters = Object.assign(defaultFilters(), {groups: ["TWICE"]});
eq(groupsIn(), ["TWICE"], "one group selected -> only that group");
const twiceOnly = endlessPool().length;
ok(twiceOnly > 0 && twiceOnly < wholePool, `TWICE alone narrows the pool (${twiceOnly})`);

S.filters = Object.assign(defaultFilters(), {groups: ["TWICE", "LE SSERAFIM"]});
eq(groupsIn(), ["LE SSERAFIM", "TWICE"], "both selected -> both, not neither");
ok(endlessPool().length > twiceOnly, "adding a group widens rather than narrows");

/* Read tier and generation the way passes() does — off the item, falling back
   to its group. Soloists have no group to look up, which used to crash this. */
const tierOfItem = x => x.tier != null ? x.tier
                        : (groupByName[x.group || x.name] || {}).tier;
const genOfItem  = x => x.gen  != null ? x.gen
                        : (groupByName[x.group || x.name] || {}).gen;

S.filters = Object.assign(defaultFilters(), {tiers: [1]});
ok(endlessPool().every(x => tierOfItem(x) === 1), "tier filter keeps only tier 1");
ok(groupsIn().length >= 5,
   `tier 1 still leaves a real pool (${groupsIn().length} artists)`);

S.filters = Object.assign(defaultFilters(), {gens: [5]});
ok(endlessPool().every(x => genOfItem(x) === 5), "generation filter holds");

/* Soloists have to be filterable too — they carry gen 2, which nothing else
   does, and "Soloist" has to work as a group chip. */
S.filters = Object.assign(defaultFilters(), {gens: [2]});
ok(endlessPool().every(x => genOfItem(x) === 2), "generation 2 filters cleanly");
S.mode = "member";
S.filters = Object.assign(defaultFilters(), {groups: ["Soloist"]});
ok(endlessPool().length > 0 &&
   endlessPool().every(m => m.group === "Soloist"),
   `"Soloist" works as a group filter (${endlessPool().length} entries)`);
S.mode = "song";

/* An impossible combination must fall back to everything rather than deal
   undefined forever. */
S.filters = Object.assign(defaultFilters(), {gens: []});
eq(endlessPool().length, wholePool, "no generations selected -> falls back to all");
S.filters = Object.assign(defaultFilters(), {groups: ["TWICE"], gens: [3], tiers: [3]});
eq(endlessPool().length, wholePool, "contradictory filters -> falls back to all");

/* Member-only switches */
S.mode = "member";
S.filters = Object.assign(defaultFilters(), {former: false});
ok(!endlessPool().some(m => m.status === "Left"),
   "former members can be excluded");
S.filters = Object.assign(defaultFilters(), {disbanded: false});
ok(!endlessPool().some(m => groupByName[m.group] &&
                            groupByName[m.group].status !== "Active"),
   "disbanded and inactive groups can be excluded");
ok(endlessPool().some(m => m.group === "Soloist"),
   "excluding disbanded groups does not sweep out soloists, who have none");

S.filters = defaultFilters();
S.play = "daily"; S.mode = "member";

/* Filters must never touch Daily — everyone has to get the same puzzle. */
const before = dailyAnswer("member", 42).id;
S.filters = Object.assign(defaultFilters(), {groups: ["TWICE"]});
eq(dailyAnswer("member", 42).id, before, "filters do not affect the daily answer");
S.filters = defaultFilters();

/* ====================================================================== */
section("volume");
ok(typeof G.loadVolume === "function", "volume is persisted");
eq(G.loadVolume(), 0.8, "defaults to 80% with nothing stored");

/* ====================================================================== */
section("stage photos");
const {photoOf, commons} = G;
const withImgs = DATA.members.filter(m => m.imgs);
const groupsWithImgs = DATA.groups.filter(g => g.imgs);
ok(withImgs.length > 80,
   `stage photos reached the payload (${withImgs.length} members, ` +
   `${groupsWithImgs.length} groups)`);

const badList = DATA.members.concat(DATA.groups).filter(
  x => x.imgs && (!Array.isArray(x.imgs) || !x.imgs.length ||
                  x.imgs.some(f => typeof f !== "string" || !f.trim())));
eq(badList.map(x => x.name), [], "every imgs entry is a non-empty filename");

const overCap = withImgs.concat(groupsWithImgs).filter(x => x.imgs.length > 12);
eq(overCap.map(x => x.name), [], "no subject carries more than 12 photos");

/* The P18 fallback is what saves the page when Commons renames a file, so
   nothing may ship stage photos without one. */
/* A member showing a stage photo must have something to fall back to: the P18
   portrait, or failing that a second stage photo. */
const noFallback = DATA.members.filter(
  m => m.imgs && !m.img && m.imgs.length < 2);
eq(noFallback.map(m => m.name), [],
   "every member with stage photos has a fallback image");
const noPortrait = DATA.members.filter(m => m.imgs && !m.img).map(m => m.name);
console.log(`   (${noPortrait.length} members have stage photos but no P18 ` +
            `portrait: ${noPortrait.join(", ") || "none"})`);

/* photoOf must be total: it has to answer for the 91 members who have none. */
const noPhotos = DATA.members.find(m => !m.imgs);
ok(noPhotos, "some members have no stage photo (expected — Commons gap)");
if (noPhotos) eq(photoOf(noPhotos, 5), noPhotos.img,
                 "a member with no stage photo falls back to her portrait");

const one = withImgs[0];
eq(photoOf(one, 3), photoOf(one, 3), "same seed picks the same photo");
eq(photoOf(one, one.imgs.length), photoOf(one, 0), "the seed wraps around");
eq(photoOf(one, -1), one.imgs[one.imgs.length - 1], "a negative seed still lands in range");
ok(new Set(Array.from({length: one.imgs.length}, (_, i) => photoOf(one, i))).size
   === one.imgs.length, "walking the seed visits every photo");

/* URLs have to survive encoding: these filenames are Korean and full of spaces,
   commas and parentheses. */
const sample = withImgs.slice(0, 30).map(m => commons(m.imgs[0], 400));
ok(sample.every(u => /^https:\/\/commons\.wikimedia\.org\/wiki\/Special:FilePath\//.test(u)),
   "photo urls point at Commons FilePath");
ok(sample.every(u => !/[ ]/.test(u)), "no raw spaces survive into the url");


/* ====================================================================== */
section("soloists");
const solo = DATA.members.filter(m => m.group === "Soloist");
ok(solo.length >= 15, `soloists reached the pool (${solo.length})`);

/* They have no group, so every column that a group would supply has to be
   filled in from the soloist's own row instead — a blank cell in the grid
   reads as a hint. */
const SOLO_REQ = ["company", "parent", "nationality", "gen", "size",
                  "debut", "birth", "status", "display", "search", "tier"];
eq(solo.filter(m => SOLO_REQ.some(k => m[k] === undefined || m[k] === null ||
                                       m[k] === "")).map(m => m.name),
   [], "every soloist has all scored columns");
eq(solo.filter(m => m.size !== 1).map(m => m.name), [], "a soloist is a group of one");
eq(solo.filter(m => m.status !== "Soloist").map(m => m.name), [],
   "soloists are marked Soloist, not Active/Left");

/* Nobody appears twice. Matching on name would have been wrong — Wonder Girls'
   Yubin and tripleS's YuBin are different people. */
const qids = DATA.members.map(m => m.qid).filter(Boolean);
eq(qids.length - new Set(qids).size, 0, "no person appears twice in the pool");
ok(solo.some(m => /^yubin$/i.test(m.name)),
   "the soloist Yubin survived the collision with tripleS's YuBin");

/* Shared names must be distinguishable in the dropdown, case-insensitively. */
const byLower = {};
DATA.members.forEach(m => {
  (byLower[m.name.toLowerCase()] = byLower[m.name.toLowerCase()] || []).push(m);
});
const ambiguous = Object.values(byLower).filter(g => g.length > 1)
  .flat().filter(m => m.display === m.name);
eq(ambiguous.map(m => m.name), [], "every shared name is disambiguated on screen");

/* Soloists must grade cleanly against each other and against group members. */
solo.forEach(m => {
  const bad = MEMBER_COLS.filter(c => grade(m, m, c).r !== "hit").map(c => c.k);
  eq(bad, [], `${m.name} grades all-green against herself`);
});
const aGroupMember = DATA.members.find(m => m.group !== "Soloist");
ok(grade(solo[0], aGroupMember, MEMBER_COLS[0]).r === "miss",
   "a soloist does not match a group member on Group");

/* Generation 2 exists only because of soloists. */
const gen2 = DATA.members.filter(m => m.gen === 2);
ok(gen2.length > 0 && gen2.every(m => m.group === "Soloist"),
   `generation 2 is soloists only (${gen2.map(m => m.name).join(", ")})`);
ok(G.defaultFilters().gens.includes(2),
   "the generation filter offers 2, or those soloists are unreachable in endless");

/* The former group is a fact, not a scored column — it must not be gradeable. */
eq(MEMBER_COLS.filter(c => c.k === "former").map(c => c.k), [],
   "'former group' is not a scored column");
ok(solo.filter(m => m.former).length >= 5,
   "several soloists carry the group they came from");

/* ====================================================================== */
section("song catalogue");
const versionTagged = DATA.songs.filter(
  s => /ver\.?|version|instrumental|remix/i.test(s.title));
eq(versionTagged.slice(0, 12).map(s => s.group + " / " + s.title), [],
   "no alternate-version tracks leaked in");
const singles = DATA.songs.filter(s => s.single);
const cuts = DATA.songs.filter(s => !s.single);
ok(singles.length > 200, `curated title tracks present (${singles.length})`);
ok(DATA.songs.length > 1000,
   `the catalogue actually landed (${DATA.songs.length} tracks, ` +
   `${cuts.length} album cuts)`);

/* Every track has to be playable: the URL is resolved at play time from the
   id, so a missing id is a dead entry. */
eq(DATA.songs.filter(s => !s.track).map(s => s.group + " / " + s.title), [],
   "every track has a Deezer id to resolve at play time");

/* Album art is stored as Deezer's cover hash and the URL is rebuilt in the
   page — 3,300 full URLs would be a third of a megabyte of duplication. */
const badArt = DATA.songs.filter(s => s.art && !/^[0-9a-f]{32}$/.test(s.art));
eq(badArt.slice(0, 6).map(s => s.title + ": " + s.art), [],
   "album art is stored as a bare cover hash");
ok(DATA.songs.filter(s => s.art).length > 500, "most tracks have cover art");

/* Daily must stay on title tracks — a shared daily puzzle built on album cuts
   nobody has heard would be unfair. Endless is where the deep cuts live. */
const singleIds = new Set(singles.map(s => s.id));
const dailyCuts = (DATA.schedules.song || []).filter(id => !singleIds.has(id));
eq([...new Set(dailyCuts)], [], "the daily song is always a title track");
S.mode = "song"; S.play = "endless"; S.filters = G.defaultFilters();
ok(endlessPool().length > singles.length,
   `endless reaches past the title tracks (${endlessPool().length})`);

/* ...and the switch to narrow it back down works. */
S.filters = Object.assign(G.defaultFilters(), {singlesOnly: true});
ok(endlessPool().every(s => s.single),
   "\"title tracks only\" excludes album cuts");
ok(endlessPool().length > 100, "and still leaves a real pool");
S.filters = G.defaultFilters();

/* Search keys are normalised at build time now; anything unfolded would never
   match, because the query is folded before comparison. */
const unfolded = DATA.songs.concat(DATA.members).slice(0, 400)
  .filter(x => x.search.some(k => k !== norm(k)));
eq(unfolded.map(x => x.title || x.name), [],
   "search keys are already normalised");
findsIt2("hype boy", "Hype Boy");
function findsIt2(q, title) {
  S.mode = "song"; S.play = "endless"; S.filters = G.defaultFilters();
  ok(candidates(q).some(x => x.title === title), `"${q}" finds ${title}`);
}
S.mode = "member"; S.play = "daily";

section("hints");
const { HINTS, hintsFor, takeHint } = G;
S.play = "endless";

/* Grid modes score every column already; a hint there would be a free tile. */
S.mode = "member"; eq(hintsFor(), [], "no hints in Idol — the grid is the hint");
S.mode = "group";  eq(hintsFor(), [], "no hints in Group");
S.mode = "image";  ok(hintsFor().length >= 3, "Face offers hints");
S.mode = "song";   ok(hintsFor().length >= 3, "Song offers hints");

/* Every hint has to produce something for every possible answer, or a stuck
   player spends a guess on an empty chip. */
["image", "song"].forEach(mode => {
  S.mode = mode;
  const pool = MODES[mode].pool();
  const sample = [pool[0], pool[(pool.length / 2) | 0], pool[pool.length - 1]];
  hintsFor().forEach(h => {
    const empty = sample.filter(a => {
      const v = h.of(a);
      return v == null || v === "" || v === "undefined";
    });
    eq(empty.length, 0, `${mode}: "${h.label}" resolves for every answer`);
  });
});

/* A hint costs a guess — that is what stops it being a free win — and it must
   never spend the last one. */
S.mode = "song"; S.play = "endless";
G.startRound(false);
const guessesBeforeHint = S.guesses.length;
takeHint();
eq(S.guesses.length, guessesBeforeHint + 1, "a hint spends a guess");
eq(S.hints.length, 1, "and is recorded");
S.guesses = new Array(G.MAXG() - 1).fill(null);
const stuck = S.hints.length;
takeHint();
eq(S.hints.length, stuck, "the last guess cannot be spent on a hint");
S.guesses = []; S.hints = []; S.done = false;
S.play = "daily"; S.mode = "member";


/* ====================================================================== */
section("filters do not persist a group pick");
/* Generation, fame and the include-switches are standing preferences and are
   remembered. A specific group is not: reloading into a filter set weeks ago
   makes Endless look permanently narrow. */
const saved = JSON.stringify({gens: [4], tiers: [1], groups: ["TWICE"],
                              former: false, disbanded: false,
                              singlesOnly: true});
sandbox.localStorage.setItem("biasdle.filters", saved);
const restored = G.loadFilters ? G.loadFilters() : null;
ok(restored, "loadFilters is reachable");
if (restored) {
  eq(restored.groups, [], "a saved group pick is not restored");
  eq(restored.gens, [4], "generation preference survives");
  eq(restored.tiers, [1], "fame preference survives");
  eq(restored.former, false, "the include-switches survive");
  eq(restored.singlesOnly, true, "title-tracks-only survives");
}
sandbox.localStorage.setItem("biasdle.filters", "");

/* ====================================================================== */
/* KEEP THIS LAST. Appending a section after the summary means it runs after
   the exit code is decided, so a failure in it is reported and then ignored.
   This has now been fixed twice. */
console.log(`\n${pass} passed, ${fail} failed`);
if (fail) {
  console.log("\nFAILURES:");
  failures.forEach(f => console.log("  ✗ " + f));
  process.exit(1);
}

/* ====================================================================== */
