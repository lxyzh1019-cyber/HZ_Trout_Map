"""Read catch limits and seasons out of the Alberta sportfishing regulations.

This is the only part of the pipeline that produces something an angler could be
fined for getting wrong, so it is written to fail closed. Where the guide is
ambiguous, or where a row cannot be read with confidence, nothing is published
for that waterbody and the app falls back to showing the official link.

Two things about the document itself are worth knowing before reading the code.

The regulation tables are typeset SIDEWAYS — every character carries a 90 degree
rotation matrix. Read naively they come out with the axes swapped and the text
reversed, which is not obviously broken: strings like "tuort 2" reverse cleanly
to "2 trout" and it looks as though simply reversing them works. It does not.
Any cell that wraps onto a second line comes back interleaved, so "Other trout
under 35 cm" silently becomes "Other under 35 trout cm". The fix is to tell
pdfminer the page is rotated before pdfplumber builds its own view of it, which
costs nothing and needs no extra dependency.

And the guide states its own precedence, which is not the obvious one. A lake is
resolved in three steps, in this order:

    1. a site-specific row in its Watershed Unit table wins outright;
    2. otherwise, if it is on the provincial put-and-take stocked list, the
       province-wide stocked-trout regulations apply — "unless the waterbody is
       stocked, in which case provincial put and take stocked lake regulations
       apply", in the guide's own words;
    3. otherwise the Watershed Unit default applies.

Step 2 matters more here than anywhere else: this map is a map of stocked lakes,
so most of its lakes resolve there rather than in the tables.

Three rules from the guide are load-bearing and easy to get backwards. Each one
is quoted where it is implemented, and each has a test:

    an unlisted waterbody is not unknown, it takes the zone default
    a listed waterbody with a blank season is CLOSED, not unknown
    a blank species cell means the species is not likely present, not unlimited
"""

import json
import re
from pathlib import Path

import pdfplumber
from pdfplumber.page import Page

import registry

ATS = r"(?:NE|NW|SE|SW)?\s*\d{1,2}-\d{1,3}-\d{1,2}-W\d"

# The guide's own species codes. Happily these are the codes this repository
# already uses for trout, so no translation table is needed for them.
SPECIES_CODES = {
    "BKTR", "BNTR", "BURB", "CISC", "CTTR", "DLVR", "GOLD", "LKTR", "LKWH",
    "MNWH", "NRPK", "RNTR", "SAUG", "TGTR", "WALL", "YLPR", "ARGR", "SPLK",
}


def _sideways(pdf, page_number):
    """The same page, read as though it were turned upright.

    Setting the rotation on pdfminer's page object has to happen before
    pdfplumber builds a Page from it, because pdfplumber reads the rotation
    once, in its constructor, and caches everything downstream of it.
    """
    page = pdf.pages[page_number - 1]
    page.page_obj.rotate = 90
    return Page(pdf, page.page_obj, page_number=page_number, initial_doctop=0)


def _cell(value):
    return re.sub(r"\s+", " ", (value or "").replace("\n", " ")).strip()


def parse_limit(text):
    """Turn a limit cell into something comparable, keeping the original words.

    The guide's own legend: "'3 over 63 cm' indicates a possession and size
    limit of '3 fish each over 63 cm' or '10 fish' indicates a possession limit
    of 10 for that species of any size."

    The original string is always kept alongside. What an angler reads must be
    what the guide says, not our paraphrase of it.
    """
    raw = _cell(text)
    if not raw:
        # "An empty cell indicates the species is not likely present" — which is
        # emphatically not the same as "no limit".
        return None
    out = {"text": raw}
    count = re.match(r"^\s*(\d+)\b", raw)
    if count:
        out["count"] = int(count.group(1))
    size = re.search(r"\b(over|under)\s+(\d+)\s*cm", raw, re.I)
    if size:
        out["size_op"] = size.group(1).lower()
        out["size_cm"] = int(size.group(2))
    if re.search(r"\bcatch\s*and\s*release\b", raw, re.I) or out.get("count") == 0:
        out["zero"] = True
    return out


def parse_season(text):
    """A blank season on a LISTED waterbody means closed, and that is the rule
    most likely to hurt someone if it is read as "unknown".

    The guide: "If a listed waterbody does not have a season listed, it is
    CLOSED to fishing during that period."
    """
    raw = _cell(text)
    if not raw:
        return {"text": "", "closed": True, "implied": True}
    if re.match(r"^CLOSED\b", raw, re.I):
        return {"text": raw, "closed": True, "implied": False}
    return {"text": raw, "closed": False, "implied": False}


def parse_bait(text):
    """Expand the bait column's legend marker into words.

    The tables print a lone "l" in this column on most rows, and the column
    heading defines it: "Bait l = Bait except Bait fish allowed". Three quarters
    of the rows carry it, so leaving it alone would put a bare glyph in front of
    an angler as though it meant something.
    """
    raw = _cell(text)
    if raw in {"l", "I", "|"}:
        return "Bait allowed, except bait fish"
    return raw


def _table_rows(page):
    tables = page.extract_tables()
    if not tables:
        return None, []
    table = max(tables, key=lambda t: len(t) * max(len(r) for r in t))
    header = None
    for row in table:
        cells = [_cell(c) for c in row]
        if cells and cells[0] == "Waterbody":
            header = cells
            break
    if not header:
        return None, []
    rows = []
    for row in table:
        cells = [_cell(c) for c in row]
        if not cells or cells[0] == "Waterbody":
            continue
        if re.match(r"^(ES|NB|PP)[1-4]\s*[-–]", cells[0]):
            continue
        rows.append(dict(zip(header, cells)))
    return header, rows


def read_tables(pdf):
    """Every site-specific row, keyed by watershed unit.

    A zone's table runs over several pages and only the first repeats the
    "ES1 - Lakes, Reservoirs and Ponds" heading, so the current zone is carried
    forward. A row with a blank waterbody name is a continuation of the one
    above it — usually a tributary with its own season — and is attached to it
    rather than dropped.
    """
    zones, zone, kind = {}, None, None
    for number in range(1, len(pdf.pages) + 1):
        if not pdf.pages[number - 1].chars:
            continue
        page = _sideways(pdf, number)
        text = page.extract_text() or ""
        if not re.search(r"Waterbody\s+Waterbody Detail\s+Season", text):
            continue
        heading = re.search(
            r"\b(ES[1-4]|NB[1-4]|PP[12])\s*[-–]\s*"
            r"(Lakes, Reservoirs and Ponds|Rivers, Creeks and Streams)", text)
        if heading:
            zone = heading.group(1)
            kind = "lakes" if "Lakes" in heading.group(2) else "rivers"
        if zone is None:
            continue
        header, rows = _table_rows(page)
        if not header:
            continue
        bucket = zones.setdefault(zone, {"lakes": {}, "rivers": {}, "pages": []})
        bucket["pages"].append(number)
        current = None
        for row in rows:
            name = row.get("Waterbody", "")
            species = {k: parse_limit(v) for k, v in row.items()
                       if k in SPECIES_CODES and _cell(v)}
            detail = row.get("Waterbody Detail", "")
            entry = {
                "detail": detail,
                "season": parse_season(row.get("Season")),
                "bait": parse_bait(next((v for k, v in row.items()
                                         if k.startswith("Bait")), "")),
                "species": species,
                "trout_total": parse_limit(row.get("Trout Total")),
                "page": number,
            }
            # Some waterbodies are not regulated in their own right: the row
            # carries no season and points somewhere else, as PP1's Bassano
            # Reservoir points at the Bow River. Left alone, the blank-season
            # rule would report those as CLOSED ALL YEAR, which is false. It
            # errs safe rather than dangerous, but it is still wrong, and the
            # app would be useless for that water. Mark them and publish
            # nothing, so the official link is shown instead.
            if re.match(r"^See\b", detail, re.I) and entry["season"]["implied"]:
                entry["cross_reference"] = detail
                entry["season"] = {"text": "", "closed": False, "implied": False,
                                   "unknown": True}

            if name:
                current = entry
                bucket[kind][name] = entry
            elif current is not None:
                # A tributary or second season for the waterbody above.
                current.setdefault("also", []).append(entry)
    return zones


def read_defaults(pdf):
    """What applies when a waterbody is not listed at all.

    The guide: "If a ES1 lake, reservoir, river, stream or species is not
    listed, follow the default regulations below."
    """
    defaults = {}
    for number in range(1, len(pdf.pages) + 1):
        page = pdf.pages[number - 1]
        if not page.chars:
            continue
        text = page.extract_text() or ""
        found = re.search(r"(ES[1-4]|NB[1-4]|PP[12]) WATERSHED UNIT REGULATIONS", text)
        if not found:
            continue
        zone = found.group(1)
        lakes = re.search(r"LAKES\s*(.*?)(?:STREAMS|$)", text, re.S)
        block = lakes.group(1) if lakes else ""
        limits = {}
        for label, value in re.findall(r"[•l]\s*([A-Z][A-Za-z \-]+?)\s+limit\s+([^\n•]+)", block):
            limits[label.strip()] = _cell(value)
        season = re.search(r"LAKES\s*[•l]?\s*(OPEN[^\n•]*|CLOSED[^\n•]*)", text)
        defaults[zone] = {
            "lakes": {
                "season": parse_season(season.group(1) if season else ""),
                "limits": limits,
                "bait": "Bait allowed" if re.search(r"Bait except Bait Fish allowed|Bait allowed", block) else "",
            },
            "page": number,
        }
    return defaults


def _segments(page, gap=12, line_tol=3):
    """Every run of words on a page that is separated from its neighbours.

    Columns cannot be found once for a whole page here: the stocked list sets a
    two-column introduction above a three-column list, so any single split puts
    entries in the wrong column. Instead each printed line is cut wherever a
    horizontal gap opens up, which works whatever the column count is and
    wherever it changes.
    """
    words = sorted(page.extract_words(), key=lambda w: (round(w["top"]), w["x0"]))
    lines, current, top = [], [], None
    for w in words:
        if top is None or abs(w["top"] - top) <= line_tol:
            current.append(w)
            top = w["top"] if top is None else top
        else:
            lines.append((top, current))
            current, top = [w], w["top"]
    if current:
        lines.append((top, current))

    out = []
    for top, line in lines:
        run = [line[0]]
        for w in line[1:]:
            if w["x0"] - run[-1]["x1"] > gap:
                out.append({"top": top, "x0": run[0]["x0"],
                            "text": " ".join(x["text"] for x in run)})
                run = [w]
            else:
                run.append(w)
        out.append({"top": top, "x0": run[0]["x0"],
                    "text": " ".join(x["text"] for x in run)})
    return out


def read_stocked(pdf):
    """The provincial put-and-take list, which governs most lakes on this map.

    These pages are NOT rotated, but they are set in columns, and that is the
    trap. Reading the page as flat text runs the columns together: a first pass
    produced "Tim Horton Children's Pond Fairfax Lake" as a single waterbody and
    glued a stray land description onto another as "SE 31-79- Chatwin Lake".
    Either would have attached a real limit to the wrong water, silently, which
    is the worst thing this file could do.

    So entries are assembled from line segments. Most read "Name (land
    description)" in one piece; where a name is long the description wraps onto
    the line below, in the same column, and is joined back to it.
    """
    stocked = {}
    for number in range(1, len(pdf.pages) + 1):
        page = pdf.pages[number - 1]
        if not page.chars:
            continue
        text = page.extract_text() or ""
        if not re.search(r"Watershed Unit\s+(ES|NB|PP)[1-4]", text):
            continue
        if len(re.findall(ATS, text)) < 20:
            continue

        segments = _segments(page)
        for index, segment in enumerate(segments):
            body = segment["text"]
            # A description alone on its line belongs to the name above it, in
            # the same column.
            if re.fullmatch(r"\(" + ATS + r"\)", body.strip()):
                for previous in reversed(segments[:index]):
                    if abs(previous["x0"] - segment["x0"]) < 14 and previous["top"] < segment["top"]:
                        body = previous["text"].rstrip() + " " + body
                        break
            match = re.search(
                # A name may carry a parenthetical anywhere in it, not only at
                # the end: "Shunda (Fish) Lake" and "Mcleod Lake (Carson Lake)"
                # are both real names. Only the LAST bracket is the land
                # description.
                r"([A-Z][A-Za-z0-9\u2019'&#\.\- ]{1,45}"
                r"(?:\([A-Za-z ]+\)[A-Za-z0-9\u2019'&#\.\- ]{0,25})?)\s*\((" + ATS + r")\)$",
                body.strip())
            if not match:
                continue
            name = match.group(1).strip(" -")
            name = re.sub(r"^(?:Watershed Unit\s*\w*|(?:NE|NW|SE|SW)?\s*[\d\-]+)\s*", "", name).strip()
            if len(name) > 2:
                stocked[name] = {"ats": _cell(match.group(2)), "page": number}
    return stocked


# The province-wide put-and-take regulations, quoted from the guide's own
# summary box. Held here rather than parsed because it is five lines of prose
# that would be fragile to pattern-match and trivial to check by eye.
PUT_AND_TAKE = {
    "season": {"text": "OPEN all year", "closed": False, "implied": False},
    "bait": "Bait is allowed",
    "limits": {
        "Trout": "5 trout of any size",
        "Northern Pike": "3 Northern Pike of any size",
        "Yellow Perch": "15 Yellow Perch of any size",
    },
    "note": "For other species, see Maximum Possession limits.",
}


def load(pdf_path):
    with pdfplumber.open(str(pdf_path)) as pdf:
        text = pdf.pages[0].extract_text() or ""
        year = re.search(r"\b(20\d\d)\b", (pdf.metadata or {}).get("Title", "") + " " + text)
        return {
            "guide_year": int(year.group(1)) if year else None,
            "source_file": Path(pdf_path).name,
            "zones": read_tables(pdf),
            "defaults": read_defaults(pdf),
            "stocked": read_stocked(pdf),
            "put_and_take": PUT_AND_TAKE,
        }


def resolve(name, zone, regs):
    """Apply the guide's precedence: site-specific, then stocked, then default.

    Returns None when nothing can be said, which the app renders as the official
    link and nothing else. Guessing here is worse than saying nothing.
    """
    unit = regs["zones"].get(zone, {})
    row = unit.get("lakes", {}).get(name)
    if row:
        if row.get("cross_reference"):
            # Nothing to publish: the guide sends the reader elsewhere, and
            # following that pointer for them is exactly the kind of guess this
            # file does not make.
            return {"basis": "cross-reference", "zone": zone,
                    "see": row["cross_reference"]}
        return {"basis": "site-specific", "zone": zone, **row}
    if name in regs["stocked"]:
        return {"basis": "put-and-take", "zone": zone, **regs["put_and_take"]}
    fallback = regs["defaults"].get(zone)
    if fallback:
        return {"basis": "watershed-default", "zone": zone, **fallback["lakes"]}
    return None


if __name__ == "__main__":
    import sys
    regs = load(sys.argv[1])
    print(f"guide year        : {regs['guide_year']}")
    print(f"watershed units   : {len(regs['zones'])}")
    print(f"site-specific rows: {sum(len(z['lakes']) for z in regs['zones'].values())} lakes, "
          f"{sum(len(z['rivers']) for z in regs['zones'].values())} rivers")
    print(f"zone defaults     : {len(regs['defaults'])}")
    print(f"put-and-take list : {len(regs['stocked'])}")


# How alike two names must be before a fuzzy match is trusted, and how unlike
# every candidate must be before a lake is accepted as genuinely unlisted.
CONFIDENT = 0.92
CLEARLY_ABSENT = 0.75


def _best_match(target, candidates):
    """The closest name and its score, using the registry's own comparison."""
    best, score = None, 0.0
    for candidate in candidates:
        this = registry.name_similarity(target, candidate)
        if this > score:
            best, score = candidate, this
    return best, score


def match_lakes(regs, lakes):
    """Resolve every lake to a regulation, or to nothing at all.

    The unsafe move here is to fall back to the watershed default whenever a
    name fails to match, because the default is often more permissive than the
    site-specific row it would be standing in for: ES1 defaults to five trout
    with bait allowed, while Barnaby Lake inside ES1 is one trout over 40 cm
    under a bait ban. Missing that row and showing the default would invite
    someone to keep four fish too many.

    So the default is used only where there is positive evidence the lake is
    unlisted — nothing in the zone resembles its name. Where something resembles
    it but not closely enough to be sure, nothing is published and the lake is
    written to the review file for a human to settle.
    """
    resolved, review = {}, []
    for lake in lakes:
        zone = lake.get("zone")
        name = lake.get("name") or ""
        key = lake.get("lake_id") or lake.get("ats")
        if not key:
            continue
        if not zone:
            review.append({"lake": name, "lake_id": key, "zone": "",
                           "why": "no fish management zone recorded",
                           "closest": "", "score": ""})
            continue

        target = registry.normalize_name(name)
        site = {registry.normalize_name(k): k for k in regs["zones"].get(zone, {}).get("lakes", {})}
        stock = {registry.normalize_name(k): k for k in regs["stocked"]}

        if target in site:
            found = resolve(site[target], zone, regs)
            found["matched_name"] = site[target]
            resolved[key] = found
            continue
        if target in stock:
            found = resolve(stock[target], zone, regs)
            found["matched_name"] = stock[target]
            resolved[key] = found
            continue

        near_site, site_score = _best_match(target, site)
        near_stock, stock_score = _best_match(target, stock)
        near, score, pool = (
            (near_site, site_score, "site") if site_score >= stock_score
            else (near_stock, stock_score, "stocked"))

        if score >= CONFIDENT:
            original = site[near] if pool == "site" else stock[near]
            found = resolve(original, zone, regs)
            found["matched_name"] = original
            found["match_score"] = round(score, 3)
            resolved[key] = found
        elif score < CLEARLY_ABSENT:
            # Nothing in this zone looks anything like it, which is evidence
            # that it really is unlisted — and an unlisted lake takes the
            # default, by the guide's own rule.
            found = resolve("__unlisted__", zone, regs)
            if found:
                resolved[key] = found
        else:
            review.append({
                "lake": name, "lake_id": key, "zone": zone,
                "why": "a similar name exists but is not close enough to trust",
                "closest": (site[near] if pool == "site" else stock[near]) if near else "",
                "score": round(score, 3),
            })
    return resolved, review
