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
  style: {}, classList: {add: noop, remove: noop, contains: () => false},
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
    createElement: () => stubEl(), addEventListener: noop,
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

const badDebut = DATA.members.filter(m => !(m.debut >= 2014 && m.debut <= 2026));
eq(badDebut.map(m => `${m.name}:${m.debut}`), [], "debut years inside gen 3-5");

/* Size must equal the number of members actually shipped for that group,
   otherwise the Members column's arrows point the wrong way. */
const counted = {};
DATA.members.forEach(m => { counted[m.group] = (counted[m.group] || 0) + 1; });
const sizeMismatch = DATA.members
  .filter(m => m.size !== counted[m.group])
  .map(m => `${m.group}: column says ${m.size}, pool has ${counted[m.group]}`);
eq([...new Set(sizeMismatch)], [], "group size column matches the shipped roster");

const gSizeMismatch = DATA.groups
  .filter(g => g.size !== (counted[g.name] || 0))
  .map(g => `${g.name}: ${g.size} vs ${counted[g.name]}`);
eq(gSizeMismatch, [], "group-mode size matches member pool");

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
 ["Seunghee", "OH MY GIRL"], ["Olivia Hye", "LOONA"], ["Zoa", "Weeekly"],
 ["Onda", "EVERGLOW"], ["Aisha", "EVERGLOW"], ["Yunjin", "LE SSERAFIM"],
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
  ok(perGroup(1) >= perGroup(3) * 2.5,
     `${mode}: a tier-1 group gets at least 2.5x a tier-3 group's days`);
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
  const noPrev = DATA.songs.filter(s => !s.preview);
  eq(noPrev.map(s => s.title), [], "every song has a preview url");
  const badHost = DATA.songs.filter(s => !/^https:\/\//.test(s.preview));
  eq(badHost.map(s => s.title), [], "preview urls are https");
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

S.filters = Object.assign(defaultFilters(), {tiers: [1]});
const t1 = groupsIn();
ok(t1.every(n => groupByName[n].tier === 1), "tier filter keeps only tier 1");
ok(t1.length >= 5, `tier 1 still leaves a real pool (${t1.length} groups)`);

S.filters = Object.assign(defaultFilters(), {gens: [5]});
ok(groupsIn().every(n => groupByName[n].gen === 5), "generation filter holds");

/* An impossible combination must fall back to everything rather than deal
   undefined forever. */
S.filters = Object.assign(defaultFilters(), {gens: []});
eq(endlessPool().length, wholePool, "no generations selected -> falls back to all");
S.filters = Object.assign(defaultFilters(), {groups: ["TWICE"], gens: [3], tiers: [3]});
eq(endlessPool().length, wholePool, "contradictory filters -> falls back to all");

/* Member-only switches */
S.mode = "member";
S.filters = Object.assign(defaultFilters(), {former: false});
ok(!endlessPool().some(m => m.status === "Former member"),
   "former members can be excluded");
S.filters = Object.assign(defaultFilters(), {disbanded: false});
ok(!endlessPool().some(m => groupByName[m.group].status !== "Active"),
   "disbanded and inactive groups can be excluded");

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
console.log(`\n${pass} passed, ${fail} failed`);
if (fail) {
  console.log("\nFAILURES:");
  failures.forEach(f => console.log("  ✗ " + f));
  process.exit(1);
}
