"""
registry.py — one stable identity per physical lake, and the rules for
deciding which lake a report row belongs to.

The problem this solves
-----------------------
Sixteen years of reports refer to the same lake in different ways. Names drift
("Captain Ayre Lake" / "Captain Eyre (Ayre) Lake"), and the land description is
mistyped: of the 340 lakes Alberta tracked with its own waterbody id between
2012 and 2019, 61 carry more than one land description across those years —
Airdrie Pond appears as both NE1-27-1-W5 and SW1-27-1-W5.

So no single field is a reliable key. Instead every row is resolved against a
registry using whatever evidence it carries, strongest first:

    waterbody_id   Alberta's own identifier. Present 2012-2019. Decisive.
    ats            An exact land-description match.
    coordinates    Published by Alberta 2012-2020, or derived from the land
                   description. Lakes are far apart — the median lake has no
                   neighbour within 12 km — so position is nearly unique.
    ats_no_quarter The 2011-2013 reports print a land description without the
                   quarter-section letter, so compare only what they give.
    alias          A name spelling already confirmed for this lake, including
                   every answer given in a past review.
    combined       Name similarity plus distance, scored together.

Anything the rules cannot settle confidently goes to a review file rather than
being guessed. Answers recorded there become aliases, so the same misspelling
or mistyped code is never asked about twice.

Confusable clusters
-------------------
Lakes that sit close together AND have similar names (Burstall Upper/Lower,
Pit 35/44/45, the Pierre Greys chain) are never auto-linked by similarity
alone — only an exact id or land description will do. Without that guard a
genuinely new lake gets silently absorbed into its neighbour, which is the one
failure that corrupts a history without anyone noticing.
"""

import csv
import difflib
import json
import math
import re
from collections import defaultdict
from pathlib import Path

from ats import ats_to_latlng, haversine_km

DATA_DIR = Path(__file__).parent.parent / "data"
PROFILES_CSV = Path(__file__).parent.parent / "profiles" / "mywildalberta_profiles.csv"
REGISTRY_PATH = DATA_DIR / "lake_registry.json"
FACTS_PATH = DATA_DIR / "lake_facts.csv"
ALIASES_PATH = DATA_DIR / "lake_aliases.csv"
REVIEW_PATH = DATA_DIR / "link_review.csv"

# A quarter-section is 0.8 km across and the ATS conversion is accurate to a
# median 0.53 km, so anything inside 1.5 km is the same piece of ground.
SAME_PLACE_KM = 1.5
# Beyond this, name similarity alone is never enough.
MAX_LINK_KM = 15.0
# Lakes closer than this with similar names are treated as confusable.
CONFUSABLE_KM = 3.0
CONFUSABLE_NAME = 0.6
# Further than this from anything known, with an unrelated name, means a lake
# the registry has not seen before rather than a link we got wrong.
NEW_LAKE_KM = 5.0

# Only true filler is dropped. "Lake", "Pond" and "Reservoir" stay: they are
# what separates Chain Lakes Reservoir from Chain Lake, and dropping them made
# distinct lakes score a perfect 1.00 against each other. For the same reason
# parentheticals are kept — "(Upper)", "(East)" is often the only difference
# between two neighbours.
NOISE_WORDS = r"\b(the|a|an|of|and)\b"


def normalize_name(name):
    """Fold a lake name to a comparable form, keeping what distinguishes it."""
    n = (name or "").lower()
    n = n.replace("&", " and ")
    n = re.sub(r"[^a-z0-9 ]", " ", n)       # brackets become spaces, text kept
    n = re.sub(NOISE_WORDS, " ", n)
    return re.sub(r"\s+", " ", n).strip()


# Words that appear in half the lakes in Alberta. Sharing one of these says
# nothing about whether two names refer to the same water.
GENERIC_TOKENS = {"lake", "lakes", "pond", "ponds", "reservoir", "creek",
                  "river", "park", "trout", "fish", "pit", "dam", "north",
                  "south", "east", "west", "upper", "lower", "little", "big"}


def name_similarity(a, b):
    """How alike two lake names are, 0 to 1.

    Character similarity alone misranks the common case where one report gives
    a short name and another gives the long one: "Payne Lake" scores higher
    against "Jane Lake" than against "Payne (Mami) Lake", which is the same
    water. So also consider whether one name's distinctive words are contained
    in the other's.
    """
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    shared = ta & tb
    # Only count containment when the shared words are distinctive ones.
    if shared - GENERIC_TOKENS:
        containment = len(shared) / min(len(ta), len(tb))
        ratio = max(ratio, containment * 0.95)
    return ratio


# Words whose whole job is to tell two neighbouring lakes apart. If one name
# carries one of these and the other does not, they are not the same water —
# no matter how similar the rest of the string looks. Upper and Lower Champion
# Lake share a land description, so without this rule they silently merge.
DISCRIMINATING_TOKENS = {
    "upper", "lower", "middle", "north", "south", "east", "west",
    "1", "2", "3", "4", "5", "first", "second", "third",
}


def discriminating_conflict(a, b):
    """True when two names disagree on a word that exists to separate lakes.

    One name being silent is not a disagreement: a report saying "Dollars Lake"
    may well mean East Dollar Lake, and "Pierre Greys Lake #1" agrees with
    "Pierre Greys Lakes (Lower) #1" even though only one of them says "Lower".
    A conflict needs both sides to make a claim, and the claims to differ —
    "#2" against "#1", or "Upper" against "Lower".
    """
    ta = set(normalize_name(a).split()) & DISCRIMINATING_TOKENS
    tb = set(normalize_name(b).split()) & DISCRIMINATING_TOKENS
    if not ta or not tb:
        return False
    return not (ta <= tb or tb <= ta)


def normalise_code(ats):
    """One spelling per quarter section, so two files can be compared."""
    return re.sub(r"[^A-Z0-9-]", "", str(ats or "").upper())


def shared_land_descriptions(registry):
    """Quarter sections that more than one lake sits on.

    Seven of the registry's 640 land descriptions are shared, and every one of
    them is a pair the survey grid cannot separate: Upper and Lower Champion,
    Upper and Lower Smuts, Pit 35 and Pit 45, MD Peace Pond #1 and #2. For
    those, the land description is the weakest evidence rather than the
    strongest, because it is the one field that is identical for both.
    """
    holders = defaultdict(set)
    for lake in registry.lakes:
        for code in lake.get("ats_codes") or []:
            holders[normalise_code(code)].add(lake["lake_id"])
    return {code for code, who in holders.items() if len(who) > 1}


def strip_quarter(ats):
    """NE10-2-28-W4 -> 10-2-28-W4. Partial codes pass through unchanged."""
    if not ats:
        return None
    return re.sub(r"^(NE|NW|SE|SW)", "", ats)


def display_name(official, common):
    """One readable name from the report's two name columns."""
    o, c = (official or "").strip(), (common or "").strip()
    if o.upper() == "UNNAMED":
        o = ""
    if o and c and o.lower() != c.lower():
        return f"{o} ({c})"
    return o or c


def _title(name):
    """Report names are often SHOUTED. Title-case them, keeping short tokens."""
    if not name or not name.isupper():
        return name
    out = []
    for word in name.split():
        if len(word) <= 2 and word.isalpha():
            out.append(word.title())
        elif re.match(r"^#?\d+$", word):
            out.append(word)
        else:
            out.append(word.title())
    return " ".join(out)


class Registry:
    def __init__(self):
        self.lakes = []                 # list of lake dicts
        self.by_id = {}
        self._wb = {}                   # waterbody_id  -> lake
        self._ats = defaultdict(list)   # exact land description -> lakes
        self._noq = defaultdict(list)   # description without quarter -> lakes
        self._alias = defaultdict(list) # normalized name -> lakes
        self._cells = defaultdict(list) # coarse spatial bucket -> lakes
        self.confusable = set()
        self._minted = 0

    # ── index maintenance ────────────────────────────────────────────────
    def _cell(self, lat, lon):
        return (round(lat * 5), round(lon * 5))     # ~20 km buckets

    def _index(self, lake):
        self.by_id[lake["lake_id"]] = lake
        if lake.get("waterbody_id"):
            self._wb[lake["waterbody_id"]] = lake
        for code in lake["ats_codes"]:
            if lake not in self._ats[code]:
                self._ats[code].append(lake)
            noq = strip_quarter(code)
            if lake not in self._noq[noq]:
                self._noq[noq].append(lake)
        for alias in lake["aliases"]:
            if lake not in self._alias[alias]:
                self._alias[alias].append(lake)
        if lake["lat"] is not None:
            c = self._cell(lake["lat"], lake["lon"])
            if lake not in self._cells[c]:
                self._cells[c].append(lake)

    def reindex(self):
        self._wb, self._ats, self._noq = {}, defaultdict(list), defaultdict(list)
        self._alias, self._cells, self.by_id = defaultdict(list), defaultdict(list), {}
        for lake in self.lakes:
            self._index(lake)
        self._find_confusable()

    def _find_confusable(self):
        self.confusable = set()
        located = [l for l in self.lakes if l["lat"] is not None]
        for i, a in enumerate(located):
            for b in located[i + 1:]:
                if abs(a["lat"] - b["lat"]) > 0.05:
                    continue
                d = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
                if d <= CONFUSABLE_KM and name_similarity(a["name"], b["name"]) >= CONFUSABLE_NAME:
                    self.confusable.add(a["lake_id"])
                    self.confusable.add(b["lake_id"])

    # ── building ─────────────────────────────────────────────────────────
    def add_lake(self, lake_id, name, lat=None, lon=None, waterbody_id=None,
                 ats_codes=(), aliases=()):
        lake = dict(lake_id=lake_id, name=name, waterbody_id=waterbody_id,
                    lat=lat, lon=lon, coord_source=None,
                    ats_codes=sorted(set(c for c in ats_codes if c)),
                    aliases=sorted({normalize_name(a) for a in aliases if normalize_name(a)}),
                    name_variants=sorted({n for n in [name, *aliases] if n}),
                    zone=None, surface_area_ha=None, amenities=None)
        self.lakes.append(lake)
        self._index(lake)
        return lake

    def mint(self, name, lat=None, lon=None, ats_codes=(), aliases=()):
        self._minted += 1
        return self.add_lake(f"lk{self._minted:04d}", name, lat, lon,
                             ats_codes=ats_codes, aliases=aliases or [name])

    def absorb(self, lake, row, wrong_ats=()):
        """Fold one resolved row's identifying details into the lake.

        `wrong_ats` holds land descriptions a review has established point at
        the wrong place. Learning one would be worse than ignoring the row: it
        teaches the matcher that a real location belongs to a lake that is not
        there, so a future report naming that spot would silently link here.
        """
        changed = False
        if row.get("ats") and row["ats"] not in lake["ats_codes"] \
                and row["ats"].upper() not in wrong_ats:
            lake["ats_codes"] = sorted(set(lake["ats_codes"] + [row["ats"]]))
            changed = True
        nm = display_name(row.get("official_name"), row.get("common_name"))
        # A few 2025 rows come back with the two name columns interleaved,
        # because that year's report leaves no gap between them. Such a row
        # still links by its land description, but its mangled name must not
        # become an alias — that would teach the matcher a name for this lake
        # that belongs to no lake at all.
        if nm and name_similarity(nm, lake["name"]) < 0.45:
            nm = ""
        if nm:
            key = normalize_name(nm)
            if key and key not in lake["aliases"]:
                lake["aliases"] = sorted(set(lake["aliases"] + [key]))
                changed = True
            if nm not in lake["name_variants"]:
                lake["name_variants"] = sorted(set(lake["name_variants"] + [nm]))
        if changed:
            self._index(lake)

    # ── scoring helpers ──────────────────────────────────────────────────
    @staticmethod
    def _name_of(lake, against):
        """The lake's own name spelling that best matches `against`.

        Public as best_matching_name() at module level, for callers outside
        the class that need to compare a report name against a lake fairly.
        """
        best, score = lake["name"], name_similarity(against, lake["name"])
        for variant in lake["name_variants"]:
            s = name_similarity(against, variant)
            if s > score:
                best, score = variant, s
        return best

    @staticmethod
    def _score(name, lake):
        return max([name_similarity(name, lake["name"])] +
                   [name_similarity(name, v) for v in lake["name_variants"]])

    def _best_by_name(self, name, lakes):
        """Pick the best-named candidate, refusing when a distinguishing word
        disagrees — that is how Upper and Lower Champion Lake get merged."""
        ranked = sorted(lakes, key=lambda l: -self._score(name, l))
        top = ranked[0]
        if discriminating_conflict(name, self._name_of(top, name)):
            return None
        if len(ranked) > 1 and self._score(name, top) - self._score(name, ranked[1]) < 0.05:
            return None                       # too close to call
        return top

    # ── candidate lookup ─────────────────────────────────────────────────
    def _nearby(self, lat, lon, radius_km):
        if lat is None:
            return []
        span = int(radius_km / 20) + 1
        base = self._cell(lat, lon)
        out = []
        for dy in range(-span, span + 1):
            for dx in range(-span, span + 1):
                out.extend(self._cells.get((base[0] + dy, base[1] + dx), []))
        return out

    def resolve(self, row, row_lat=None, row_lon=None):
        """Return (lake, method, confidence, note, alternatives).

        lake is None when the evidence does not settle it; the caller sends
        those to the review file.
        """
        lat = row_lat if row_lat is not None else row.get("lat")
        lon = row_lon if row_lon is not None else row.get("lon")
        if lat is None and row.get("ats"):
            lat, lon = ats_to_latlng(row["ats"])
        name = display_name(row.get("official_name"), row.get("common_name"))

        # 1. Alberta's own identifier.
        wb = row.get("waterbody_id")
        if wb and wb in self._wb:
            return self._wb[wb], "waterbody_id", 1.0, "", []

        # 2. Exact land description.
        code = row.get("ats")
        if code and len(self._ats.get(code, [])) == 1:
            return self._ats[code][0], "ats", 0.98, "", []
        if code and len(self._ats.get(code, [])) > 1:
            same = self._ats[code]
            best = self._best_by_name(name, same)
            if best and name_similarity(name, self._name_of(best, name)) >= 0.6:
                return best, "ats+name", 0.9, "", [l["lake_id"] for l in same]
            return None, "ats_shared", 0.0, \
                f"{len(same)} lakes share this land description", [l["lake_id"] for l in same]

        # 3. Land description without the quarter letter (2011-2013 reports).
        noq = strip_quarter(code) if code else None
        if noq and len(self._noq.get(noq, [])) == 1:
            return self._noq[noq][0], "ats_no_quarter", 0.9, "", []
        if noq and len(self._noq.get(noq, [])) > 1:
            same = self._noq[noq]
            scored = sorted(((self._score(name, l), l) for l in same), reverse=True,
                            key=lambda t: t[0])
            alts = [l["lake_id"] for _, l in scored]
            if not discriminating_conflict(name, self._name_of(scored[0][1], name)) \
               and scored[0][0] >= 0.75 \
               and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.15):
                return scored[0][1], "ats_no_quarter+name", 0.85, "", alts
            return None, "ats_no_quarter_shared", scored[0][0], \
                f"{len(same)} lakes share this partial land description", alts

        # 4. A name spelling already confirmed for exactly one lake.
        key = normalize_name(name)
        if key and len(self._alias.get(key, [])) == 1:
            lake = self._alias[key][0]
            if lat is None or lake["lat"] is None or \
               haversine_km(lat, lon, lake["lat"], lake["lon"]) <= MAX_LINK_KM:
                return lake, "alias", 0.95, "", []

        # 5. No position at all — the 2015 report gives a name and nothing else.
        #    Name is the only evidence, so demand a near-perfect match with a
        #    clear margin over the runner-up, and never touch a confusable lake.
        if lat is None:
            scored = sorted(((self._score(name, lake), lake) for lake in self.lakes),
                            key=lambda t: -t[0])
            if not scored:
                return None, "none", 0.0, "registry is empty", []
            top_s, top_lake = scored[0]
            runner_s = scored[1][0] if len(scored) > 1 else 0.0
            alts = [l["lake_id"] for _, l in scored[:4]]
            if top_lake["lake_id"] in self.confusable:
                return None, "confusable", top_s, \
                    "name-only row near a similarly named lake", alts
            if discriminating_conflict(name, self._name_of(top_lake, name)):
                return None, "discriminator", top_s, \
                    f"names disagree on which of a pair this is ({top_lake['name']})", alts
            if top_s >= 0.92 and top_s - runner_s >= 0.08:
                return top_lake, "name_only", 0.8, "", alts
            return None, "name_only_uncertain", top_s, \
                f"best {top_lake['name']} at name {top_s:.2f}, runner-up {runner_s:.2f}", alts

        # 6. Position, then name as the tiebreaker.
        cands = []
        for lake in self._nearby(lat, lon, MAX_LINK_KM):
            d = haversine_km(lat, lon, lake["lat"], lake["lon"])
            if d > MAX_LINK_KM:
                continue
            s = self._score(name, lake)
            cands.append((s * 0.6 + max(0.0, 1 - d / MAX_LINK_KM) * 0.4, s, d, lake))
        cands.sort(key=lambda t: -t[0])
        if not cands:
            return None, "none", 0.0, "no lake within %.0f km" % MAX_LINK_KM, []

        score, sim, dist, lake = cands[0]
        runner = cands[1] if len(cands) > 1 else (0.0, 0.0, 99.0, None)
        alts = [l["lake_id"] for _, _, _, l in cands[:4]]

        if lake["lake_id"] in self.confusable:
            return None, "confusable", 0.0, \
                "close to a similarly named lake; needs a human", alts
        if discriminating_conflict(name, self._name_of(lake, name)):
            return None, "discriminator", sim, \
                f"names disagree on which of a pair this is ({lake['name']})", alts
        if sim >= 0.9 and dist <= 8:
            return lake, "name+location", 0.9, "", alts
        if dist <= SAME_PLACE_KM and sim >= 0.5:
            return lake, "location", 0.85, "", alts
        if score - runner[0] >= 0.25 and sim >= 0.75:
            return lake, "name+location", 0.8, "", alts
        # Far from everything known and named nothing like it: that is a lake
        # the registry has never seen, not an ambiguity to ask a human about.
        if dist > NEW_LAKE_KM and sim < 0.5:
            return None, "unknown_lake", score, \
                f"nearest is {lake['name']} at {dist:.1f} km, name {sim:.2f}", alts
        return None, "uncertain", score, \
            f"best {lake['name']} at {dist:.1f} km, name {sim:.2f}", alts


# ─────────────────────────────────────────────────────────────────────────
# Aliases recorded by past reviews
# ─────────────────────────────────────────────────────────────────────────
def load_aliases():
    """Return {'name': {normalized name: lake_id}, 'ats': {code: lake_id}}."""
    out = {"name": {}, "ats": {}, "new": set(), "skip": set(), "wrong_ats": set()}
    if not ALIASES_PATH.exists():
        return out
    with open(ALIASES_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            kind = (row.get("kind") or "").strip()
            value = (row.get("value") or "").strip()
            lake_id = (row.get("lake_id") or "").strip()
            if kind == "name" and value and lake_id:
                out["name"][normalize_name(value)] = lake_id
            elif kind == "ats" and value and lake_id:
                out["ats"][value.upper()] = lake_id
            elif kind == "wrong_ats" and value:
                out["wrong_ats"].add(value.upper())
            elif kind in ("new", "skip") and value:
                out[kind].add(normalize_name(value))
    return out


def save_registry(registry, path=REGISTRY_PATH):
    payload = [{k: v for k, v in lake.items()} for lake in registry.lakes]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_registry(path=REGISTRY_PATH):
    reg = Registry()
    reg.lakes = json.loads(path.read_text(encoding="utf-8"))
    reg.reindex()
    return reg


# ─────────────────────────────────────────────────────────────────────────
# Profile enrichment (zone, amenities, verified coordinates)
# ─────────────────────────────────────────────────────────────────────────
def load_profiles():
    profiles = {}
    if not PROFILES_CSV.exists():
        return profiles
    with open(PROFILES_CSV, newline="", encoding="cp1252") as f:
        for row in csv.DictReader(f):
            code = (row.get("ats") or "").strip()
            if not code:
                continue

            def num(key):
                try:
                    return float((row.get(key) or "").strip())
                except (TypeError, ValueError):
                    return None

            area = None
            m = re.search(r"(\d+(?:\.\d+)?)", (row.get("surface_area") or "").replace(",", ""))
            if m:
                area = float(m.group(1))
            profiles[code] = dict(
                name=(row.get("Trout Map Name") or row.get("name") or "").strip() or None,
                lat=num("override_lat") if num("override_lat") is not None else num("lat"),
                lon=num("override_lon") if num("override_lon") is not None else num("lon"),
                zone=(row.get("zone") or "").strip() or None,
                surface_area_ha=area,
                amenities=(row.get("site_amenities") or "").strip() or None,
            )
    return profiles


def best_matching_name(lake, against):
    """The spelling of `lake`'s name that best matches `against`.

    A lake carries every spelling its reports have used, so comparing a report
    name against only the canonical one understates the match.
    """
    return Registry._name_of(lake, against)
