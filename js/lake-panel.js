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
 *   to load keeps its frame and says it failed.
 *
 * The address is Alberta's, unaltered
 * ------------------------------------
 * Alberta publishes these URLs already percent-encoded. This file used to run
 * encodeURI over them on the way out, which escaped the percent signs a second
 * time and turned every %20 into %2520 — so every photograph 404'd, silently,
 * for as long as the panel has existed. See photoUrl().
 */
(function () {
  "use strict";

  const HOST_ID = "lake-panel";

  function host() { return document.getElementById(HOST_ID); }

  function close() {
    const el = host();
    if (el) { el.hidden = true; el.innerHTML = ""; }
  }

  /* Alberta publishes these URLs already percent-encoded, so the folder
   * "Pine Coulee Reservoir" arrives as "Pine%20Coulee%20Reservoir". Running
   * encodeURI over that escaped the percent itself — %20 became %2520 — and
   * every one of the 662 photographs 404'd. Encode only what is not encoded.
   */
  function photoUrl(raw) {
    const url = String(raw == null ? "" : raw);
    try {
      // decodeURI turns %20 back into a space, so a URL that changes under it
      // was already encoded and must be left exactly as published.
      if (decodeURI(url) !== url) return url;
    } catch (e) {
      // A stray percent that is not an escape sequence. Not ours to repair.
      return url;
    }
    return encodeURI(url);
  }

  /* HEIC is what an iPhone writes and what Alberta uploaded for twenty of
   * these. Only Safari decodes it, so in Chrome or Firefox a correct URL still
   * yields nothing. Those are offered as links instead of dead tiles. */
  function isHeic(url) {
    return /\.heic$/i.test(String(url == null ? "" : url).split("?")[0]);
  }

  function shot(photo) {
    const url = photoUrl(photo.url);
    const caption = photo.caption || "Photograph";
    // A tile that cannot load says so — it used to delete itself, which made a
    // bug look like Alberta quietly moving the pictures.
    return `<a class="lp-shot" href="${url}" target="_blank" rel="noopener noreferrer"
      title="${escapeHtml(caption)}">
      <img src="${url}" alt="${escapeHtml(caption)}" loading="lazy"
           referrerpolicy="no-referrer"
           onerror="this.closest('.lp-shot').classList.add('failed')">
      <span class="lp-cap">${escapeHtml(caption)}</span></a>`;
  }

  /* The ones this browser cannot decode, as a line of links. */
  function heicHtml(shots) {
    if (!shots.length) return "";
    const links = shots.map(p =>
      `<a href="${photoUrl(p.url)}" target="_blank" rel="noopener noreferrer"
        >${escapeHtml(p.caption || "Photograph")}</a>`).join(", ");
    return `<div class="lp-offline">${shots.length} photograph${shots.length === 1 ? " is" : "s are"}
      in a format this browser cannot show. On Alberta's site: ${links}</div>`;
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
      body += `<div class="lp-shots" data-shots>Loading…</div><div data-heic></div>`;
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
      const viewable = shots.filter(p => !isHeic(p.url));
      const unshowable = shots.filter(p => isHeic(p.url));
      // Pine Coulee's only photograph is a HEIC. An empty grid there is not a
      // fetch that failed, and saying so sends someone looking for a fault
      // that is not there — the line below already explains it.
      slot.innerHTML = viewable.length
        ? viewable.map(shot).join("")
        : unshowable.length
          ? ""
          : `<div class="lp-offline">The photographs could not be fetched.</div>`;
      const heic = el.querySelector("[data-heic]");
      if (heic) heic.innerHTML = heicHtml(unshowable);
    }
  }

  window.LakePanel = { open: open, close: close };
})();
