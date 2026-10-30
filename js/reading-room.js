/* The Learn room: short guides to read at home or in the truck.
 *
 * The map answers "where and when". Some answers need a paragraph of why —
 * how the Bite score is built, why a shallow lake dies under ice, how to tell
 * a brook trout from a tiger. None of that changes from day to day, so it
 * lives in plain HTML fragments under learn/ and this file only shows them.
 *
 *   ReadingRoom.open()                the index of guides and species
 *   ReadingRoom.open("barometer")     one guide, learn/barometer.html
 *   ReadingRoom.open("species:RNTR")  one species, learn/species-RNTR.html
 *   ReadingRoom.close()
 *
 * The room builds its own overlay
 * -------------------------------
 * Nothing in index.html has to exist first. The overlay, its dialog and one
 * <style> block are made the first time the room opens, so a page that never
 * opens it pays nothing beyond this file.
 *
 * It behaves as a modal dialog: focus moves into it on open and back to the
 * button that opened it on close; Tab stays inside; Esc closes. The close
 * button is 44 px square, the smallest target a thumb hits reliably.
 *
 * Offline
 * -------
 * The fragments and species photos are small and meant to be precached by the
 * service worker. If one is not saved yet and there is no connection, the
 * room says so in a plain sentence instead of showing an empty card.
 *
 * Links inside a fragment
 * -----------------------
 * A link with data-topic="species:BKTR" (or any topic id) opens that page in
 * the room instead of leaving the app. Every other link opens in a new tab,
 * so the map underneath keeps its place. Fragments put their links in a
 * <ul class="links">, where each one is styled as a full 44 px row; a link
 * buried in a sentence is too small to hit with a cold thumb.
 */
(function () {
  "use strict";

  const ROOM_ID = "reading-room";
  const STYLE_ID = "reading-room-style";
  const OFFLINE = "This guide is not saved on this device yet. It opens when you are back online.";

  const GUIDES = [
    { id: "scores", title: "How the Bite and Day out scores work",
      blurb: "What goes into each score, and what the bands mean." },
    { id: "barometer", title: "Reading the barometer",
      blurb: "Why the direction of change matters more than the number." },
    { id: "winterkill", title: "Winterkill and aeration",
      blurb: "Why shallow lakes lose oxygen under ice, and what aerators do." },
    { id: "ice-safety", title: "Ice safety",
      blurb: "Legal is not safe. Ice thickness is never forecast." },
    { id: "stocked-sizes", title: "What stocked sizes mean",
      blurb: "Alberta publishes the length at stocking, not the size you catch." },
    { id: "trout-id", title: "Telling the trout apart",
      blurb: "Key marks for the trout stocked in Alberta." },
  ];

  const SPECIES = [
    { code: "RNTR", name: "Rainbow Trout" },
    { code: "BKTR", name: "Brook Trout" },
    { code: "BNTR", name: "Brown Trout" },
    { code: "TGTR", name: "Tiger Trout" },
    { code: "CTTR", name: "Cutthroat Trout" },
    { code: "WSCT", name: "Westslope Cutthroat" },
    { code: "WALL", name: "Walleye" },
    { code: "NRPK", name: "Northern Pike" },
    { code: "ARGR", name: "Arctic Grayling" },
  ];

  // Fragments already fetched this session. A guide read twice is fetched once.
  const cache = {};
  // Where focus was before the room opened, so closing can put it back.
  let returnFocus = null;
  // Bumped on every navigation, so a slow fetch cannot overwrite a newer page.
  let seq = 0;

  const CSS = `
#reading-room { position: fixed; inset: 0; z-index: 5000; display: flex;
  justify-content: center; align-items: flex-start; background: rgba(0,0,0,0.6);
  overflow: hidden; }
#reading-room[hidden] { display: none; }
#reading-room .rr-card { box-sizing: border-box; width: 100%; max-width: 720px;
  height: 100%; display: flex; flex-direction: column; background: var(--panel);
  color: var(--ink); border: 2px solid var(--panel-edge); }
@media (min-width: 760px) {
  #reading-room { align-items: center; padding: 24px; box-sizing: border-box; }
  #reading-room .rr-card { height: auto; max-height: 100%; border-radius: 6px; }
}
#reading-room .rr-head { display: flex; align-items: center; gap: 8px;
  padding: 6px 6px 6px 14px; background: var(--panel-2);
  border-bottom: 2px solid var(--panel-edge); flex-shrink: 0; }
#reading-room .rr-title { flex: 1; min-width: 0; margin: 0; font-size: 17px;
  line-height: 1.3; overflow-wrap: anywhere; }
#reading-room .rr-btn { min-width: 44px; min-height: 44px; box-sizing: border-box;
  background: none; border: 1px solid transparent; border-radius: 4px;
  color: var(--accent); font: inherit; font-size: 14px; cursor: pointer;
  padding: 0 10px; }
#reading-room .rr-btn:hover { color: var(--ink); border-color: var(--panel-edge); }
#reading-room .rr-close { width: 44px; height: 44px; padding: 0; font-size: 24px;
  line-height: 1; color: var(--ink); }
#reading-room .rr-body { flex: 1; overflow-y: auto; overflow-x: hidden;
  padding: 14px 16px 28px; font-size: 15px; line-height: 1.55;
  overflow-wrap: break-word; -webkit-overflow-scrolling: touch; }
#reading-room .rr-body h3 { font-size: 15px; color: var(--accent); margin: 18px 0 6px; }
#reading-room .rr-body p, #reading-room .rr-body ul { margin: 0 0 10px; }
#reading-room .rr-body ul { padding-left: 20px; }
#reading-room .rr-body li { margin-bottom: 4px; }
#reading-room .rr-body a { color: var(--accent); }
#reading-room .rr-body a:hover { color: var(--ink); }
#reading-room .rr-body img { display: block; max-width: 100%; height: auto;
  border-radius: 4px; background: var(--bg); }
#reading-room .rr-body figure { margin: 0 0 14px; }
#reading-room .rr-body figcaption, #reading-room .rr-note { font-size: 12px;
  color: var(--ink-dim); margin-top: 4px; }
#reading-room .rr-warn { padding: 8px 10px; margin: 0 0 12px;
  border-left: 3px solid var(--accent); background: rgba(201,138,62,0.08); }
#reading-room ul.rr-list { list-style: none; padding: 0; margin: 0 0 16px; }
#reading-room .rr-list li { margin: 0 0 6px; }
#reading-room .rr-item { display: block; width: 100%; min-height: 44px;
  box-sizing: border-box; text-align: left; padding: 8px 12px;
  background: var(--panel-2); color: var(--ink); font: inherit;
  border: 1px solid var(--panel-edge); border-radius: 4px; cursor: pointer; }
#reading-room .rr-item:hover { border-color: var(--accent); }
#reading-room .rr-item span { display: block; font-size: 12px; color: var(--ink-dim); }
#reading-room .rr-grid { display: grid; gap: 6px;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
#reading-room .rr-grid li { margin: 0; }
#reading-room .rr-body ul.links { list-style: none; padding: 0; }
#reading-room .rr-body ul.links li { margin: 0; }
#reading-room .rr-body ul.links a { display: block; min-height: 44px;
  box-sizing: border-box; padding: 11px 0; line-height: 1.4; }
#reading-room .rr-body figcaption a { display: inline-flex; align-items: center;
  min-height: 44px; min-width: 44px; justify-content: center; }
`;

  function escapeHtml(text) {
    return String(text == null ? "" : text).replace(/[&<>"']/g,
      c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = CSS;
    document.head.appendChild(style);
  }

  /* The overlay, made once and kept. The heading id is fixed so the dialog's
   * aria-labelledby always names whatever page is showing. */
  function room() {
    let el = document.getElementById(ROOM_ID);
    if (el) return el;
    injectStyle();
    el = document.createElement("div");
    el.id = ROOM_ID;
    el.hidden = true;
    el.innerHTML = `<div class="rr-card" role="dialog" aria-modal="true"
        aria-labelledby="rr-title">
        <div class="rr-head">
          <button class="rr-btn rr-back" type="button" hidden>‹ All guides</button>
          <h2 class="rr-title" id="rr-title" tabindex="-1">Learn</h2>
          <button class="rr-btn rr-close" type="button" aria-label="Close">×</button>
        </div>
        <div class="rr-body"></div>
      </div>`;
    document.body.appendChild(el);

    el.querySelector(".rr-close").addEventListener("click", close);
    el.querySelector(".rr-back").addEventListener("click", () => show(""));
    // A tap on the dimmed backdrop, outside the card, closes like Esc does.
    el.addEventListener("click", e => { if (e.target === el) close(); });
    el.addEventListener("keydown", onKey);
    el.querySelector(".rr-body").addEventListener("click", onBodyClick);
    return el;
  }

  function onKey(e) {
    if (e.key === "Escape") { e.preventDefault(); close(); return; }
    if (e.key !== "Tab") return;
    // Keep Tab inside the dialog: wrap from the last control to the first.
    const el = document.getElementById(ROOM_ID);
    const focusable = Array.prototype.filter.call(
      el.querySelectorAll("button, a[href], [tabindex]:not([tabindex='-1'])"),
      n => !n.hidden && n.offsetParent !== null);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && (document.activeElement === first || !el.contains(document.activeElement))) {
      e.preventDefault(); last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault(); first.focus();
    }
  }

  /* In-room links carry data-topic; the rest leave in a new tab. */
  function onBodyClick(e) {
    const link = e.target.closest("[data-topic]");
    if (link) { e.preventDefault(); show(link.getAttribute("data-topic")); return; }
    const a = e.target.closest("a[href]");
    if (a && !a.target) { a.target = "_blank"; a.rel = "noopener noreferrer"; }
  }

  function guideFor(topic) {
    return GUIDES.find(g => g.id === topic) || null;
  }

  function speciesFor(topic) {
    const m = /^species:([A-Z]{4})$/.exec(String(topic || ""));
    return m ? SPECIES.find(s => s.code === m[1]) || null : null;
  }

  function indexHtml() {
    const guides = GUIDES.map(g => `<li><button class="rr-item" type="button"
        data-topic="${g.id}">${escapeHtml(g.title)}<span>${escapeHtml(g.blurb)}</span></button></li>`).join("");
    const fish = SPECIES.map(s => `<li><button class="rr-item" type="button"
        data-topic="species:${s.code}">${escapeHtml(s.name)}</button></li>`).join("");
    return `<p class="rr-note">Short guides. They work offline once this device has saved them.</p>
      <h3>Guides</h3><ul class="rr-list">${guides}</ul>
      <h3>Fish</h3><ul class="rr-list rr-grid">${fish}</ul>`;
  }

  /* One fragment, from memory if we have it. Resolves to HTML or null. */
  function load(file) {
    if (cache[file]) return Promise.resolve(cache[file]);
    return fetch(file)
      .then(res => (res.ok ? res.text() : null))
      .then(text => { if (text) cache[file] = text; return text; })
      .catch(() => null);
  }

  /* Render one page into the open room. "" or an unknown topic is the index. */
  function show(topic) {
    const el = room();
    const guide = guideFor(topic);
    const fish = speciesFor(topic);
    const title = guide ? guide.title : fish ? fish.name : "Learn";
    const file = guide ? `learn/${guide.id}.html`
      : fish ? `learn/species-${fish.code}.html` : "";
    const head = el.querySelector(".rr-title");
    const body = el.querySelector(".rr-body");
    const back = el.querySelector(".rr-back");
    const mine = ++seq;

    head.textContent = title;
    back.hidden = !file;
    body.scrollTop = 0;
    if (!file) {
      body.innerHTML = indexHtml();
      head.focus();
      return Promise.resolve();
    }
    body.innerHTML = `<p class="rr-note">Loading…</p>`;
    head.focus();
    return load(file).then(html => {
      if (mine !== seq) return;
      // The fragments are this app's own files, served from its own origin.
      body.innerHTML = html || `<p class="rr-warn">${OFFLINE}</p>`;
    });
  }

  function open(topic) {
    const el = room();
    if (el.hidden) {
      returnFocus = document.activeElement;
      el.hidden = false;
    }
    return show(topic || "");
  }

  function close() {
    const el = document.getElementById(ROOM_ID);
    if (!el || el.hidden) return;
    el.hidden = true;
    seq++;
    const back = returnFocus;
    returnFocus = null;
    if (back && typeof back.focus === "function" && document.contains(back)) back.focus();
  }

  window.ReadingRoom = {
    open: open,
    close: close,
    topics: GUIDES.map(g => g.id).concat(SPECIES.map(s => "species:" + s.code)),
  };
})();
