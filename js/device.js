/* Build 5 Stage 4: keeping the owner's data safe on this device, with no sign-in.
 *
 *   storage   ask the browser to keep this site's data (navigator.storage.persist)
 *             and say in Settings whether it was granted
 *   tip       on iPhone and iPad in Safari (not opened from the Home Screen), a
 *             one-time tip to add the app to the Home Screen: Safari clears site
 *             data after 7 days without use; Home Screen apps are exempt (owner)
 *   backup    one file with the saved lakes and the imported spots, made in this
 *             browser and saved to the device; it is never sent anywhere
 *   restore   read that file back: check it, show what it holds, and replace the
 *             saved lakes and spots after the owner confirms (decision 2 A)
 */
(function () {
  "use strict";

  var TIP_KEY = "troutmap.a2hs";
  var APP = "hz-trout-map", KIND = "backup", VERSION = 1;

  // ============================================================ storage
  function storageState() {
    var s = typeof navigator !== "undefined" ? navigator.storage : null;
    if (!s || typeof s.persisted !== "function") return Promise.resolve("unknown");
    return s.persisted().then(function (kept) {
      if (kept) return "kept";
      if (typeof s.persist !== "function") return "not-kept";
      return s.persist().then(function (granted) { return granted ? "kept" : "not-kept"; });
    }).catch(function () { return "unknown"; });
  }

  var STORAGE_TEXT = {
    kept: "Storage: kept. This browser will not clear your saved lakes and spots on its own.",
    "not-kept": "Storage: not guaranteed. The browser may clear your saved lakes and spots. Use Back up.",
    unknown: "Storage: this browser does not say whether it keeps your data. Use Back up.",
  };

  // ============================================================ the Home Screen tip
  function isAppleTouch(nav) {
    nav = nav || (typeof navigator !== "undefined" ? navigator : {});
    var ua = nav.userAgent || "";
    // iPadOS Safari says "Macintosh"; a touch screen gives it away.
    return /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && (nav.maxTouchPoints || 0) > 1);
  }

  function isHomeScreenApp(nav, win) {
    nav = nav || (typeof navigator !== "undefined" ? navigator : {});
    win = win || (typeof window !== "undefined" ? window : {});
    if (nav.standalone === true) return true;
    try { return !!(win.matchMedia && win.matchMedia("(display-mode: standalone)").matches); } catch (e) { return false; }
  }

  function tipWanted(nav, win, seen) {
    return isAppleTouch(nav) && !isHomeScreenApp(nav, win) && !seen;
  }

  var TIP_TEXT = "Add this app to your Home Screen: tap Share, then Add to Home Screen. "
    + "Safari clears site data after 7 days without use. Home Screen apps are exempt.";

  // ============================================================ backup and restore
  function makeBackup(favourites, spots, now) {
    return {
      app: APP, kind: KIND, version: VERSION, made: (now || new Date()).toISOString(),
      favourites: (favourites || []).slice(), spots: spots || null,
    };
  }

  function backupName(now) {
    return "trout-map-backup-" + (now || new Date()).toISOString().slice(0, 10) + ".json";
  }

  /** The text of a file → {ok, backup, summary} or {ok: false, why}. */
  function readBackup(text) {
    var doc;
    try { doc = JSON.parse(String(text || "")); } catch (e) { return { ok: false, why: "This file is not a Trout Map backup (it cannot be read)." }; }
    if (!doc || doc.app !== APP || doc.kind !== KIND) return { ok: false, why: "This file is not a Trout Map backup." };
    if (doc.version !== VERSION) return { ok: false, why: "This backup is from another version of the app." };
    if (!Array.isArray(doc.favourites) || !doc.favourites.every(function (k) { return typeof k === "string"; }))
      return { ok: false, why: "This backup is damaged (its saved lakes cannot be read)." };
    var sp = doc.spots;
    if (sp !== null && (typeof sp !== "object" || !sp.result || !Array.isArray(sp.result.spots)))
      return { ok: false, why: "This backup is damaged (its spots cannot be read)." };
    var places = sp ? sp.result.total : 0;
    return { ok: true, backup: doc, summary: { lakes: doc.favourites.length, places: places, made: doc.made } };
  }

  function summaryText(s) {
    var day = String(s.made || "").slice(0, 10);
    return "Backup from " + (day || "an unknown day") + ": " + s.lakes + " saved lake" + (s.lakes === 1 ? "" : "s")
      + " and " + s.places + " imported place" + (s.places === 1 ? "" : "s") + ".";
  }

  function download(name, text) {
    var blob = new Blob([text], { type: "application/json" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  }

  window.Device = {
    storageState: storageState, STORAGE_TEXT: STORAGE_TEXT,
    tipWanted: tipWanted, TIP_KEY: TIP_KEY, TIP_TEXT: TIP_TEXT,
    makeBackup: makeBackup, backupName: backupName, readBackup: readBackup, summaryText: summaryText,
    download: download,
    _internal: { isAppleTouch: isAppleTouch, isHomeScreenApp: isHomeScreenApp },
  };
})();
