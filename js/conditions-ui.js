/* The conditions panel: the next six hours, and the next seven days.
 *
 * Two horizons because there are two questions. "Should I go now, and when in
 * the window" is answered by a strip of half-hours. "Saturday or Sunday" is not
 * — six hours cannot see the weekend — so the same single weather call also
 * draws a grid of seven days by five parts of the day.
 *
 * The sun and the moon are drawn as SEPARATE tracks under the strip, and that
 * is the whole argument of this feature made visible. Solunar tables fold them
 * into one ranking, which is how an app ends up telling you to fish at two in
 * the afternoon in July: the moon's major periods are pure geometry, they sweep
 * every hour of the clock over a month, and they are worth about five percent.
 * Drawn apart, you can see that the moon band moved and the dawn band did not.
 *
 * Colour encodes magnitude, so it is one hue with monotone lightness rather
 * than a red-to-green traffic light. The band word and the number are in every
 * cell, so nothing here is carried by colour alone.
 */
(function () {
  "use strict";

  /* Sequential ramp, dark surface, validated against #33362f: monotone
   * lightness, single hue (4 degrees of spread), and the dimmest step still
   * clears 2:1 on the panel so a poor cell is a cell rather than a hole.
   *
   * Not the documented default blue: in this app blue already means Rainbow
   * Trout, and orange, aqua, yellow, violet and red are the other five species.
   * Every categorical slot is spoken for, so the score takes the interface's
   * own ochre and stays out of the species channel entirely. */
  var RAMP = ["#736440", "#957c48", "#b69551", "#d5af60", "#f2d183"];

  var DAY_PARTS = [
    { id: "dawn", label: "Dawn" },
    { id: "morning", label: "Morning" },
    { id: "midday", label: "Midday" },
    { id: "evening", label: "Evening" },
    { id: "night", label: "Night" },
  ];

  var SLOT_MS = 30 * 60000;
  var STRIP_SLOTS = 12;          // six hours

  function colourFor(score) {
    if (score === null || score === undefined || !isFinite(score)) return "#3f4139";
    var i = Math.min(RAMP.length - 1, Math.max(0, Math.floor(score * RAMP.length)));
    return RAMP[i];
  }

  function pad(n) { return (n < 10 ? "0" : "") + n; }

  /* Clock times are shown at the LAKE, not on the reader's device.
   *
   * Using the device clock is wrong for anyone planning a trip from another
   * timezone, and it is not a subtle wrongness: in a UTC browser this panel
   * put the six-hour window at 10:30 to 16:00 Alberta time while labelling it
   * 16:30 to 22:00, so the evening peak sat outside the window and every bar
   * came out the same middling height. It looked like a flat afternoon rather
   * than like a bug.
   *
   * The offset comes from the weather response, which knows the lake's zone and
   * whether daylight saving is in force there. With no weather there is no
   * offset, so the device clock is used and the panel says so. */
  var tzOffsetSec = null;

  function hhmm(d) {
    if (tzOffsetSec === null) return pad(d.getHours()) + ":" + pad(d.getMinutes());
    var shifted = new Date(d.getTime() + tzOffsetSec * 1000);
    return pad(shifted.getUTCHours()) + ":" + pad(shifted.getUTCMinutes());
  }

  /** The calendar day at the lake, for the grid's column headings. */
  function lakeDayName(d, index) {
    if (index === 0) return "Today";
    var shifted = tzOffsetSec === null ? d : new Date(d.getTime() + tzOffsetSec * 1000);
    var names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    return names[tzOffsetSec === null ? shifted.getDay() : shifted.getUTCDay()];
  }

  function lakeDayNumber(d) {
    if (tzOffsetSec === null) return d.getDate();
    return new Date(d.getTime() + tzOffsetSec * 1000).getUTCDate();
  }

  // ============================================================
  // WHAT TO SCORE
  // ============================================================

  function placeFor(lake) {
    return { lat: lake.lat, lon: lake.lon, name: lake.name, lake: lake,
             species: filteredDominantOrder(lake) };
  }

  /** The nearest lake to home, by the distance prepareLakes already measured.
   *  Home itself is a town, and a forecast for a town is the one thing this
   *  panel should never give: the water temperature input only exists for a
   *  lake, the species bands only mean something at a lake, and nobody drives
   *  to a postcode to fish. So when no lake has been chosen, the panel picks
   *  the closest one and says which. */
  function nearestLake() {
    if (typeof LAKES === "undefined") return null;
    var best = null;
    for (var i = 0; i < LAKES.length; i++) {
      var l = LAKES[i];
      if (l.lat == null || l.lon == null || !isFinite(l.distanceKm)) continue;
      if (!best || l.distanceKm < best.distanceKm) best = l;
    }
    return best;
  }

  /** The lake the panel is talking about — the chosen one, or the nearest. */
  function anchor() {
    var key = state.conditions && state.conditions.anchorKey;
    if (key) {
      var lake = LAKES.find(function (l) { return lakeKey(l) === key; });
      if (lake) return placeFor(lake);
    }
    var near = nearestLake();
    if (near) {
      // Remember it, so the water-temperature input — which exists only for a
      // lake — appears, and so a reading typed here is kept against that lake.
      if (state.conditions) {
        state.conditions.anchorKey = lakeKey(near);
        state.conditions.anchorAuto = true;
      }
      return placeFor(near);
    }
    // No lake has a position yet. Home is the last resort, not the default.
    return { lat: state.home.lat, lon: state.home.lon, name: state.home.name,
             lake: null, species: [...state.species] };
  }

  /* One day's astronomy is computed once and handed to every slot in that day.
   * Recomputing the moon per half-hour would be 48 times the work for an answer
   * that does not change. */
  var astroCache = {};
  function astroFor(place, dayStart) {
    var key = place.lat.toFixed(3) + "," + place.lon.toFixed(3) + "," + dayStart.getTime();
    if (!astroCache[key]) astroCache[key] = Astro.dayFor(place.lat, place.lon, dayStart);
    return astroCache[key];
  }

  function startOfDay(d) {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate());
  }

  function scoreAt(place, when, wx, water) {
    return Conditions.scoreSlot({
      when: when, lat: place.lat, lon: place.lon, species: place.species,
      weather: wx.data ? Weather.at(wx.data, when) : null,
      water: water,
      astro: astroFor(place, startOfDay(when)),
      leadDays: Weather.leadDays(when),
      // Known depth turns the thermocline advisory from a guess into a
      // statement; unknown depth keeps it silent, which is the whole point.
      maxDepthM: place.lake && typeof depthFor === "function"
        ? ((depthFor(place.lake) || {}).max_depth_m ?? null) : null,
      areaHa: place.lake ? place.lake.surface_area_ha : null,
    });
  }

  /** The water estimate for a place, modelled from air unless measured. */
  function waterFor(place, wx) {
    var override = place.lake && state.conditions.waterOverrides[lakeKey(place.lake)];
    if (override && isFinite(override.tempC)) {
      return { tempC: override.tempC, source: "measured", sigmaC: 0, at: override.atISO };
    }
    if (!wx.data) return null;
    return Conditions.waterFromAir(
      Weather.dailyMeansUpTo(wx.data, new Date()),
      { areaHa: place.lake ? place.lake.surface_area_ha : null });
  }

  // ============================================================
  // THE NEXT SIX HOURS
  // ============================================================

  function stripHtml(place, wx, water) {
    var now = new Date();
    // Snap to the half hour so the cells line up with the clock.
    var start = new Date(Math.floor(now.getTime() / SLOT_MS) * SLOT_MS);
    var cells = [], best = null, i;
    for (i = 0; i < STRIP_SLOTS; i++) {
      var when = new Date(start.getTime() + i * SLOT_MS);
      var r = scoreAt(place, when, wx, water);
      r.when = when;
      cells.push(r);
      if (!best || (r.scoreRaw || r.score) > (best.scoreRaw || best.score)) best = r;
    }

    var bars = cells.map(function (r) {
      var pct = Math.round(r.score * 100);
      var title = hhmm(r.when) + " — " + r.band + " " + pct
        + (r.moonNote ? " · " + r.moonNote : "");
      return '<div class="cx-slot" title="' + esc(title) + '" tabindex="0" role="img"'
        + ' aria-label="' + esc(title) + '">'
        + '<div class="cx-bar" style="height:' + Math.max(6, pct) + '%;background:'
        + colourFor(r.score) + '"></div>'
        + '<div class="cx-time">' + (r.when.getMinutes() === 0 ? hhmm(r.when) : "") + '</div>'
        + '</div>';
    }).join("");

    // Two tracks, deliberately apart. The sun band is the evidence; the moon
    // band is the five percent.
    var sun = cells.map(function (r) {
      var alt = r.factors.light.value;
      var cls = alt === null ? "" : alt > 6 ? "day" : alt > -6 ? "twilight" : "night";
      return '<div class="cx-tick ' + cls + '" title="' + esc("sun " + (alt === null ? "—" : Math.round(alt) + "°")) + '"></div>';
    }).join("");
    var moon = cells.map(function (r) {
      var kind = !r.moonNote ? "" : /major/.test(r.moonNote) ? "major" : "minor";
      return '<div class="cx-tick ' + kind + '" title="' + esc(r.moonNote || "no lunar period") + '"></div>';
    }).join("");

    return '<div class="cx-strip">' + bars + '</div>'
      + '<div class="cx-track"><span class="cx-track-label">Sun</span><div class="cx-ticks">' + sun + '</div></div>'
      + '<div class="cx-track"><span class="cx-track-label">Moon</span><div class="cx-ticks">' + moon + '</div></div>'
      + '<div class="cx-best">Best in the next six hours: <strong>' + hhmm(best.when)
      + '</strong> · ' + best.band + ' ' + Math.round(best.score * 100) + '</div>';
  }

  // ============================================================
  // THE NEXT SEVEN DAYS
  // ============================================================

  /* Day parts are anchored to the SUN, never to a clock reading.
   *
   * The first version of this used fixed hours — midday as 11:00 to 16:00 —
   * and it was wrong twice over. "11:00" is 11:00 on whatever device is
   * running the page, so planning an Alberta trip from another timezone shifted
   * every box; in a UTC browser the midday cells landed at five in the morning,
   * the windows inverted, and two whole rows of the grid silently rendered
   * empty rather than wrong, which is how it went unnoticed.
   *
   * Solar anchors have no such dependency. They are also the better definition:
   * dawn in June and dawn in December are four hours apart on the clock, and a
   * fixed box would misdescribe both.
   */
  function partWindow(part, dayStart, sun, nextSun) {
    var noon = sun.solarNoon;
    var hoursFromNoon = function (h) { return new Date(noon.getTime() + h * 3600000); };
    var minutes = function (d, m) { return new Date(d.getTime() + m * 60000); };

    // With no sunrise or sunset — far north, midsummer or midwinter — the solar
    // day still has a noon, so everything can hang off that.
    var rise = sun.sunrise || hoursFromNoon(-6);
    var set = sun.sunset || hoursFromNoon(6);
    var dawn = sun.civilDawn || minutes(rise, -35);
    var dusk = sun.civilDusk || minutes(set, 35);
    var nextDawn = (nextSun && (nextSun.civilDawn || nextSun.sunrise))
      || new Date(dawn.getTime() + 86400000);

    switch (part) {
      case "dawn":    return [minutes(dawn, -30), minutes(rise, 90)];
      case "morning": return [minutes(rise, 90), hoursFromNoon(-2)];
      case "midday":  return [hoursFromNoon(-2), hoursFromNoon(3)];
      case "evening": return [hoursFromNoon(3), minutes(set, 30)];
      /* Night begins where the light actually goes, at the end of civil
       * twilight — not at sunset. Starting it half an hour after sunset put the
       * dusk peak inside the night window, and because each cell takes the best
       * moment in its window, Night scored 90 on the strength of a moment that
       * Evening already owns. The row has to mean what its label says. */
      default:        return [minutes(dusk, 30), minutes(nextDawn, -30)];
    }
  }

  function gridHtml(place, wx, water) {
    var today = startOfDay(new Date());
    var days = [], d;
    for (d = 0; d < 7; d++) days.push(new Date(today.getTime() + d * 86400000));

    var head = '<div class="cx-gcell cx-ghead"></div>' + days.map(function (day, i) {
      return '<div class="cx-gcell cx-ghead">' + esc(lakeDayName(day, i))
        + '<span>' + lakeDayNumber(day) + '</span></div>';
    }).join("");

    var rows = DAY_PARTS.map(function (part) {
      var cells = days.map(function (day, dayIndex) {
        var astro = astroFor(place, day);
        var next = astroFor(place, new Date(day.getTime() + 86400000));
        var window = partWindow(part.id, day, astro.sun, next.sun);
        var from = window[0], to = window[1];
        var best = null;
        // A window that comes out backwards means the sun events were not what
        // this part assumed. Render nothing rather than a made-up score, but
        // never silently — the empty cell says so.
        if (from.getTime() > to.getTime()) {
          return '<div class="cx-gcell cx-gempty" title="no window for this part of the day">·</div>';
        }
        for (var t = from.getTime(); t <= to.getTime(); t += SLOT_MS) {
          var r = scoreAt(place, new Date(t), wx, water);
          if (!best || (r.scoreRaw || r.score) > (best.scoreRaw || best.score)) {
            best = r; best.when = new Date(t);
          }
        }
        if (!best) return '<div class="cx-gcell"></div>';
        var pct = Math.round(best.score * 100);
        // Past day three the weather half of this is guesswork, and the cell
        // says so rather than looking as certain as tomorrow.
        var fade = dayIndex <= 2 ? "" : dayIndex <= 4 ? " lead-mid" : " lead-far";
        var title = lakeDayName(day, dayIndex) + " " + lakeDayNumber(day)
          + " " + part.label + " — " + best.band + " " + pct
          + " · best " + hhmm(best.when)
          + (dayIndex > 2 ? " · forecast confidence lower this far out" : "");
        return '<div class="cx-gcell cx-score' + fade + '" style="background:' + colourFor(best.score) + '"'
          + ' title="' + esc(title) + '" tabindex="0" role="img" aria-label="' + esc(title) + '">'
          + '<span class="cx-n">' + pct + '</span></div>';
      }).join("");

      /* The labels say Dawn and Morning and never say when either one is, so
       * the boundary between them — ninety minutes after sunrise, which moves
       * by hours across the year — was invisible. Today's window, in the
       * lake's own clock, printed under the name. */
      var todayAstro = astroFor(place, days[0]);
      var todayNext = astroFor(place, new Date(days[0].getTime() + 86400000));
      var span = partWindow(part.id, days[0], todayAstro.sun, todayNext.sun);
      var spanText = span[0].getTime() <= span[1].getTime()
        ? hhmm(span[0]) + "\u2013" + hhmm(span[1]) : "";
      var labelTitle = part.label + (spanText
        ? " today runs " + spanText + ", anchored to the sun rather than the clock"
        : "");
      return '<div class="cx-gcell cx-glabel" title="' + esc(labelTitle) + '">' + part.label
        + (spanText ? '<span class="cx-gspan">' + esc(spanText) + '</span>' : "")
        + '</div>' + cells;
    }).join("");

    return '<div class="cx-grid">' + head + rows + '</div>'
      + '<div class="cx-legend">'
      + '<span class="cx-key">Poor</span>'
      + RAMP.map(function (c) { return '<i style="background:' + c + '"></i>'; }).join("")
      + '<span class="cx-key">Prime</span>'
      + '<span class="cx-key cx-faded">hatched = forecast further out, trusted less</span>'
      + '</div>';
  }

  // ============================================================
  // WHY
  // ============================================================

  /* A thermometer beats the model outright, and this is the only input on the
   * panel. It matters most exactly where the app is least able to help: with no
   * signal at the lake there is no weather and no modelled water temperature,
   * so the score falls back to sun and moon alone. One reading you took lifts
   * it back to a real estimate. */
  function waterInputHtml(place, water) {
    if (!place.lake) return "";
    var key = lakeKey(place.lake);
    var override = state.conditions.waterOverrides[key];
    var value = override && isFinite(override.tempC) ? override.tempC : "";
    var measured = water && water.source === "measured";
    return '<div class="cx-measure">'
      + '<label for="cx-water">Water you measured</label>'
      + '<input id="cx-water" type="number" inputmode="decimal" step="0.1" min="-2" max="35"'
      + ' value="' + esc(value) + '" placeholder="°C">'
      + (measured ? '<button type="button" class="cx-clear" title="Go back to the estimate">clear</button>'
                  : '<span class="cx-measure-note">beats the estimate</span>')
      + '</div>'
      /* Where to hold the thermometer changes the number more than which
       * thermometer it is — except in summer, when only something on a line
       * reaches the layer the fish are actually in. */
      + '<div class="cx-measure-hint" title="An infrared gun reads the skin of '
      + 'the water and is thrown off by glare and ripple. A thermometer on a '
      + 'marked line, or a sounder with a temperature transducer, is the only '
      + 'kind that reads below the surface — which is exactly what matters once '
      + 'a lake has stratified in July.">'
      + 'Surface reading, taken in shade. A probe on a line beats an infrared gun.'
      + '</div>';
  }

  /* The pills read strong, moderate, weak, and every one of them was read as a
   * description of the conditions. They are not. They say how good the evidence
   * behind that factor is — how much this app is willing to let it move the
   * number — which is why rain and the moon are permanently weak and why water
   * turns strong the moment you type in a thermometer reading. */
  var TIER_WHY = {
    strong: "Strong evidence: this factor is well supported and carries real "
      + "weight in the score.",
    moderate: "Moderate evidence: real, but thinner — it moves the score only "
      + "a little.",
    weak: "Weak evidence: barely moves the score on purpose. The moon is capped "
      + "at five per cent either way.",
    none: "Not available right now, so it is left out and the other factors "
      + "are reweighted.",
  };

  function tierPill(tier) {
    var key = tier || "none";
    return '<span class="cx-tier ' + key + '" title="' + esc(TIER_WHY[key] || "")
      + '">' + (tier || "n/a") + '</span>';
  }

  function factorsHtml(result) {
    var order = ["light", "water", "pressure", "wind", "precip"];
    var names = { light: "Light", water: "Water temp", pressure: "Pressure",
                  wind: "Wind", precip: "Rain" };
    var rows = order.map(function (id) {
      var f = result.factors[id];
      if (!f) return "";
      var absent = f.s === null;
      return '<div class="cx-factor' + (absent ? " absent" : "") + '">'
        + '<span class="cx-fname">' + names[id] + '</span>'
        + tierPill(f.tier)
        + '<span class="cx-fval">' + esc(f.note || "—") + '</span>'
        + '<span class="cx-fbar"><i style="width:' + (absent ? 0 : Math.round(f.s * 100))
        + '%;background:' + colourFor(absent ? null : f.s) + '"></i></span>'
        + '</div>';
    }).join("");
    var moon = '<div class="cx-factor">'
      + '<span class="cx-fname">Moon</span>'
      + tierPill("weak")
      + '<span class="cx-fval">' + esc(result.moonNote || "no lunar period")
      + " · " + (result.moonMult >= 1 ? "+" : "") + Math.round((result.moonMult - 1) * 100) + "%</span>"
      + '<span class="cx-fbar"></span></div>';
    var legend = '<div class="cx-tierkey">strong / moderate / weak is how good the '
      + 'evidence is, not how good the conditions are. '
      + '<a href="evidence.html' + esc(location.search) + '" target="_blank" rel="noopener">'
      + 'What each is worth ↗</a></div>';
    return rows + moon + legend;
  }

  // ============================================================
  // RENDER
  // ============================================================

  function render() {
    var host = document.getElementById("conditions-panel");
    if (!host || !state.conditions.open) return;
    var place = anchor();
    var wx = Weather.peek(place.lat, place.lon);
    tzOffsetSec = wx.data && typeof wx.data.offset === "number" ? wx.data.offset : null;
    var water = waterFor(place, wx);
    var now = scoreAt(place, new Date(), wx, water);

    var closed = place.lake ? lakeOpenNow(place.lake) === false : false;
    var source = wx.source === "none"
      ? '<span class="cx-warn">No weather — sun and moon only</span>'
      : '<span class="cx-src">weather ' + esc(Weather.ageText(wx.fetchedAt))
        + (wx.source === "cache" ? " (cached)" : "") + "</span>";

    var body;
    if (closed) {
      // Ranking a lake that is legally shut is worse than useless.
      var reg = regulationFor(place.lake);
      body = '<div class="cx-closed"><strong>CLOSED today</strong>'
        + '<div>' + esc((reg && reg.season && reg.season.text) || "season not listed")
        + '</div><div class="cx-why">No score is shown for a lake whose season is shut.</div></div>';
    } else {
      body = (state.conditions.horizon === "week"
        ? gridHtml(place, wx, water)
        : stripHtml(place, wx, water))
        + '<div class="cx-factors">' + factorsHtml(now) + '</div>'
        + waterInputHtml(place, water);
    }

    host.innerHTML =
      '<div class="cx-head">'
      + '<div class="cx-title">Conditions<span class="cx-place">' + esc(place.name) + '</span></div>'
      + '<button class="cx-close" type="button" aria-label="Close conditions">×</button>'
      + '</div>'
      + '<div class="cx-row">'
      + '<div class="chips cx-horizon">'
      + '<button class="chip' + (state.conditions.horizon === "now" ? " active" : "") + '" data-horizon="now">Next 6 h</button>'
      + '<button class="chip' + (state.conditions.horizon === "week" ? " active" : "") + '" data-horizon="week">7 days</button>'
      + '</div>'
      + '<span class="cx-conf">' + esc(now.confidence) + '</span>'
      + '</div>'
      + '<div class="cx-src-row">' + source
      + '<span class="cx-tz">' + (tzOffsetSec === null
          ? "times on this device's clock"
          : "times at the lake" + (wx.data.timezone ? " (" + esc(wx.data.timezone) + ")" : ""))
      + '</span></div>'
      + body
      + (now.advisories.length
          ? '<div class="cx-advisory">' + now.advisories.map(esc).join("<br>") + "</div>" : "")
      + '<div class="cx-foot"><a href="evidence.html' + esc(location.search) + '" target="_blank" rel="noopener">'
      + 'What this score is built on ↗</a></div>';

    host.querySelector(".cx-close").addEventListener("click", function () { toggle(false); });

    var input = host.querySelector("#cx-water");
    if (input) {
      var save = function () {
        var key = lakeKey(place.lake);
        var value = parseFloat(input.value);
        if (isFinite(value)) {
          state.conditions.waterOverrides[key] =
            { tempC: value, atISO: new Date().toISOString() };
        } else {
          delete state.conditions.waterOverrides[key];
        }
        writeStore(STORE_WATER, state.conditions.waterOverrides);
        render();
      };
      input.addEventListener("change", save);
      input.addEventListener("keydown", function (e) { if (e.key === "Enter") save(); });
    }
    var clear = host.querySelector(".cx-clear");
    if (clear) {
      clear.addEventListener("click", function () {
        delete state.conditions.waterOverrides[lakeKey(place.lake)];
        writeStore(STORE_WATER, state.conditions.waterOverrides);
        render();
      });
    }
    [...host.querySelectorAll("[data-horizon]")].forEach(function (b) {
      b.addEventListener("click", function () {
        state.conditions.horizon = b.dataset.horizon;
        writeUrl();
        render();
      });
    });
  }

  /** Open or close the panel, fetching weather the first time it is opened. */
  function toggle(open) {
    state.conditions.open = open === undefined ? !state.conditions.open : open;
    var host = document.getElementById("conditions-panel");
    host.hidden = !state.conditions.open;
    document.getElementById("conditions-btn")
      .classList.toggle("active", state.conditions.open);
    if (!state.conditions.open) { writeUrl(); return; }

    // The two floating panels would collide at phone width.
    // Both panels float in the same corner, so only one is up at a time.
    if (window.LakePanel) LakePanel.close();
    render();
    var place = anchor();
    Weather.load(place.lat, place.lon).then(function () { render(); });
    writeUrl();
  }

  /** Point the panel at a lake, opening it if needed. */
  function focusLake(key) {
    state.conditions.anchorKey = key;
    state.conditions.anchorAuto = false;
    astroCache = {};
    toggle(true);
  }

  window.ConditionsUI = {
    render: render,
    toggle: toggle,
    focusLake: focusLake,
    RAMP: RAMP,
    _internal: { partWindow: partWindow, colourFor: colourFor, anchor: anchor },
  };
})();
