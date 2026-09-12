/* A month at a time, for the lake you are thinking about.
 *
 * The conditions panel answers "should I go now, or this week". This answers
 * "which day in June", which is a different question and the one you ask when
 * you are booking time off rather than loading the truck.
 *
 * What it is NOT
 * --------------
 * It is not a solunar calendar, though it shows the solunar periods. A solunar
 * app ranks days by the moon and would tell you to fish at two in the afternoon
 * in July. This repo's whole argument about the moon is in conditions.js: it is
 * real, it is measured, and it is worth about five per cent — so it is applied
 * once, at the end, clamped to [0.95, 1.05], and it can never reorder a dusk
 * slot below a midday one. evidence.html?selfcheck=1 asserts exactly that.
 *
 * The major and minor periods are here because you asked for them and because
 * they are honest geometry: the moon really is overhead at that time. They are
 * shown as reference, beside the score, never as the score.
 *
 * Where the numbers come from
 * ---------------------------
 * Every cell is the best half-hour of that day, scored by the same
 * Conditions.scoreSlot the panel uses, through the same ConditionsUI internals.
 * Two views of one engine; nothing here re-implements the scoring.
 *
 * Weather reaches seven days out. Past that the cell is astronomy alone — the
 * sun, and the moon's five per cent — and it says so rather than looking as
 * confident as tomorrow. That is not a degraded score so much as an honest one:
 * seven days out, "when is dusk" is genuinely most of what anyone knows.
 */
(function () {
  "use strict";

  var SLOT_MS = 30 * 60000;
  var HOST_ID = "calendar-view";

  // How far out the forecast actually reaches. Past this a day is sun and moon.
  var WEATHER_DAYS = 7;

  var MONTHS = ["January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"];
  var DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  // The month on screen, and the day whose detail is open. Not in `state`:
  // neither belongs in a shareable link, and neither survives a reload usefully.
  var cursor = null;
  var selected = null;

  function host() { return document.getElementById(HOST_ID); }
  function esc(t) {
    return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function startOfMonth(d) { return new Date(d.getFullYear(), d.getMonth(), 1); }
  function sameDay(a, b) {
    return a && b && a.getFullYear() === b.getFullYear()
      && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  /* Monday-first, because a fishing weekend is Saturday and Sunday together and
   * a Sunday-first grid splits it across two rows. */
  function leadingBlanks(first) { return (first.getDay() + 6) % 7; }

  /** Eight glyphs is as much as the phase deserves; the illumination carries
   *  the detail for anyone who wants it. */
  function moonGlyph(phase) {
    var glyphs = ["●", "◒", "◑", "◑", "○", "◐", "◐", "◓"];
    return glyphs[Math.round(phase * 8) % 8];
  }

  /** The best half-hour of a day, and how much of it rests on weather. */
  function scoreDay(place, day, wx, water, leadDays) {
    var ui = ConditionsUI._internal;
    var end = new Date(day.getTime() + 86400000);
    var best = null;
    for (var t = day.getTime(); t < end.getTime(); t += SLOT_MS) {
      var r = ui.scoreAt(place, new Date(t), wx, water);
      if (!best || (r.scoreRaw || r.score) > (best.scoreRaw || best.score)) {
        best = r;
        best.when = new Date(t);
      }
    }
    if (best) best.leadDays = leadDays;
    return best;
  }

  function dayCell(place, day, wx, water, today) {
    var ui = ConditionsUI._internal;
    var leadDays = Math.round((day.getTime() - today.getTime()) / 86400000);
    var astro = ui.astroFor(place, day);
    var past = leadDays < 0;
    // A day already gone is drawn but never scored: the weather it would be
    // scored against is the forecast for a week from now, not what happened.
    var best = past ? null : scoreDay(place, day, wx, water, leadDays);
    var far = leadDays >= WEATHER_DAYS;

    var phase = astro.moon ? astro.moon.phase : 0;
    var sun = astro.sun || {};
    var rise = sun.sunrise ? ui.hhmm(sun.sunrise) : "—";
    var set = sun.sunset ? ui.hhmm(sun.sunset) : "—";

    var pct = best ? Math.round(best.score * 100) : null;
    var title = day.toDateString()
      + (best ? " — " + best.band + " " + pct + ", best at " + ui.hhmm(best.when) : "")
      + (past ? " — in the past" : far ? " — beyond the forecast: sun and moon only" : "")
      + "\nSunrise " + rise + ", sunset " + set
      + "\n" + (astro.moon ? astro.moon.name : "");

    var cls = "cal-day";
    if (past) cls += " past";
    if (far) cls += " far";
    if (sameDay(day, today)) cls += " today";
    if (selected && sameDay(day, selected)) cls += " picked";

    return '<button type="button" class="' + cls + '" data-day="' + day.getTime()
      + '" title="' + esc(title) + '"'
      + (best ? ' style="--cal-tint:' + ui.colourFor(best.score) + '"' : "")
      + '><span class="cal-n">' + day.getDate() + '</span>'
      + '<span class="cal-moon">' + moonGlyph(phase) + '</span>'
      + (pct === null ? '<span class="cal-score cal-none">·</span>'
                      : '<span class="cal-score">' + pct + '</span>')
      + '<span class="cal-sun">' + esc(rise) + "–" + esc(set) + '</span>'
      + '</button>';
  }

  /** Majors, minors, twilight and the moon, for the day you clicked. */
  function detailHtml(place, day, wx, water) {
    var ui = ConditionsUI._internal;
    var astro = ui.astroFor(place, day);
    var sun = astro.sun || {};
    var periods = astro.periods || [];
    var time = function (t) { return t ? ui.hhmm(t) : "—"; };

    var rows = periods.map(function (p) {
      return '<span class="cal-period ' + esc(p.kind) + '">'
        + '<b>' + (p.kind === "major" ? "Major" : "Minor") + '</b> '
        + esc(time(p.start)) + "–" + esc(time(p.end))
        + '<i>' + esc(p.label) + '</i></span>';
    }).join("");

    var moonTimes = astro.moonTimes || {};
    var firstOf = function (list) { return (list && list.length) ? time(list[0]) : "—"; };

    var best = scoreDay(place, day, wx, water,
                        Math.round((day.getTime() - ui.startOfDay(new Date()).getTime()) / 86400000));

    return '<div class="cal-detail">'
      + '<div class="cal-dhead">' + esc(DOW[(day.getDay() + 6) % 7]) + " "
      + esc(MONTHS[day.getMonth()]) + " " + day.getDate()
      + (best ? '<span class="cal-dbest">best around ' + esc(ui.hhmm(best.when))
                + " · " + esc(best.band) + '</span>' : "")
      + '</div>'
      + '<div class="cal-drow"><span class="cal-dk">Light</span>'
      + '<span>first light ' + esc(time(sun.civilDawn)) + " · sunrise "
      + esc(time(sun.sunrise)) + " · sunset " + esc(time(sun.sunset))
      + " · last light " + esc(time(sun.civilDusk)) + '</span></div>'
      + '<div class="cal-drow"><span class="cal-dk">Moon</span>'
      + '<span>' + esc(astro.moon ? astro.moon.name : "—")
      + ", " + Math.round((astro.moon ? astro.moon.illumination : 0) * 100) + "% lit"
      + " · rise " + esc(firstOf(moonTimes.rises))
      + " · set " + esc(firstOf(moonTimes.sets)) + '</span></div>'
      + '<div class="cal-drow"><span class="cal-dk" title="Solunar periods: the '
      + 'moon overhead or underfoot (major, two hours) and rising or setting '
      + '(minor, one hour). Shown because you asked where they fall — not '
      + 'because they drive the score. The moon is worth five per cent here, '
      + 'and cannot move a midday slot above a dusk one.">Periods</span>'
      + '<span class="cal-periods">' + (rows || "none today") + '</span></div>'
      + '</div>';
  }

  function render() {
    var el = host();
    if (!el || typeof ConditionsUI === "undefined") return;

    var ui = ConditionsUI._internal;
    var place = ui.anchor();
    var wx = Weather.peek(place.lat, place.lon);
    ui.setTz(wx);
    var water = ui.waterFor(place, wx);
    var today = ui.startOfDay(new Date());
    if (!cursor) cursor = startOfMonth(today);

    var first = startOfMonth(cursor);
    var days = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
    var cells = [];
    var blanks = leadingBlanks(first);
    for (var b = 0; b < blanks; b++) cells.push('<span class="cal-blank"></span>');
    for (var d = 1; d <= days; d++) {
      cells.push(dayCell(place, new Date(first.getFullYear(), first.getMonth(), d),
                         wx, water, today));
    }

    var stale = !wx.data
      ? "No forecast yet — every day here is sun and moon only."
      : "Weather reaches " + WEATHER_DAYS + " days out. Beyond that a day is scored "
        + "on sun and moon alone, and is drawn faded to say so.";

    el.innerHTML =
      '<div class="cal-bar">'
      + '<button type="button" class="btn" data-cal="prev" aria-label="Previous month">‹</button>'
      + '<span class="cal-title">' + esc(MONTHS[first.getMonth()]) + " " + first.getFullYear()
      + '<span class="cal-place">' + esc(place.name) + '</span></span>'
      + '<button type="button" class="btn" data-cal="next" aria-label="Next month">›</button>'
      + '<button type="button" class="btn" data-cal="today">Today</button>'
      + '</div>'
      + '<div class="cal-dow">' + DOW.map(function (n) {
          return '<span>' + n + '</span>'; }).join("") + '</div>'
      + '<div class="cal-grid">' + cells.join("") + '</div>'
      + (selected ? detailHtml(place, selected, wx, water) : "")
      + '<div class="cal-foot">' + esc(stale) + " The number is the best half-hour "
      + "of that day, out of 100, by the same measure the conditions panel uses.</div>";

    el.querySelectorAll("[data-cal]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var which = btn.dataset.cal;
        if (which === "prev") cursor = new Date(first.getFullYear(), first.getMonth() - 1, 1);
        else if (which === "next") cursor = new Date(first.getFullYear(), first.getMonth() + 1, 1);
        else { cursor = startOfMonth(today); selected = today; }
        render();
      });
    });
    el.querySelectorAll("[data-day]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var day = new Date(Number(btn.dataset.day));
        selected = (selected && sameDay(selected, day)) ? null : day;
        render();
      });
    });
  }

  /** Opened from the view switcher. Fetches the forecast if it is not already
   *  in hand, exactly as the conditions panel does. */
  function open() {
    var place = ConditionsUI._internal.anchor();
    render();
    Weather.load(place.lat, place.lon).then(render);
  }

  window.FishingCalendar = { open: open, render: render };
})();
