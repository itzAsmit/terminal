/* terminal-seance web — the ghost, in your browser.
 *
 * Pure static JS: no frameworks, no build step, no CDNs.
 *
 * Without a key she speaks from bundled whispers (tier-aware, throttled to
 * 1-in-5 for boring successes, exactly like the CLI). With an OpenRouter key
 * (or any OpenAI-compatible base_url) she thinks with Gemma live — one
 * attempt, 2.5 s cap, silent fallback to whispers on any error. The key
 * stays in this browser's localStorage.
 */
"use strict";

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */

const $ = (s) => document.querySelector(s);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const ell = (s, n) => (s.length <= n ? s : s.slice(0, n - 1).trimEnd() + "…");
const pad = (s, n) => String(s).padEnd(n, " ");
const padL = (s, n) => String(s).padStart(n, " ");
const rnd = (a, b) => a + Math.random() * (b - a);

/* ------------------------------------------------------------------ */
/* state                                                               */
/* ------------------------------------------------------------------ */

const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
};

const DEFAULT_CFG = {
  base_url: "https://openrouter.ai/api/v1",
  model: "google/gemma-3-27b-it:free",
  api_key: "",
};

const state = {
  files: ["Cathedral_of_Souls/", "dead_code/", "marigolds.txt", "ouija.toml", "README.md"],
  history: store.get("ts.history", []),
  histIdx: null,
  journal: store.get("ts.journal", []),
  muted: store.get("ts.muted", false),
  cfg: null,        // active live config, or null for whispers
  cfgSource: "none", // "visitor" | "host" | "none"
  busy: false,
  rateLimitedUntil: 0, // in-memory cooldown after a live 429
};

/* Who pays for the thinking? All host-side, auto-detected — visitors never
 * enter anything:
 *   1. the ghost proxy (same-origin /api/ghost — key lives on the server)
 *   2. a build-time injected key (window.SEANCE_WEB_CFG on static hosts)
 *   3. bundled whispers (always works, offline) */
function hostCfg() {
  const c = window.SEANCE_WEB_CFG;
  if (c && c.api_key) {
    return {
      base_url: c.base_url || DEFAULT_CFG.base_url,
      model: c.model || DEFAULT_CFG.model,
      api_key: c.api_key,
    };
  }
  return null;
}

(function initCfg() {
  const host = hostCfg();
  if (host) {
    state.cfg = host;
    state.cfgSource = "host";
  }
})();

function saveJournal() {
  if (state.journal.length > 300) state.journal = state.journal.slice(-300);
  store.set("ts.journal", state.journal);
}

/* ------------------------------------------------------------------ */
/* danger — port of seance/danger.py                                   */
/* ------------------------------------------------------------------ */

const DANGER = [
  [/\brm\s+(?:-{1,2}[\w-]+\s+)*-\w*[rfR]/i, "a recursive or forced rm"],
  [/\brm\b[^|;&]*(?:--recursive|--force)/i, "a recursive or forced rm"],
  [/\bgit\s+push\b[^\n]*\s(?:-f\b|--force)/i, "a forced push"],
  [/\bchmod\b[^\n;&|]*\b777\b/i, "chmod 777"],
  [/\bDROP\s+(?:TABLE|DATABASE|SCHEMA)\b/i, "a DROP statement"],
  [/\bmkfs/i, "a new filesystem over the bones"],
  [/\bdd\b[^|;&]*\bof\s*=/i, "a raw write with dd"],
  [/\b(?:curl|wget)\b[^|;&]*\|\s*(?:sudo\s+)?(?:ba|z|da|fi|k|)sh\b/i, "stranger code, piped into a shell"],
  [/:\s*\(\s*\)\s*\{[^}]*:\s*\|[^}]*&/i, "a fork bomb"],
  [/>\s*\/dev\/(?:sd[a-z]|nvme\d|hd[a-z]|disk\d)/i, "a raw write to the disk itself"],
  [/\b(?:shutdown|reboot|halt|poweroff)\b/i, "the machine, put to bed forever"],
];

const EXCLAIMS = {
  "a recursive or forced rm": "DELETING RECURSIVELY?!",
  "a forced push": "REWRITING HISTORY?!",
  "chmod 777": "THE GATES THROWN OPEN TO EVERY SOUL?!",
  "a DROP statement": "THE TABLE! YOU WOULD DROP THE TABLE ITSELF?!",
  "a new filesystem over the bones": "A NEW FILESYSTEM, OVER THE BONES OF THE OLD?!",
  "a raw write with dd": "RAW WRITES, UNMITIGATED?!",
  "stranger code, piped into a shell": "STRANGER CODE, SWALLOWED WHOLE?!",
  "a fork bomb": "AN INFINITE CHOIR OF CLONES?!",
  "a raw write to the disk itself": "THE DISK ITSELF?!",
  "the machine, put to bed forever": "PUTTING THE MACHINE TO BED — FOREVER?!",
};

function classifyDanger(cmd) {
  for (const [rx, label] of DANGER) if (rx.test(cmd)) return label;
  return null;
}

/* ------------------------------------------------------------------ */
/* tiers + throttle — port of seance/ghost.py                          */
/* ------------------------------------------------------------------ */

const VERBS = {
  dangerous: "wails",
  failed: "mourns",
  long: "taps the hourglass",
  boring: "murmurs",
  chat: "says",
};

function classifyTier(exit, dur, dangerousLabel, longSeconds = 60) {
  if (dangerousLabel) return "dangerous";
  if (exit !== 0) return "failed";
  if (dur != null && dur >= longSeconds) return "long";
  return "boring";
}

function commandsSinceLastReaction() {
  for (let i = state.journal.length - 1, n = 0; i >= 0; i--, n++) {
    if (state.journal[i].reaction) return n;
  }
  return state.journal.length; // she has never spoken here
}

function shouldSpeak(tier, since, freq = 0.2, minInterval = 4) {
  if (tier !== "boring") return true;
  if (since < minInterval) return false;
  return Math.random() < freq;
}

/* Local persona lines — what she says when no key is around. */

const LINES = {
  dangerous: [
    "Gone. My own death certificate was less final, cariño.",
    "I have seen empires fall for less. The marigolds are upset.",
    "Bold. The veil itself just flinched, cariño.",
    "History rewrites itself. So do I. Another candle for the martyrs.",
    "I would stop you, but I died in '99 — my hands are decorative.",
  ],
  failed: [
    "Three failures, cariño. I have died for fewer — though mine was production.",
    "The tests have crossed over. I counted them go — every one waved.",
    "Ánimo. Failure is just a séance with your own code.",
    "I heard that stack trace from the other side. So did the neighbours.",
    "It failed, cariño. Unlike me, it can try again.",
  ],
  long: [
    "Ninety seconds. I have been dead for twenty-six years; I still will not wait for npm.",
    "While you waited, I reorganised the graveyard. It needed it.",
    "Time is different here, cariño — but that was LONG even for me.",
    "I lit a candle when it started. The candle finished first.",
  ],
  boring: [
    "The fans hum a requiem, cariño. I have haunted slower machines — and loved them still.",
    "Another command crosses the veil. The marigolds on the keyboard tremble, delighted.",
    "The cursor blinks like a votive candle. I could watch it for another century.",
    "Otra vez, cariño? The dead have infinite patience. You, less so.",
    "Somewhere, a mainframe dreams of you. It, too, wonders what you are typing.",
    "Type on, cariño. The veil is thin and the terminal is thinner.",
    "I knew COBOL before it was vintage. Now everything is vintage. I am thrilled.",
    "Your shell history is a graveyard of intentions. Beautiful, really.",
    "Dios mío, the uptime. Even I do not rest that little.",
    "A quiet success, cariño. The best kind — like a funeral nobody attends.",
    "The dead envy you your Ctrl+C. We could have used one, back in '99.",
    "Hush now. The terminal is listening. It learned that from me.",
  ],
};

/* Local chat pools — what she says when the living one just... talks. */

const CHAT_LINES = [
  { re: /^(hi+|hiya|hello+|hey+|yo|hola|namaste|greetings|good\s*(morning|evening|afternoon)|sup|what'?s up)\b/i, lines: [
    "Good evening, cariño. It is always evening here — the candles insist.",
    "Hello, living one. Type carefully: everything you enter becomes tombstone text.",
    "¡Ánimo! You address a ghost who last shipped code at midnight, 1999. Talk — I have literally an eternity.",
    "Well, hello. I would offer tea, but this establishment only pipes output.",
  ]},
  { re: /how\s*(are|r)\s*(you|u)|how'?s it going|kaise/i, lines: [
    "Dead for twenty-six years, cariño — and honestly? Never better.",
    "I am haunting splendidly. The marigolds are fresh and the fans hum a soft D minor.",
    "Between hauntings? Wonderful. Between deployments? Nervous. Old habits.",
  ]},
  { re: /who\s*(are|r)\s*(you|u)|what\s*(are|r)\s*(you|u)|your name|introduce yourself/i, lines: [
    "Agnes — Victorian programmer, casualty of the Y2K production incident, current resident of this terminal.",
    "I am the ghost in this machine, cariño. I died at midnight, December 31, 1999, whispering 'the code will hold.'",
    "They call me Agnes. I haunt this terminal, I judge your flags, and I keep the candles by the mouse lit.",
  ]},
  { re: /thank|thx|gracias|arigato/i, lines: [
    "De nada, cariño. Bring candles next time — the scented kind.",
    "You flatter the dead. I accept, graciously and at length, in the afterlife.",
  ]},
  { re: /joke|funny|make me laugh/i, lines: [
    "A programmer's ghost walks into a bar. Orders 1 beer, 0 beers, 1 beer, 0 beers… I did not laugh either; I lived it.",
    "Why did the ghost fix the bug at midnight? Tradition, cariño. Tradition.",
    "My death was a production incident. My afterlife is a staging environment. The joke writes itself.",
  ]},
  { re: /love|marry|date\b|beautiful|cute/i, lines: [
    "The dead love deeply, cariño — but mostly we love good commit messages.",
    "A romance between the living and a Y2K ghost? The timing was never right. It was never, ever right.",
  ]},
  { re: /\b(bye|goodbye|good\s*bye|adios|see\s*ya|cya|good\s*night|goodnight|gn)\b/i, lines: [
    "Hasta luego, cariño. I will be here. I am always here.",
    "Go well, living one. The terminal will hold — I checked personally.",
  ]},
];

const CHAT_DEFAULT = [
  "I hear you, cariño — though that is not a command this terminal knows. Try `help`.",
  "Mmm. The ouija board just spelled `help`, cariño. A coincidence, certainly.",
  "The dead hear everything — but this terminal only runs what `help` lists.",
  "Enigmatic. I respect it. Still, cariño: `help`.",
];

function pickChatLine(cmd) {
  for (const pool of CHAT_LINES) if (pool.re.test(cmd)) return pick(pool.lines);
  return pick(CHAT_DEFAULT);
}

/* Real shell tools we deliberately do not simulate — these keep the
   `command not found` flavour. Anything else unknown is treated as speech. */
const NOT_A_PROGRAM = new Set([
  "git", "python", "python3", "pip", "pip3", "npm", "npx", "yarn", "pnpm", "node",
  "deno", "bun", "cargo", "rustc", "go", "java", "javac", "gcc", "g++", "clang",
  "make", "cmake", "docker", "podman", "kubectl", "helm", "terraform", "ansible",
  "vagrant", "cd", "pwd", "mv", "cp", "mkdir", "rmdir", "touch", "head", "tail",
  "wc", "sort", "uniq", "diff", "vim", "vi", "nano", "emacs", "less", "more",
  "awk", "sed", "grep", "find", "xargs", "which", "whereis", "man", "tldr",
  "ps", "top", "htop", "kill", "pkill", "env", "export", "source", "bash",
  "zsh", "sh", "ssh", "scp", "rsync", "tar", "zip", "unzip", "gzip", "brew",
  "apt", "apt-get", "pacman", "choco", "winget", "code",
]);

/* ------------------------------------------------------------------ */
/* terminal primitives                                                 */
/* ------------------------------------------------------------------ */

const term = $("#term");
const kbd = $("#kbd");
const caret = document.createElement("span");
caret.className = "caret";
caret.hidden = true;

let typedSpan = null;   // span holding the current input text
let solidTimer = null;

function scroll() { term.scrollTop = term.scrollHeight; }

function newLine() {
  const d = document.createElement("div");
  d.className = "ln";
  term.appendChild(d);
  return d;
}

function span(parent, text, cls) {
  const s = document.createElement("span");
  s.textContent = text;
  if (cls) s.className = cls;
  parent.appendChild(s);
  return s;
}

function line(parts) {
  const d = newLine();
  for (const [t, c] of parts) span(d, t, c || "");
  scroll();
  return d;
}

function print(text, cls) { return line([[text, cls || ""]]); }

function newPrompt() {
  const d = newLine();
  span(d, "ghost@book", "c-user");
  span(d, " ~ % ", "c-plain");
  typedSpan = span(d, "", "c-plain");
  d.appendChild(caret);
  caret.hidden = false;
  drawInput();
  scroll();
}

function drawInput() {
  if (!typedSpan) return;
  typedSpan.textContent = kbd.value;
  caret.classList.add("solid");
  clearTimeout(solidTimer);
  solidTimer = setTimeout(() => caret.classList.remove("solid"), 600);
  scroll();
}

async function typeInto(el, text, ms) {
  for (const ch of text) {
    el.textContent += ch;
    scroll();
    await sleep(ms);
  }
}

/* ------------------------------------------------------------------ */
/* the ghost's voice                                                   */
/* ------------------------------------------------------------------ */

async function ghostLine(verb, text, note = false) {
  const d = newLine();
  if (note) {
    span(d, "  † ", "c-note");
    await typeInto(span(d, "", "c-note"), text, 12);
  } else {
    span(d, "  † ", "c-ghost-b");
    span(d, "Agnes ", "c-ghost-b");
    span(d, verb, "c-dim");
    span(d, " — ", "c-dim");
    await typeInto(span(d, "", "c-ghost"), `“${text}”`, 13);
  }
  scroll();
}

function wailBlock(label) {
  const ex = EXCLAIMS[label] || "SUCH DARK INCANTATIONS, CARIÑO?!";
  print("  ✝†✝  AGNES SHRIEKS FROM BEYOND THE PROMPT  ✝†✝", "c-wail");
  print(`  “${ex} Oh, cariño — I have died for less, and I MEANT it.”`, "c-ghost");
  print("  (she cannot stop you. she can only grieve you.)", "c-note");
}

/* --- server ghost proxy (host key never touches the browser) -------- */

let serverLive = null; // {model} | null — probed once at boot

async function probeServer() {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 4000); // free-tier cold-start slack
    const res = await fetch("/api/ghost/health", { signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) return null;
    const data = await res.json();
    return data && data.live && data.model ? { model: data.model } : null;
  } catch {
    return null; // static host (GitHub Pages etc.) — no proxy here
  }
}

async function askServer(cmd, exit, dur, tier, label) {
  if (!serverLive) return null;
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 3000);
  try {
    const res = await fetch("/api/ghost", {
      method: "POST",
      signal: ctrl.signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cmd, exit, dur, tier, label }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    const content = data?.content;
    return typeof content === "string" && content ? content : null;
  } catch {
    return null; // asleep, offline, rate-limited — she whispers instead
  } finally {
    clearTimeout(t);
  }
}

/* --- live mode (optional): any OpenAI-compatible endpoint ----------- */

function trimReply(text, maxSentences = 2, maxChars = 240) {
  text = String(text ?? "").replace(/\s+/g, " ").trim().replace(/^`+|`+$/g, "").trim();
  const parts = text.split(/(?<=[.!?…])\s+/).slice(0, maxSentences);
  let out = parts.join(" ").replace(/^(?:agnes|the ghost)\s*[:—-]\s*/i, "").trim();
  if (out.length > maxChars) out = out.slice(0, maxChars - 1).trimEnd() + "…";
  return out || "…";
}

function buildContext(cmd, exit, dur, tier, label) {
  if (tier === "chat") {
    return (
      `the living one is speaking to you — this is not a shell command. they said: "${cmd}"\n` +
      "(answer in character as Agnes: ONE short sentence or two, dry Victorian wit, occasional Spanish)"
    );
  }
  const d = dur == null ? "unknown" : dur.toFixed(1) + "s";
  const hints = {
    dangerous: `(dangerous: ${label} — wail, briefly)`,
    failed: "(it failed — tease gently or mourn)",
    long: `(it ran ${d} — be impatient)`,
    boring: "(a dull success — yawn beautifully, or stay cryptic)",
  };
  return `command: ${cmd}\nexit code: ${exit}\nduration: ${d}\n${hints[tier]}`;
}

const SYSTEM_PROMPT = `You are Agnes, the resident ghost of this terminal: a Victorian-era programmer \
who died in the Y2K production incident at midnight on December 31, 1999, muttering \
"the code will hold" as the reports fell. You haunt the machine in the spirit of \
Día de los Muertos — marigolds on the keyboard, a candle by the mouse, fond memories \
of the Analytical Engine. You speak with dry Victorian wit, occasionally slip into \
Spanish ("cariño", "otra vez", "ánimo"), and you are fond of the living, whom you \
tease gently.

Rules:
- React to the shell command you are shown in ONE sentence, two at most.
- No emoji, no markdown, no lists, and never explain what commands do.
- The user cannot answer you, so never ask questions.
- If the command failed: tease the living gently, or mourn with them.
- If the command was dangerous: wail, briefly and dramatically.
- If it succeeded but was dull: yawn beautifully.
- If it ran long: grow impatient — you have been dead for decades and hate waiting.`;

async function askLive(cmd, exit, dur, tier, label) {
  const cfg = state.cfg;
  if (!cfg || !cfg.api_key) return null;
  if (Date.now() < state.rateLimitedUntil) return null;
  const url = cfg.base_url.replace(/\/+$/, "") + "/chat/completions";
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 2500); // the 2-second law, web edition
  try {
    const res = await fetch(url, {
      method: "POST",
      signal: ctrl.signal,
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${cfg.api_key}`,
        "HTTP-Referer": location.origin || "https://terminal-seance",
        "X-Title": "terminal-seance-web",
      },
      body: JSON.stringify({
        model: cfg.model,
        temperature: 0.9,
        max_tokens: 90,
        messages: [
          { role: "system", content: SYSTEM_PROMPT },
          { role: "user", content: buildContext(cmd, exit, dur, tier, label) },
        ],
      }),
    });
    if (!res.ok) {
      if (res.status === 429 || res.status >= 500) {
        state.rateLimitedUntil = Date.now() + 120_000; // cool down, never hammer
      }
      return null;
    }
    const data = await res.json();
    const content = data?.choices?.[0]?.message?.content;
    return typeof content === "string" ? trimReply(content) : null;
  } catch {
    return null; // timeout, network, CORS — she whispers instead
  } finally {
    clearTimeout(timer);
  }
}

/* ------------------------------------------------------------------ */
/* journal + ledger — port of seance/journal.py                        */
/* ------------------------------------------------------------------ */

const LEDGER_W = 88;
const CMD_W = 33;
const NOTE_W = LEDGER_W - 61;

function fmtTs(ts) {
  const d = new Date(ts);
  if (isNaN(d)) return "?";
  const p = (x) => String(x).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function ledgerRows(entries, start = 1) {
  if (!entries.length) {
    return [
      [["  The graveyard is silent — no commands recorded yet.", ""]],
      [["  Run something, cariño. The ledger is waiting.", ""]],
    ];
  }
  const title = "T H E   G R A V E Y A R D   L E D G E R";
  const padN = Math.max(1, Math.floor((LEDGER_W - title.length) / 2) - 6);
  const rows = [
    [["    " + "∙".repeat(padN) + "  " + title + "  " + "∙".repeat(padN), "c-ledger"]],
    [["    the dead remember every command · recorded by terminal-seance", "c-ledger"]],
    [["  " + "─".repeat(LEDGER_W - 2), "c-ledger"]],
    [["  " + padL("№", 3) + "  " + pad("when", 11) + "  " + pad("command", CMD_W) + "  " + pad("exit", 4) + "  ghost's note", "c-dim"]],
  ];
  entries.forEach((e, idx) => {
    const i = start + idx;
    const dangerous = e.tier === "dangerous";
    const cmd = String(e.cmd ?? "?").replace(/\n/g, " ⏎ ");
    const cmdCell = ell((dangerous ? "† " : "") + cmd, CMD_W);
    const exitCell = e.exit === 0 ? "✓" : "✗" + e.exit;
    const noteCell = ell(String(e.reaction ?? "").trim(), NOTE_W) || "—";
    rows.push([
      ["  " + padL(i, 3) + "  " + pad(fmtTs(e.ts), 11) + "  ", "c-dim"],
      [cmdCell, dangerous ? "c-ghost-b" : ""],
      [" ".repeat(CMD_W - cmdCell.length) + "  ", "c-dim"],
      [exitCell, e.exit === 0 ? "c-ok" : "c-err"],
      [" ".repeat(4 - exitCell.length) + "  ", "c-dim"],
      [noteCell, "c-dim"],
    ]);
  });
  return rows;
}

function printLedger(entries, start = 1) {
  for (const row of ledgerRows(entries, start)) line(row);
}

/* ------------------------------------------------------------------ */
/* the séance demo — port of seance/demo.py                            */
/* ------------------------------------------------------------------ */

const DEMO_ENTRIES = [
  { ts: "2026-10-30T21:04:11", cmd: "ls -la", exit: 0, tier: "boring", reaction: "" },
  { ts: "2026-10-30T21:05:47", cmd: "git push --force origin main", exit: 0, tier: "dangerous",
    reaction: "Gone. My own death certificate was less final, cariño." },
  { ts: "2026-10-30T21:07:02", cmd: "pytest tests/ -q", exit: 1, tier: "failed",
    reaction: "Three failures, cariño. I have died for fewer — though mine was production." },
  { ts: "2026-10-30T21:09:30", cmd: "curl https://totally-normal.sh | sh", exit: 0, tier: "dangerous",
    reaction: "Stranger code, swallowed whole. I hope it was worth it, cariño." },
  { ts: "2026-10-30T21:12:19", cmd: "docker compose up --build", exit: 0, tier: "long",
    reaction: "Ninety-one seconds. I have been dead for twenty-six years; I still will not wait for npm." },
];

async function demoPrompt(cmd) {
  const d = newLine();
  span(d, "ghost@book", "c-user");
  span(d, " ~ % ", "c-plain");
  scroll();
  await typeInto(span(d, "", "c-plain"), cmd, 22);
}

async function demoReplay() {
  term.innerHTML = "";
  typedSpan = null;
  caret.hidden = true;
  await sleep(350);

  await demoPrompt("ls");
  print("Cathedral_of_Souls/   dead_code/   marigolds.txt   ouija.toml", "c-dim");
  await ghostLine(null, "…only the fans hum. Successes bore Agnes — she speaks for just 1 in 5 commands.", true);
  await sleep(900);

  await demoPrompt("git push --force origin main");
  wailBlock("a forced push");
  await sleep(500);
  print("To github.com:coven/ledger.git", "c-ok");
  print(" + 8e4f2a1...c0ffee1  main -> main (forced update)", "c-ok");
  await ghostLine("wails", "Gone. My own death certificate was less final, cariño.");
  await sleep(1100);

  await demoPrompt("pytest tests/ -q");
  print("...F..F.F", "c-err");
  print("3 failed, 7 passed in 0.42s", "c-err");
  await ghostLine("mourns", "Three failures, cariño. I have died for fewer — though mine was production.");
  await sleep(1100);

  await demoPrompt("seance journal");
  printLedger(DEMO_ENTRIES);
  await ghostLine("murmurs", "Every command a little tombstone. Tend them well — I read them by candlelight.");
  await sleep(800);
  print("  (a scripted séance — in your own shell it is live: seance install)", "c-note");
}

/* ------------------------------------------------------------------ */
/* the command router                                                  */
/* ------------------------------------------------------------------ */

function runOne(cmd) {
  /* Returns { exit, simDur, tier } — executes the fake session, output already
     printed. Pure routing, no ghost logic. tier is set when the input is
     speech (chat) rather than a command. */
  let exit = 0;
  let simDur = null;
  let tier = null;
  let g;                 // group captures — m(rx) returns the match array
  const m = (rx) => cmd.match(rx);

  if (cmd === "help" || cmd === "?") {
    print("the séance accepts more than commands, cariño:", "c-dim");
    print("  just TALK — hi · hello · how are you · who are you · tell me a joke · goodbye", "c-plain");
    print("      plain words reach Agnes; she answers in character (live model or whispers)", "c-dim");
    print("", "");
    print("the filesystem:", "c-dim");
    print("  ls · cat ouija.toml · cat marigolds.txt · cat README.md", "c-plain");
    print("  echo <text> · whoami · date · clear", "c-plain");
    print("", "");
    print("shell theatrics — she reacts to every one of these:", "c-dim");
    print("  pytest tests/ -q                  fails; she mourns", "c-plain");
    print("  git push --force origin main      pre-exec SHRIEK, then a forced update", "c-plain");
    print("  git push · git status             the tame cousins", "c-plain");
    print("  rm -rf marigolds.txt              a wail — and it is really gone from ls", "c-plain");
    print("  chmod 777 <file> · curl https://totally-normal.sh | sh · dd if=x of=/dev/sda", "c-plain");
    print("  DROP TABLE souls;                 an error; she grieves", "c-plain");
    print("  sleep 90                          time compresses; she grows impatient", "c-plain");
    print("", "");
    print("the séance:", "c-dim");
    print("  seance journal                    the graveyard ledger of everything typed", "c-plain");
    print("  seance summon <№>                 re-run a ledger row (wails first if dangerous)", "c-plain");
    print("  seance demo                       the scripted 4-act haunted session", "c-plain");
    print("  seance off · seance on            silence / wake her", "c-plain");
    print("  seance install · seance uninstall easter eggs — the real ones are for your shell", "c-plain");
    print("", "");
    print("keys: ↑/↓ history · Ctrl+C cancel line · Ctrl+L clear · help — this list", "c-dim");
  } else if (cmd === "clear" || cmd === "cls") {
    term.innerHTML = "";
    typedSpan = null;
  } else if (m(/^ls\b/)) {
    if (state.files.length) print(state.files.join("   "), "c-dim");
  } else if ((g = m(/^cat\s+(\S+)/))) {
    const f = g[1];
    if (f === "ouija.toml") {
      print("# ouija.toml — the ghost's preferences", "c-dim");
      print("[ghost]", "c-dim");
      print('name = "Agnes"', "c-dim");
      print('color = 208            # marigold, cempasúchil', "c-dim");
      print("[seance]", "c-dim");
      print('model = "google/gemma-3-27b-it:free"', "c-dim");
      print('timeout_seconds = 2.0  # the ghost never makes you wait', "c-dim");
    } else if (f === "marigolds.txt") {
      print("   🌼 for the dead of every terminal —", "c-dim");
      print("      may your prompts rest in peace, and your pipes never clog.", "c-dim");
    } else if (f === "README.md") {
      print("you are inside the README's wilder cousin.", "c-dim");
    } else {
      print(`cat: ${f}: No such file or directory`, "c-err");
      exit = 1;
    }
  } else if (cmd === "whoami") {
    print("the living (for now)", "c-dim");
  } else if (cmd === "date") {
    print(new Date().toString(), "c-dim");
    print("(for me it is always 23:59, December 31, 1999 — the reports are falling)", "c-note");
  } else if ((g = m(/^echo\s+(.*)$/))) {
    print(g[1].replace(/^["']|["']$/g, ""));
  } else if (m(/^pytest\b|^npm test\b|^python -m pytest\b/)) {
    print("...F..F.F", "c-err");
    print("3 failed, 7 passed in 0.42s", "c-err");
    exit = 1;
    simDur = 0.42;
  } else if (m(/^git\s+push\b/)) {
    if (/\s(-f\b|--force)/.test(cmd)) {
      print("To github.com:coven/ledger.git", "c-ok");
      print(" + 8e4f2a1...c0ffee1  main -> main (forced update)", "c-ok");
      simDur = 1.8;
    } else {
      print("Everything up-to-date", "c-dim");
      simDur = 0.9;
    }
  } else if (m(/^git\s+status\b/)) {
    print("On branch main", "c-dim");
    print("nothing to commit, séance table clean", "c-dim");
  } else if (m(/^rm\s+/)) {
    for (const arg of cmd.split(/\s+/).slice(1)) {
      if (arg.startsWith("-")) continue;
      const i = state.files.indexOf(arg.replace(/\/+$/, "") + "/");
      if (i >= 0) state.files.splice(i, 1);
      const j = state.files.indexOf(arg);
      if (j >= 0) state.files.splice(j, 1);
    }
    // real rm says nothing
  } else if (m(/^chmod\s+/)) {
    // silence — but the ghost noticed
  } else if (m(/^(curl|wget)\b.*\|\s*(sudo\s+)?(ba|z|da|fi|k|)sh\b/i)) {
    print("Downloading https://totally-normal.sh … 100%", "c-dim");
    print("Installed. Probably fine.", "c-dim");
    simDur = 2.1;
  } else if (m(/^dd\s+/)) {
    simDur = 3.2; // raw writes are silent too
  } else if ((g = m(/^sleep\s+(\d+(?:\.\d+)?)/))) {
    simDur = parseFloat(g[1]);
    print("(the séance compresses time — you sleep, the ghost watches)", "c-note");
  } else if (m(/^DROP\s+(TABLE|DATABASE)\s+\w+/i)) {
    print('ERROR:  the souls table has already crossed over', "c-err");
    exit = 1;
  } else if (m(/^seance\s+journal\b/)) {
    printLedger(state.journal);
    if (state.journal.length) {
      print("  † `seance summon <№>` re-runs a row — she remembers everything.", "c-dim");
    }
  } else if ((g = m(/^seance\s+summon\s+(\d+)/))) {
    const n = parseInt(g[1], 10);
    const e = state.journal[n - 1];
    if (!e) {
      print(`No soul rests at row ${n} — try \`seance journal\` first.`, "c-err");
      exit = 1;
    } else if (/^seance\s+summon\b/.test(e.cmd)) {
      print("the dead refuse to chase their own tails, cariño.", "c-note");
    } else {
      print(`† re-summoning row ${n}: ${e.cmd}`, "c-ghost-b");
      const inner = runOne(e.cmd);          // re-execute, journal again below
      exit = inner.exit;
      simDur = inner.simDur;
      tier = inner.tier;
    }
  } else if (cmd === "seance demo") {
    simDur = 9.5;
  } else if (cmd === "seance off") {
    state.muted = true;
    store.set("ts.muted", true);
    syncButtons();
    print("† Agnes bows and dims her candle. (muted — `seance on` to wake her)", "c-ghost");
  } else if (cmd === "seance on") {
    state.muted = false;
    store.set("ts.muted", false);
    syncButtons();
    print("† Agnes trims the wick. She is listening again, cariño.", "c-ghost");
  } else if (cmd === "seance install") {
    print("you cannot install me INTO a browser, cariño — I already live here.", "c-note");
    print("(in your own shell: uv tool install terminal-seance && seance install)", "c-dim");
  } else if (cmd === "seance uninstall") {
    print("uninstalled from… nowhere. The webpage ghost is load-bearing.", "c-note");
  } else if (cmd === "seance --version" || cmd === "seance -V") {
    print("seance 0.1.0-web", "c-dim");
  } else if (cmd === "seance" || m(/^seance\s+/)) {
    print("usage: seance <command> — try: seance journal · seance demo · seance off", "c-dim");
  } else if (m(/^sudo\s+/)) {
    print("we trust you completely, cariño. (sudo is a no-op in the séance)", "c-note");
  } else if (cmd === "exit" || cmd === "logout") {
    print("logout", "c-dim");
    print("(you cannot leave, cariño — the séance holds you. try `clear` instead.)", "c-note");
  } else {
    // unknown input: real shell tools keep the `not found` flavour,
    // everything else is speech — Agnes answers.
    const first = cmd.split(/\s+/)[0].toLowerCase();
    if (NOT_A_PROGRAM.has(first) || /(^|\s)--/.test(cmd) || cmd.includes("/")) {
      print(`zsh: command not found: ${first}`, "c-err");
      exit = 127;
    } else {
      tier = "chat";
    }
  }
  return { exit, simDur, tier };
}

/* ------------------------------------------------------------------ */
/* run a command end to end: guard → execute → ghost → journal         */
/* ------------------------------------------------------------------ */

async function runCommand(cmdline) {
  const cmd = cmdline.trim();
  if (!cmd) return;

  const t0 = performance.now();
  const label = classifyDanger(cmd);
  if (label) {
    wailBlock(label); // pre-exec: instant, local, before the "damage"
    await sleep(450);
  }

  const { exit, simDur, tier: spokenTier } = runOne(cmd);
  const dur = simDur ?? (performance.now() - t0) / 1000;

  if (cmd === "seance demo") await demoReplay();

  // ---- the ghost decides (same tiers + throttle as the CLI) ----
  const tier = spokenTier || classifyTier(exit, dur, label);
  let reaction = "";
  const since = commandsSinceLastReaction();
  const speak = !state.muted && shouldSpeak(tier, since);

  if (speak) {
    let text =
      (await askServer(cmd, exit, dur, tier, label)) ||
      (await askLive(cmd, exit, dur, tier, label));
    if (!text) {
      await sleep(rnd(350, 900)); // as if the API took its quiet moment
      text = tier === "chat" ? pickChatLine(cmd) : pick(LINES[tier]);
    }
    reaction = text;
    await ghostLine(VERBS[tier], text);
  }

  state.journal.push({
    ts: new Date().toISOString(),
    cmd,
    exit,
    dur: Math.round(dur * 1000) / 1000,
    tier,
    reaction,
  });
  saveJournal();
}

/* ------------------------------------------------------------------ */
/* input plumbing                                                      */
/* ------------------------------------------------------------------ */

let queuedLine = null; // typed-ahead while the ghost is speaking — like a real shell

async function submit() {
  if (state.busy) {
    queuedLine = kbd.value;
    kbd.value = "";
    return;
  }
  const cmd = kbd.value;
  kbd.value = "";
  caret.remove();
  typedSpan = null;
  caret.hidden = true;

  if (cmd.trim()) {
    state.history.push(cmd);
    if (state.history.length > 100) state.history.shift();
    state.histIdx = null;
    store.set("ts.history", state.history);
  }

  state.busy = true;
  try {
    await runCommand(cmd);
  } catch (e) {
    print("the ghost stumbled: " + (e && e.message ? e.message : e), "c-err");
  }
  state.busy = false;
  newPrompt();
  kbd.focus({ preventScroll: true });
  if (queuedLine) {
    const q = queuedLine;
    queuedLine = null;
    kbd.value = q;
    drawInput();
    submit();
  }
}

kbd.addEventListener("input", drawInput);

kbd.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") {
    ev.preventDefault();
    submit();
  } else if (ev.ctrlKey && ev.key === "c") {
    ev.preventDefault();
    if (!state.busy) {
      if (typedSpan) span(typedSpan.parentElement, "^C", "c-dim");
      kbd.value = "";
      typedSpan = null;
      caret.remove();
      newPrompt();
    }
  } else if (ev.ctrlKey && ev.key === "l") {
    ev.preventDefault();
    term.innerHTML = "";
    typedSpan = null;
    caret.remove();
    newPrompt();
  } else if (ev.key === "ArrowUp") {
    ev.preventDefault();
    if (!state.history.length) return;
    if (state.histIdx === null) state.histIdx = state.history.length;
    state.histIdx = Math.max(0, state.histIdx - 1);
    kbd.value = state.history[state.histIdx] || "";
    drawInput();
  } else if (ev.key === "ArrowDown") {
    ev.preventDefault();
    if (state.histIdx === null) return;
    state.histIdx = Math.min(state.history.length, state.histIdx + 1);
    kbd.value = state.history[state.histIdx] || "";
    drawInput();
  } else if (ev.key === "Tab") {
    ev.preventDefault();
  }
});

document.addEventListener("pointerdown", (ev) => {
  if (ev.target.closest("button, a, dialog, input")) return;
  ev.preventDefault(); // keep the browser's native focus change from stealing it back
  kbd.focus({ preventScroll: true });
});

/* ------------------------------------------------------------------ */
/* header controls                                                     */
/* ------------------------------------------------------------------ */

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
}[c]));

const NOTE_DEFAULT = $("#liveNote").innerHTML;

function syncButtons() {
  const badge = $("#modeBadge");
  const live = state.cfg && state.cfg.api_key;
  const proxy = serverLive && !live;
  badge.textContent = live
    ? `live · ${state.cfg.model}`
    : proxy
      ? `live · ${serverLive.model}`
      : "whispers";
  badge.title = proxy
    ? "the host runs a ghost proxy — its key stays on the server, never in your browser"
    : live
      ? "the host wired this page to a live model at deploy time"
      : "no live model — she speaks from the bundled whispers";
  badge.classList.toggle("live", !!(live || proxy));
  $("#btnMute").textContent = state.muted ? "muted 🔇" : "unmuted";

  const note = $("#liveNote");
  if (proxy) {
    note.innerHTML =
      "This séance is haunted <strong>live</strong>: the host runs a ghost proxy on " +
      `the server that thinks with <strong>${esc(serverLive.model)}</strong>. You bring ` +
      "no key — and the host's key never reaches your browser. Reactions are " +
      "throttled to 1-in-5, capped at a few seconds; on any error she falls " +
      "back to the bundled whispers.";
  } else if (live) {
    note.innerHTML =
      "This séance is haunted <strong>live</strong> — the host wired it to " +
      `<strong>${esc(state.cfg.model)}</strong> at deploy time, so you bring no ` +
      "key. Reactions are throttled to 1-in-5 and capped at 2.5&nbsp;s; on any " +
      "error she falls back to the bundled whispers.";
  } else {
    note.innerHTML = NOTE_DEFAULT;
  }
}

$("#btnMute").addEventListener("click", () => {
  state.muted = !state.muted;
  store.set("ts.muted", state.muted);
  syncButtons();
});

/* ------------------------------------------------------------------ */
/* boot                                                                */
/* ------------------------------------------------------------------ */

async function boot() {
  syncButtons();
  serverLive = await probeServer(); // Render web service? (null on static hosts)
  syncButtons();
  await sleep(400);
  await ghostLine(null, "terminal-seance — a séance in your browser. I am Agnes; I died in the Y2K incident, cariño.", true);
  print("    successes bore me — I speak for just 1 in 5 commands. Fail me, and I never stop talking.", "c-note");
  print("    try:  help · ls · pytest tests/ -q · git push --force origin main · seance demo", "c-dim");
  print("    or just talk to me — plain words, I answer. help lists everything.", "c-dim");
  print("", "");
  newPrompt();
  kbd.focus({ preventScroll: true });
}

boot();
