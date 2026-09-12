/* What Alberta says about a lake, once you have decided to go.
 *
 * The popup holds what decides the trip: how recently it was stocked, whether
 * the season is open, how deep it is, what you may keep. This holds what you
 * read afterwards — the province's own description of the place, and its
 * photographs. Both are long, neither changes a decision, and a popup capped
 * at 60vh cannot hold them without pushing the regulations off the bottom.
 *
 * The photographs stay on Alberta's server
 * -----------------------------------------
 * They are linked, never copied. Three consequences, all deliberate:
 *
 *   They load only when someone opens this panel, so simply browsing the map
 *   never tells a government server which lakes you looked at.
 *
 *   Every request carries no referrer, so opening the panel does not announce
 *   where it was opened from.
 *
 *   They cannot work offline. The service worker only handles this app's own
 *   origin, and caching a few hundred photographs would evict the map tiles
 *   that make the app useful at the lake. So the panel says the pictures need
 *   a connection rather than showing broken frames, and a picture that fails
 *   to load is replaced by its caption as a link.
 */
(function () {
  "use strict";

  const HOST_ID = "lake-panel";

  function host() { return document.getElementById(HOST_ID); }

  function close() {
    const el = host();
    if (el) { el.hidden = true; el.innerHTML = ""; }
  }

  function shot(photo) {
    const url = encodeURI(photo.url);
    const caption = photo.caption || "Photograph";
    // If the image cannot load — no signal, or Alberta has moved it — the tile
    // becomes the caption as a link rather than a broken frame.
    return `<a class="lp-shot" href="${url}" target="_blank" rel="noopener noreferrer"
      title="${escapeHtml(caption)}">
      <img src="${url}" alt="${escapeHtml(caption)}" loading="lazy"
           referrerpolicy="no-referrer"
           onerror="this.remove()">
      <span class="lp-cap">${escapeHtml(caption)}</span></a>`;
  }

  function escapeHtml(text) {
    return String(text == null ? "" : text).replace(/[&<>"']/g,
      c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function chrome(title, body) {
    return `<div class="cx-head">
        <span class="cx-title">About this lake<span class="cx-place">${escapeHtml(title)}</span></span>
        <button class="cx-close" type="button" aria-label="Close">×</button>
      </div>${body}`;
  }

  async function open(key) {
    const el = host();
    if (!el) return;
    // Bare references, like the other modules: LAKES is a top-level `let`, so
    // it never becomes a property of window, and window.LAKES is undefined.
    const lake = (typeof LAKES === "undefined" ? [] : LAKES).find(l => lakeKey(l) === key);
    if (!lake) return;
    const profile = (typeof profileFor === "function" && profileFor(lake)) || {};

    let body = "";
    if (profile.description) {
      body += `<div class="lp-desc">${escapeHtml(profile.description)}</div>`;
    }
    if (profile.photo_count) {
      body += `<div class="cx-title" style="font-size:11px">Photographs</div>`;
      body += `<div class="lp-shots" data-shots>Loading…</div>`;
      if (!navigator.onLine) {
        body += `<div class="lp-offline">These are Alberta's photographs and stay
          on Alberta's server, so they need a connection.</div>`;
      }
    }
    if (!body) body = `<div class="lp-offline">Alberta publishes nothing further
      about this lake.</div>`;

    // Both panels float in the same corner of the map, so only one is up at a
    // time. The conditions panel already expects this of anything that opens.
    if (window.ConditionsUI && state.conditions.open) ConditionsUI.toggle(false);
    el.innerHTML = chrome(lake.name, body);
    el.hidden = false;
    el.querySelector(".cx-close").addEventListener("click", close);

    const slot = el.querySelector("[data-shots]");
    if (slot) {
      const index = await loadPhotos();
      const shots = (index && index.lakes && index.lakes[key]) || [];
      slot.innerHTML = shots.length
        ? shots.map(shot).join("")
        : `<div class="lp-offline">The photographs could not be fetched.</div>`;
    }
  }

  window.LakePanel = { open: open, close: close };
})();
