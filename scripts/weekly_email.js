#!/usr/bin/env node
/* Build 5 Stage 4: the weekly email, run by .github/workflows/weekly-email.yml.
 *
 * Reads the owner's saved lake ids from the repository variable SAVED_LAKES (never
 * from a file in the repository), gets each lake's 7-day forecast from Open-Meteo,
 * scores it with the app's own js/astro.js, js/weather.js and js/conditions.js
 * (trout, decision 1 A), and sends one email through Resend only when a saved lake
 * has a Prime day (a best hour of 75 or more) or a stocking in the last 7 days.
 *
 * The repository is public and so are its Action logs: this prints counts only,
 * never a lake id, a lake name or the address.
 *
 * Environment: SAVED_LAKES (comma-separated ids; the workflow reads the repository
 * secret first, which GitHub masks in the log, then the repository variable),
 * RESEND_API_KEY, EMAIL_TO,
 * DRY_RUN ("true" builds the email and sends nothing), APP_URL (optional).
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
const PRIME = 0.75;
const DAYS = 7;
const FROM = "Trout Map <onboarding@resend.dev>";
const RESEND_URL = "https://api.resend.com/emails";
const DEFAULT_APP_URL = "https://lxyzh1019-cyber.github.io/HZ_Trout_Map/";

function engine() {
  const ctx = { window: {}, console, Math, Date, JSON };
  vm.createContext(ctx);
  for (const f of ["astro.js", "weather.js", "conditions.js"]) {
    vm.runInContext(fs.readFileSync(path.join(ROOT, "js", f), "utf8"), ctx, { filename: f });
  }
  return ctx.window;
}

function readJson(rel) { return JSON.parse(fs.readFileSync(path.join(ROOT, rel), "utf8")); }

/** Every water the app shows, by key: stocked lakes (all years merged), waters not stocked, rivers. */
function loadWaters() {
  const out = new Map();
  for (const f of fs.readdirSync(path.join(ROOT, "data")).filter(n => /^lakes_\d{4}\.json$/.test(n)).sort()) {
    const doc = readJson("data/" + f);
    for (const lk of (Array.isArray(doc) ? doc : doc.lakes)) {
      const key = lk.lake_id || lk.ats;
      if (!key) continue;
      const have = out.get(key);
      if (have) have.stockings.push(...(lk.stockings || []));
      else out.set(key, { key, name: lk.name, lat: lk.lat, lon: lk.lon, areaHa: lk.surface_area_ha, stockings: [...(lk.stockings || [])] });
    }
  }
  for (const lk of readJson("data/waters_unstocked.json").lakes) {
    if (!out.has(lk.lake_id)) out.set(lk.lake_id, { key: lk.lake_id, name: lk.name, lat: lk.lat, lon: lk.lon, stockings: [] });
  }
  for (const rv of readJson("data/rivers.json").stretches) {
    const spot = (rv.spots || [])[0];
    if (spot) out.set(rv.lake_id, { key: rv.lake_id, name: rv.name, lat: spot[0], lon: spot[1], stockings: [], river: true });
  }
  return out;
}

function closedNow(key) {
  try {
    const regs = readJson("data/lake_regulations.json");
    const r = (regs.lakes || regs)[key];
    return !!(r && r.season && r.season.closed);
  } catch (e) { return false; }
}

function elevation(key) {
  try {
    const e = readJson("data/lake_elevation.json");
    const v = (e.lakes || {})[key];
    return Number.isFinite(v) ? v : null;
  } catch (e) { return null; }
}

/** The stocked species, most fish first (the app's dominant order, all years). */
function speciesOf(lake) {
  const n = {};
  for (const s of lake.stockings) n[s.species] = (n[s.species] || 0) + Number(s.number || 0);
  return Object.keys(n).sort((a, b) => n[b] - n[a]);
}

function recentStockings(lake, now, days = DAYS) {
  const from = now.getTime() - days * 86400000;
  return lake.stockings.filter(s => {
    if (!s.date) return false;
    const t = Date.parse(s.date + "T12:00:00Z");
    return Number.isFinite(t) && t >= from && t <= now.getTime() + 86400000;
  });
}

/* Days by the lake's own time zone, not one fixed offset: a week can cross a
 * daylight-saving change (js/weather.js says the same about its unix times). */
function localDay(t, tz) {
  return new Date(t).toLocaleDateString("en-CA", { timeZone: tz });
}

function offsetSec(t, tz) {
  const part = new Intl.DateTimeFormat("en-US", { timeZone: tz, timeZoneName: "longOffset" })
    .formatToParts(new Date(t)).find(p => p.type === "timeZoneName");
  const m = /GMT([+-])(\d\d):(\d\d)/.exec(part ? part.value : "");
  return m ? (m[1] === "-" ? -1 : 1) * (Number(m[2]) * 3600 + Number(m[3]) * 60) : 0;
}

/** Local midnight of a YYYY-MM-DD day: Astro.dayFor expects the start of the local day. */
function localMidnight(day, tz) {
  const t = Date.parse(day + "T00:00:00Z");
  return new Date(t - offsetSec(t, tz) * 1000);
}

/** Best Bite score per local day for the next 7 days, from an Open-Meteo answer. */
function scoreWeek(W, lake, json, now) {
  const data = W.Weather._internal.compact(json);
  const C = W.Conditions;
  const elev = elevation(lake.key);
  const water = C.waterFromAir(W.Weather.dailyMeansUpTo(data, now), {
    areaHa: lake.areaHa == null ? null : lake.areaHa,
    airOffsetC: elev == null ? 0 : C.heightOffsetC(data.elevM, elev),
  });
  const iced = !!(water && water.likelyIce);
  const species = speciesOf(lake);
  const tz = data.timezone || "America/Edmonton";
  const days = new Map();
  const astroCache = {};
  for (const ts of data.t) {
    const when = new Date(ts * 1000);
    if (when < now || when.getTime() > now.getTime() + DAYS * 86400000) continue;
    const day = localDay(when.getTime(), tz);
    if (!astroCache[day]) astroCache[day] = W.Astro.dayFor(lake.lat, lake.lon, localMidnight(day, tz));
    const r = C.scoreSlot({ when, lat: lake.lat, lon: lake.lon, species: species.length ? species : ["RNTR"],
      weather: W.Weather.at(data, when), water, astro: astroCache[day],
      leadDays: Math.max(0, (when.getTime() - now.getTime()) / 86400000) });
    // Under ice the app hides the open-water score and shows the winter score.
    const s = iced ? C.scoreWinter(r).score : r.score;
    if (s == null) continue;
    const best = days.get(day);
    if (!best || s > best.score) days.set(day, { day, score: s, when, iced });
  }
  return [...days.values()];
}

function primeDays(week) { return week.filter(d => d.score >= PRIME); }

function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

function dayName(day) {
  return new Date(day + "T12:00:00Z").toLocaleDateString("en-CA", { weekday: "long", month: "short", day: "numeric", timeZone: "UTC" });
}

function hourText(when) {
  return when.toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit", timeZone: "America/Edmonton" });
}

/** report: [{lake, prime: [...], stocked: [...]}] → {subject, html, text} or null when there is nothing to say. */
function buildEmail(report, appUrl) {
  const rows = report.filter(r => r.prime.length || r.stocked.length);
  if (!rows.length) return null;
  const nPrime = rows.filter(r => r.prime.length).length, nStock = rows.filter(r => r.stocked.length).length;
  const subject = "Trout Map this week: " + [nPrime ? nPrime + " lake" + (nPrime > 1 ? "s" : "") + " with a Prime day" : "",
    nStock ? nStock + " newly stocked" : ""].filter(Boolean).join(", ");
  const html = ["<p>Your saved lakes, for the next 7 days (trout scores, estimated).</p><ul>"];
  const text = ["Your saved lakes, for the next 7 days (trout scores, estimated).", ""];
  for (const r of rows) {
    const link = appUrl + "?lake=" + encodeURIComponent(r.lake.key);
    const bits = [];
    for (const d of r.prime) bits.push(dayName(d.day) + ": Prime " + Math.round(d.score * 100) + ", best near " + hourText(d.when) + (d.iced ? " (under ice: winter score)" : ""));
    for (const s of r.stocked) bits.push("Stocked " + s.date + ": " + Number(s.number || 0).toLocaleString("en-CA") + " " + s.species);
    html.push(`<li><a href="${esc(link)}">${esc(r.lake.name)}</a><br>${bits.map(esc).join("<br>")}</li>`);
    text.push(r.lake.name + " — " + link, ...bits.map(b => "  " + b), "");
  }
  html.push("</ul><p>Check the season, rules and ice in the app before you go. Legal is not safe; ice thickness is never forecast.</p>");
  text.push("Check the season, rules and ice in the app before you go. Legal is not safe; ice thickness is never forecast.");
  return { subject, html: html.join(""), text: text.join("\n") };
}

async function getForecast(W, lake, fetchFn) {
  const res = await fetchFn(W.Weather.url(lake.lat, lake.lon));
  if (!res.ok) throw new Error("forecast HTTP " + res.status);
  return res.json();
}

async function run(env, fetchFn, now = new Date(), log = console.log) {
  const W = engine();
  const ids = String(env.SAVED_LAKES || "").split(/[,\s]+/).map(s => s.trim()).filter(Boolean);
  const waters = loadWaters();
  const lakes = ids.map(id => waters.get(id)).filter(l => l && Number.isFinite(l.lat));
  log(`saved lakes: ${ids.length} listed, ${lakes.length} found`);
  const report = [];
  let failed = 0;
  for (const lake of lakes) {
    const stocked = recentStockings(lake, now);
    let prime = [];
    if (!closedNow(lake.key)) {
      try { prime = primeDays(scoreWeek(W, lake, await getForecast(W, lake, fetchFn), now)); }
      catch (e) { failed++; }
    }
    report.push({ lake, prime, stocked });
  }
  if (lakes.length && failed === lakes.length) {
    // A dead forecast service must not look like a quiet week.
    log("every forecast failed: no email; the run fails so it shows in GitHub");
    return { sent: false, email: null, report, error: "forecasts failed" };
  }
  const email = buildEmail(report, env.APP_URL || DEFAULT_APP_URL);
  const nPrime = report.filter(r => r.prime.length).length, nStock = report.filter(r => r.stocked.length).length;
  log(`lakes with a Prime day: ${nPrime}; newly stocked: ${nStock}; forecasts that failed: ${failed}`);
  if (!email) { log("nothing to report: no email this week"); return { sent: false, email: null, report }; }
  if (String(env.DRY_RUN).toLowerCase() === "true") { log("dry run: email built, not sent"); return { sent: false, email, report }; }
  const key = String(env.RESEND_API_KEY || "").trim(), to = String(env.EMAIL_TO || "").trim();
  if (!key || !to) { log("missing RESEND_API_KEY or EMAIL_TO: not sent"); return { sent: false, email, report, error: "missing secret" }; }
  const res = await fetchFn(RESEND_URL, {
    method: "POST",
    headers: { "Authorization": "Bearer " + key, "Content-Type": "application/json" },
    body: JSON.stringify({ from: FROM, to: [to], subject: email.subject, html: email.html, text: email.text }),
  });
  log(res.ok ? "email sent" : `email not sent: Resend answered HTTP ${res.status}`);
  return { sent: res.ok, email, report, status: res.status };
}

module.exports = { run, buildEmail, scoreWeek, primeDays, recentStockings, loadWaters, speciesOf, engine, localDay, localMidnight, PRIME, FROM, RESEND_URL };

if (require.main === module) {
  run(process.env, (u, o) => fetch(u, Object.assign({ signal: AbortSignal.timeout(20000) }, o || {})))
    .then(r => { process.exitCode = r.error || (r.status && !r.sent) ? 1 : 0; })
    // A fixed text only: an error message could quote a header, which holds the key.
    .catch(e => { console.log("weekly email failed (" + (e && e.name ? e.name : "error") + ")"); process.exitCode = 1; });
}
