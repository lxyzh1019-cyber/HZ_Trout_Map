"""Build 5 Stage 4: no sign-in. Storage, the Home Screen tip, Back up and Restore
(js/device.js), the weekly email (scripts/weekly_email.js and its workflow), and the
monthly commit that keeps the scheduled jobs on.

    PYTHONPATH=scripts python3 -m unittest scripts/test_device_and_email.py
"""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"


def node(script, args):
    exe = shutil.which("node")
    if not exe:
        raise unittest.SkipTest("node is not installed")
    out = subprocess.run([exe, "-e", script], input=json.dumps(args), capture_output=True, text=True,
                         encoding="utf-8", check=True, cwd=ROOT)
    return json.loads(out.stdout)


DEVICE = r"""
const fs = require('fs'), vm = require('vm');
const ctx = { window: {}, console, JSON, Date }; vm.createContext(ctx);
vm.runInContext(fs.readFileSync('js/device.js', 'utf8'), ctx);
const D = ctx.window.Device, A = JSON.parse(fs.readFileSync(0, 'utf8'));
const spots = { file: '2 files', importedAt: '2026-11-07T00:00:00Z', result: { spots: [{ id: 's1', lake: 'wb5952' }], saved: [], notPlaced: [], total: 3, counts: {} } };
const b = D.makeBackup(['wb5952', 'gu-pp2-gull-lake'], spots, new Date('2026-11-07T12:00:00Z'));
const back = D.readBackup(JSON.stringify(b));
const iphone = { userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Safari', maxTouchPoints: 5 };
const ipad = { userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari', maxTouchPoints: 5 };
const mac = { userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari', maxTouchPoints: 0 };
const homeScreen = { userAgent: iphone.userAgent, maxTouchPoints: 5, standalone: true };
const win = { matchMedia: () => ({ matches: false }) };
process.stdout.write(JSON.stringify({
  name: D.backupName(new Date('2026-11-07T12:00:00Z')), back,
  bad: [D.readBackup('not json'), D.readBackup('{"app":"other"}'), D.readBackup(JSON.stringify(Object.assign({}, b, { version: 9 }))),
        D.readBackup(JSON.stringify(Object.assign({}, b, { favourites: [1, 2] })))].map(r => r.ok),
  summary: D.summaryText(back.summary),
  tip: [D.tipWanted(iphone, win, false), D.tipWanted(ipad, win, false), D.tipWanted(mac, win, false),
        D.tipWanted(homeScreen, win, false), D.tipWanted(iphone, win, true)],
  tipText: D.TIP_TEXT, kept: D.STORAGE_TEXT.kept,
}));
"""


class DeviceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = node(DEVICE, {})

    def test_a_backup_comes_back_whole(self):
        b = self.r["back"]
        self.assertTrue(b["ok"])
        self.assertEqual(b["backup"]["favourites"], ["wb5952", "gu-pp2-gull-lake"])
        self.assertEqual(b["summary"], {"lakes": 2, "places": 3, "made": "2026-11-07T12:00:00.000Z"})
        self.assertEqual(self.r["name"], "trout-map-backup-2026-11-07.json")
        self.assertEqual(self.r["summary"], "Backup from 2026-11-07: 2 saved lakes and 3 imported places.")

    def test_a_damaged_or_foreign_file_is_refused(self):
        self.assertEqual(self.r["bad"], [False, False, False, False])

    def test_the_tip_shows_once_on_iphone_and_ipad_safari_only(self):
        # iPhone, iPad (says Macintosh, has touch), a Mac, already on the Home Screen, already seen.
        self.assertEqual(self.r["tip"], [True, True, False, False, False])
        self.assertIn("Safari clears site data after 7 days without use. Home Screen apps are exempt.", self.r["tipText"])

    def test_settings_and_restore_in_the_page(self):
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        for snippet in ('<div class="group" id="settings-group">', 'id="backup-btn">Back up</button>',
                        'id="restore-btn">Restore</button>', 'id="copy-ids-btn">Copy saved lake ids</button>',
                        "// Decision 2 A: Restore replaces what this browser has, after you confirm.",
                        'if (!confirm(Device.summaryText(read.summary) + " Replace the saved lakes and spots in this browser with it?")) {'):
            self.assertIn(snippet, page)
        dev = (ROOT / "js" / "device.js").read_text(encoding="utf-8")
        for call in ("fetch(", "XMLHttpRequest", "sendBeacon"):
            self.assertNotIn(call, dev)          # a backup is never sent anywhere
        self.assertIn("s.persist()", dev)
        sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        self.assertIn('"js/device.js"', sw)

    def test_no_backup_file_in_the_repository(self):
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
        self.assertFalse([f for f in tracked if "backup" in Path(f).name.lower() and f.endswith(".json")])


EMAIL = r"""
const fs = require('fs');
const E = require('./scripts/weekly_email.js');
const A = JSON.parse(fs.readFileSync(0, 'utf8'));
function forecast(now) {
  const t0 = Math.floor(now.getTime() / 3600000) * 3600 - 24 * 3600, n = 24 * 8;
  const time = [], air = [], cloud = [], wind = [], gust = [], precip = [], pres = [];
  for (let i = 0; i < n; i++) { time.push(t0 + i * 3600); air.push(14); cloud.push(60); wind.push(10); gust.push(15); precip.push(0); pres.push(1012 - i * 0.05); }
  const dt = [], dm = [];
  for (let d = -7; d < 8; d++) { dt.push(Math.floor(now.getTime() / 86400000 + d) * 86400); dm.push(14); }
  return { utc_offset_seconds: -25200, timezone: 'America/Edmonton', elevation: 900,
    hourly: { time, temperature_2m: air, cloud_cover: cloud, wind_speed_10m: wind, wind_gusts_10m: gust, precipitation: precip,
              precipitation_probability: precip, pressure_msl: pres, weather_code: precip, wind_direction_10m: precip },
    daily: { time: dt, temperature_2m_mean: dm } };
}
async function go() {
  const out = {};
  for (const c of A.cases) {
    const now = new Date(c.now), calls = [], logs = [];
    const fake = async (u, o) => { calls.push({ u: String(u), o: o || null });
      if (String(u).startsWith(E.RESEND_URL)) return { ok: true, status: 200, json: async () => ({ id: 'x' }) };
      return { ok: true, status: 200, json: async () => forecast(now) }; };
    const r = await E.run(c.env, fake, now, s => logs.push(s));
    const W = E.engine(), lake = E.loadWaters().get('wb5952');
    out[c.name] = { sent: r.sent, email: r.email, logs, resend: calls.filter(x => x.u.startsWith(E.RESEND_URL)).map(x => ({ h: x.o.headers, b: JSON.parse(x.o.body) })),
      week: c.name === 'stocked' ? E.scoreWeek(W, lake, forecast(now), now).map(d => d.score) : null };
  }
  out.prime = E.primeDays([{ score: 0.80 }, { score: 0.74 }, { score: 0.75 }]).length;
  out.none = E.buildEmail([{ lake: { key: 'a', name: 'A' }, prime: [], stocked: [] }], 'https://x/');
  process.stdout.write(JSON.stringify(out));
}
go();
"""


class WeeklyEmailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = {"SAVED_LAKES": "wb3482, wb5952,not-a-lake", "RESEND_API_KEY": "re_test_key", "EMAIL_TO": "owner@example.com",
                "APP_URL": "https://app.example/"}
        cls.r = node(EMAIL, {"cases": [
            # Mount Lorette Ponds was stocked on 2026-07-22 (data/lakes_*.json).
            {"name": "stocked", "now": "2026-07-24T15:00:00Z", "env": dict(base, DRY_RUN="false")},
            {"name": "dry", "now": "2026-07-24T15:00:00Z", "env": dict(base, DRY_RUN="true")},
            {"name": "quiet", "now": "2026-07-24T15:00:00Z", "env": dict(base, SAVED_LAKES="", DRY_RUN="false")},
        ]})

    def test_a_new_stocking_sends_one_email_through_resend(self):
        s = self.r["stocked"]
        self.assertTrue(s["sent"])
        self.assertEqual(len(s["resend"]), 1)
        call = s["resend"][0]
        self.assertEqual(call["h"]["Authorization"], "Bearer re_test_key")
        self.assertEqual(call["b"]["from"], "Trout Map <onboarding@resend.dev>")
        self.assertEqual(call["b"]["to"], ["owner@example.com"])
        self.assertIn("Mount Lorette Ponds", call["b"]["html"])
        self.assertIn("Stocked 2026-07-22", call["b"]["text"])
        self.assertIn("https://app.example/?lake=wb3482", call["b"]["html"])
        self.assertIn(len(s["week"]), (7, 8))                     # the next 7 days touch 7 or 8 calendar days
        self.assertTrue(all(0 <= x <= 1 for x in s["week"]))

    def test_a_dry_run_and_a_quiet_week_send_nothing(self):
        self.assertFalse(self.r["dry"]["sent"])
        self.assertEqual(self.r["dry"]["resend"], [])
        self.assertIsNotNone(self.r["dry"]["email"])
        self.assertFalse(self.r["quiet"]["sent"])
        self.assertEqual(self.r["quiet"]["resend"], [])
        self.assertIsNone(self.r["none"])
        self.assertEqual(self.r["prime"], 2)                      # 75 and up is Prime

    def test_the_public_log_shows_counts_only(self):
        for case in ("stocked", "dry", "quiet"):
            log = "\n".join(self.r[case]["logs"])
            for secret in ("wb3482", "wb5952", "not-a-lake", "Mount Lorette", "Sylvan", "owner@example.com", "re_test_key"):
                self.assertNotIn(secret, log, (case, secret))
        self.assertIn("saved lakes: 3 listed, 2 found", self.r["stocked"]["logs"][0])

    def test_the_workflow_reads_the_variable_and_secrets(self):
        wf = (WF / "weekly-email.yml").read_text(encoding="utf-8")
        for snippet in ("SAVED_LAKES: ${{ vars.SAVED_LAKES }}", "RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}",
                        "EMAIL_TO: ${{ secrets.EMAIL_TO }}", 'cron: "37 14 * * 4"', "default: true", "contents: read"):
            self.assertIn(snippet, wf)
        js = (ROOT / "scripts" / "weekly_email.js").read_text(encoding="utf-8")
        self.assertIn('const FROM = "Trout Map <onboarding@resend.dev>";', js)
        self.assertNotIn("saved_lakes.json", js.lower())         # never a file in the repository


class ScheduledJobsStayOnTests(unittest.TestCase):
    def test_the_advisories_job_commits_once_a_month(self):
        wf = (WF / "advisories.yml").read_text(encoding="utf-8")
        self.assertIn('if [ "$(date -u +%d)" = "01" ]; then', wf)
        self.assertIn("date -u +%F > live/last_checked.txt", wf)
        # The commit step after it still commits only when live/ changed.
        self.assertLess(wf.index("live/last_checked.txt"), wf.index('git status --porcelain live/'))

    def test_the_feature_check_runs_on_pull_requests(self):
        wf = (WF / "checks.yml").read_text(encoding="utf-8")
        self.assertIn("fetch-depth: 0", wf)
        self.assertIn("central/checks/feature_check.py", wf)
        self.assertIn("if: github.event_name == 'pull_request'", wf)


if __name__ == "__main__":
    unittest.main()
