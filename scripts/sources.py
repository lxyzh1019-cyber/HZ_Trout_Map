"""
sources.py — read every year's stocking report into one normalized row shape.

Alberta has published this report in four different layouts since 2011, and for
some years the machine-readable file is only a partial snapshot. This module
hides all of that: ask for a year, get back a list of normalized rows.

Normalized row
--------------
    year            int, the stocking season
    official_name   str, waterbody official name ("" if the report says Unnamed)
    common_name     str, waterbody common name ("" if absent)
    ats             str or None — the land description. May be a *partial* code
                    with no quarter letter (2011-2013), e.g. "10-2-28-W4".
    waterbody_id    str or None — Alberta's own stable waterbody identifier.
                    Present 2012-2019 only. When present it is authoritative.
    lat, lon        float or None — coordinates published by Alberta.
                    Present 2012-2020 only.
    species         4-letter code (RNTR, BKTR, BNTR, TGTR, CTTR, ...)
    strain          str
    genotype        str
    length_cm       float or None
    number          int
    date            "YYYY-MM-DD"
    date_precision  "day" or "month" (2011-2013 report a month only; those are
                    approximated to the first of the month)
    source          which file the row came from

Why each year uses the source it does
-------------------------------------
Measured row counts, PDF versus spreadsheet, decided this:

  2011        PDF only. No spreadsheet exists.
  2012-2014   CSV. Carries the waterbody id, coordinates and an exact date;
              the PDF for those years has a month only.
  2015        PDF. The CSV holds 79 rows against 304 in the PDF — a fragment.
  2016-2019   CSV. The PDFs for these years carry no land description at all,
              only a district and a name.
  2020        CSV. Coordinates and land description, comparable to the PDF.
  2021-2024   XLSX. Comparable to the PDF and already tabular.
  2025        PDF. The spreadsheet holds 279 rows against 591 in the PDF, and
              undercounts Payne Lake alone by 130,000 fish.
  2026        PDF only. Current season, so the figures are still provisional.
"""

import csv
import datetime as dt
import re
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"

TROUT_SPECIES = {"RNTR", "BKTR", "BNTR", "TGTR", "CTTR", "WSCT"}

# Full names used by the 2015-2019 spreadsheets, and a few one-off spellings.
SPECIES_BY_NAME = {
    "RAINBOW TROUT": "RNTR",
    "BROOK TROUT": "BKTR",
    "BROWN TROUT": "BNTR",
    "TIGER TROUT": "TGTR",
    "CUTTHROAT TROUT": "CTTR",
    "WESTSLOPE CUTTHROAT TROUT": "WSCT",
    "WALLEYE": "WALL",
    "ARCTIC GRAYLING": "ARGR",
    "LAKE TROUT": "LKTR",
    "SPLAKE": "SPLK",
    "GOLDEN TROUT": "GLTR",
}

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
MONTHS_FULL = {m.upper(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], 1)}

# Full land description, and the partial form used in the 2011-2013 reports
# (section-township-range-meridian, with no quarter-section letter).
ATS_FULL_RE = re.compile(r"^(NE|NW|SE|SW)(\d{1,2})-(\d{1,3})-(\d{1,2})-(W[456])$")
ATS_PARTIAL_RE = re.compile(r"^(\d{1,2})-(\d{1,3})-(\d{1,2})-(W[456])$")


def normalize_ats(text):
    """Return a cleaned land description, or None. Keeps partial codes as-is."""
    if not text:
        return None
    t = re.sub(r"\s+", "", str(text)).upper()
    if ATS_FULL_RE.match(t) or ATS_PARTIAL_RE.match(t):
        return t
    return None


def species_code(text):
    if not text:
        return None
    t = str(text).strip().upper()
    if len(t) == 4 and t.isalpha():
        return t
    return SPECIES_BY_NAME.get(t)


def to_float(x):
    try:
        f = float(str(x).replace(",", "").strip())
        return f
    except (TypeError, ValueError):
        return None


def to_int(x):
    f = to_float(x)
    return int(round(f)) if f is not None else None


def parse_date(value, year):
    """Return ("YYYY-MM-DD", precision) or (None, None).

    Handles every shape these files use: datetime objects, "4/3/2012",
    "25-Apr-16", "2021/05/15", "2022-05-16 00:00:00", and bare month names.
    """
    if value is None or value == "":
        return None, None
    if isinstance(value, (dt.datetime, dt.date)):
        return value.strftime("%Y-%m-%d"), "day"
    s = str(value).strip()

    m = re.match(r"^(\d{1,2})[-/]([A-Za-z]{3})[a-z]*[-/](\d{2,4})$", s)  # 25-Apr-16
    if m:
        day, mon, yr = int(m.group(1)), MONTHS.get(m.group(2).title()), int(m.group(3))
        if mon:
            if yr < 100:
                yr += 2000
            return f"{yr:04d}-{mon:02d}-{day:02d}", "day"

    m = re.match(r"^(\d{1,4})[-/](\d{1,2})[-/](\d{1,4})", s)             # 4/3/2012 or 2021/05/15
    if m:
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 31:
            yr, mon, day = a, b, c
        else:
            mon, day, yr = a, b, c
            if yr < 100:
                yr += 2000
        if 1 <= mon <= 12 and 1 <= day <= 31:
            return f"{yr:04d}-{mon:02d}-{day:02d}", "day"

    mon = MONTHS_FULL.get(s.upper()) or MONTHS.get(s.title()[:3])        # "August"
    if mon:
        return f"{year:04d}-{mon:02d}-01", "month"
    return None, None


def _row(year, source, **kw):
    row = dict(year=year, source=source, official_name="", common_name="", ats=None,
               waterbody_id=None, lat=None, lon=None, species=None, strain="",
               genotype="", length_cm=None, number=None, date=None, date_precision=None)
    row.update(kw)
    return row


# ─────────────────────────────────────────────────────────────────────────
# Spreadsheet readers
# ─────────────────────────────────────────────────────────────────────────
def _clean_header(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().upper().rstrip("*")


def read_csv_year(path, year):
    """2012-2020 CSVs. Column names drift between years, so match loosely."""
    out = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for raw in csv.DictReader(f):
            r = {_clean_header(k): (v or "").strip() for k, v in raw.items() if k}
            sp = species_code(r.get("SPECIES") or r.get("SPECIES CODE"))
            if not sp:
                continue
            number = to_int(r.get("QUANTITY") or r.get("NUMBER STOCKED"))
            if not number or number <= 0:
                continue
            date, precision = parse_date(r.get("SHIPMENT DATE") or r.get("STOCKING DATE"), year)
            # "AVG. LEGTH" is a real typo in the 2015 file.
            length = to_float(next((v for k, v in r.items() if k.startswith(("AVG", "AVERAGE"))), None))
            out.append(_row(
                year, path.name,
                official_name=r.get("OFFICIAL NAME", ""),
                common_name=r.get("COMMON NAME", ""),
                ats=normalize_ats(r.get("ATS")),
                waterbody_id=r.get("WATERBODY ID") or None,
                lat=to_float(r.get("LAT") or r.get("LATITUDE")),
                lon=to_float(r.get("LONG") or r.get("LONGITUDE")),
                species=sp, strain=r.get("STRAIN", ""), genotype=r.get("GENOTYPE", ""),
                length_cm=length, number=number, date=date, date_precision=precision))
    return out


def read_xlsx_year(path, year):
    """2021-2025 workbooks. The data sheet is named for the year."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = wb[str(year)] if str(year) in wb.sheetnames else wb[wb.sheetnames[0]]
        header, out = None, []
        for raw in sheet.iter_rows(values_only=True):
            cells = list(raw)
            if header is None:
                if any(_clean_header(c) == "ATS" for c in cells):
                    header = [_clean_header(c) for c in cells]
                continue
            if not any(c not in (None, "") for c in cells):
                continue
            r = {h: c for h, c in zip(header, cells) if h}
            sp = species_code(r.get("SPECIES"))
            number = to_int(r.get("NUMBER STOCKED") or r.get("QUANTITY"))
            if not sp or not number or number <= 0:
                continue
            date, precision = parse_date(r.get("STOCKING DATE"), year)
            length = to_float(next((v for k, v in r.items() if k.startswith("AVERAGE")), None))
            out.append(_row(
                year, path.name,
                official_name=str(r.get("WATERBODY OFFICIAL NAME") or "").strip(),
                common_name=str(r.get("WATERBODY COMMON NAME") or "").strip(),
                ats=normalize_ats(r.get("ATS")),
                species=sp, strain=str(r.get("STRAIN") or "").strip(),
                genotype=str(r.get("GENOTYPE") or "").strip(),
                length_cm=length, number=number, date=date, date_precision=precision))
        return out
    finally:
        wb.close()


# ─────────────────────────────────────────────────────────────────────────
# PDF readers — three layouts
# ─────────────────────────────────────────────────────────────────────────
# The last page of every report carries a summary and a legend below the data.
# Absorbed as a continuation line it welds pages of footer text onto the final
# lake's name, so it ends the table.
_FOOTER_MARKERS = ("Total Trout Stocked", "Total Walleye", "Total Fish Stocked",
                   "*Strain", "**Gentotype", "**Genotype", "Classification:",
                   "For more information", "Government of Alberta")


def _squash(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


_FOOTER_KEYS = tuple(_squash(m) for m in _FOOTER_MARKERS)


def _is_footer(text):
    """Footer text is split across columns mid-word, so compare without spaces."""
    squashed = _squash(text)
    return any(key in squashed for key in _FOOTER_KEYS)


def _pdf_lines(path):
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").split("\n"):
                line = line.strip()
                if line:
                    yield line


# 2011-2013: "PAYNE LAKE (MAMI LAKE) (10-2-28-W4) May 56,400 RNTR 3N 12"
#
# These rows wrap in an awkward way. The measurement always finishes the line,
# but the name and its bracketed land description can run onto the NEXT line,
# sometimes splitting the code itself mid-number:
#
#     DOLLAR LAKES (EAST DOLLAR LAKE) (8-73-   May 3,000 RNTR 2N 18
#     21-W5)
#
# So: find the measurement at the end of a line, then look for the code in the
# text before it, and if it is not there yet, take it from the following line.
_EARLY_TAIL = re.compile(
    r"(?P<month>[A-Z][a-z]{2,8})\s+(?P<number>[\d,]+)\s+(?P<species>[A-Z]{4})"
    r"(?:\s+(?P<genotype>[0-9][A-Z]{1,3}|A?F?[23]N[A-Z]*))?"
    r"(?:\s+(?P<length>\d{1,3}(?:\.\d)?))?\s*$")
_EARLY_CODE = re.compile(r"\((?P<ats>\d{1,2}-\d{1,3}-\d{1,2}-W[456])\)")


def _early_emit(out, path, year, name_text, tail):
    """Turn one matched name + measurement into a normalized row."""
    joined = re.sub(r"\s*-\s*", "-", name_text)
    code = _EARLY_CODE.search(joined)
    if not code:
        return False
    name = joined[:code.start()].strip(" .")
    common = ""
    paren = re.match(r"^(?P<main>.*?)\s*\((?P<alt>[^()]+)\)\s*$", name)
    if paren:
        name, common = paren.group("main").strip(), paren.group("alt").strip()
    sp = species_code(tail.group("species"))
    number = to_int(tail.group("number"))
    if not sp or not number or number <= 0:
        return False
    date, precision = parse_date(tail.group("month"), year)
    out.append(_row(
        year, path.name, official_name=name, common_name=common,
        ats=normalize_ats(code.group("ats")), species=sp,
        genotype=tail.group("genotype") or "",
        length_cm=to_float(tail.group("length")),
        number=number, date=date, date_precision=precision))
    return True


def read_pdf_early(path, year):
    out, pending, dropped = [], None, 0
    for line in _pdf_lines(path):
        if line.startswith(("Stocking Report", "Location ", "Sport Fishing Zone")):
            continue
        tail = _EARLY_TAIL.search(line)
        if tail:
            if pending:                       # previous row never found its code
                dropped += 1
            name_text = line[:tail.start()].strip()
            if not _early_emit(out, path, year, name_text, tail):
                pending = (name_text, tail)   # code must be on the next line
            else:
                pending = None
        elif pending:
            name_text, prev_tail = pending
            if _early_emit(out, path, year, name_text + " " + line, prev_tail):
                pending = None
            else:
                dropped += 1
                pending = None
    if pending:
        dropped += 1
    if dropped:
        print(f"  note: {path.name} — {dropped} row(s) had no readable land description")
    return out


# 2015-2019: "EDSON  FAIRFAX LAKE  RNTR  TLTLS  AF3N  10,000  19.1  25-May-15"
#
# District first, then the waterbody name, and no land description anywhere in
# the document. Reading this by regex fails because districts are multi-word
# ("ROCKY MOUNTAIN HOUSE", "MEDICINE HAT", "LAC LA BICHE") and splitting on the
# first space welds the tail of the district onto the lake name — that is how
# "TWIN LAKE" in Rocky Mountain House became "MOUNTAIN HOUSETWIN LAKE".
# The columns are at fixed positions, so use those instead of guessing.
_DISTRICT_COLUMNS = {
    "district": (30, 179),
    "name":     (179, 415),
    "species":  (415, 510),
    "strain":   (510, 625),
    "genotype": (625, 740),
    "number":   (740, 852),
    "length":   (852, 934),
    "date":     (934, 9999),
}


def _column_of(x0, columns):
    for name, (lo, hi) in columns.items():
        if lo <= x0 < hi:
            return name
    return None


def _columns_from_chars(chars, columns, gap=1.2):
    """Split a line of characters into columns by x position.

    Word-level extraction is not safe here: when the district ends flush
    against the lake name the PDF yields a single fused word ("HOUSECAMP" for
    Rocky Mountain House + Camp 9 Pond), which then lands entirely in one
    column and truncates the other. Characters carry their own x, so splitting
    at the column boundary recovers both sides.
    """
    out = {name: "" for name in columns}
    last_x1 = {name: None for name in columns}
    for ch in sorted(chars, key=lambda c: c["x0"]):
        col = _column_of(ch["x0"], columns)
        if not col:
            continue
        prev = last_x1[col]
        if prev is not None and ch["x0"] - prev > gap and not out[col].endswith(" "):
            out[col] += " "
        out[col] += ch["text"]
        last_x1[col] = ch["x1"]
    return {k: re.sub(r"\s+", " ", v).strip() for k, v in out.items()}


def read_pdf_district(path, year):
    import pdfplumber
    out = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            buckets = {}
            for ch in page.chars:
                buckets.setdefault(round(ch["top"] / 2) * 2, []).append(ch)
            pending = None                      # a row still waiting for its date
            for top in sorted(buckets):
                joined = _columns_from_chars(buckets[top], _DISTRICT_COLUMNS)

                # A stray line carrying only the date belongs to the row above.
                if pending is not None and joined["date"] and not joined["species"]:
                    pending["date"], pending["date_precision"] = parse_date(joined["date"], year)
                    out.append(pending)
                    pending = None
                    continue
                if pending is not None:
                    out.append(pending)         # no date ever arrived; keep the row
                    pending = None

                sp = species_code(joined["species"])
                number = to_int(joined["number"])
                if not sp or not number or number <= 0 or not joined["name"]:
                    continue
                date, precision = parse_date(joined["date"], year)
                row = _row(
                    year, path.name, official_name=joined["name"],
                    species=sp, strain=joined["strain"], genotype=joined["genotype"],
                    length_cm=to_float(joined["length"]), number=number,
                    date=date, date_precision=precision)
                row["district"] = joined["district"]
                if date:
                    out.append(row)
                else:
                    pending = row
            if pending is not None:
                out.append(pending)
    return out


# 2020-2026: full columns including the land description.
#
# These cannot be read line by line. When a long lake name and a long strain
# both wrap, the continuation line carries a fragment of each, side by side:
#
#     Wildhorse Lakes Upper Wildhorse  SW31-49-26-W5  BKTR  Beitty Resort ...
#     L ake
#
# Read as text that yields "Wildhorse Lake) Lodge/Kamloops Wildhorse Lakes
# (Upper" — a name that belongs to no lake. Read by column, each fragment goes
# back where it came from. Column positions move every year, so they are
# measured from each page rather than hardcoded.
_SPECIES_TOKEN = re.compile(r"^(RNTR|BKTR|BNTR|TGTR|CTTR|WSCT|WALL|ARGR|LKTR|SPLK|GLTR|NRPK)$")
_GENOTYPE_TOKEN = re.compile(r"^A?F?[23]N[A-Z]*$")
_DATE_TOKEN = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$")
_ATS_TOKEN = re.compile(r"^(NE|NW|SE|SW)\d{1,2}-\d{1,3}-\d{1,2}-W[456]$")


def _median(values):
    values = sorted(values)
    return values[len(values) // 2] if values else None


def _modern_columns(page):
    """Measure this page's column boundaries from the tokens that identify them."""
    anchors = {"ats": [], "species": [], "genotype": [], "date": []}
    for w in page.extract_words():
        t = w["text"]
        if _ATS_TOKEN.match(t):
            anchors["ats"].append(w["x0"])
        elif _SPECIES_TOKEN.match(t):
            anchors["species"].append(w["x0"])
        elif _GENOTYPE_TOKEN.match(t):
            anchors["genotype"].append(w["x0"])
        elif _DATE_TOKEN.match(t):
            anchors["date"].append(w["x0"])
    ats_x, sp_x = _median(anchors["ats"]), _median(anchors["species"])
    gt_x, dt_x = _median(anchors["genotype"]), _median(anchors["date"])
    if None in (ats_x, sp_x, gt_x, dt_x):
        return None
    return {
        "name":     (0, ats_x - 6),
        "ats":      (ats_x - 6, sp_x - 6),
        "species":  (sp_x - 6, sp_x + 34),
        "strain":   (sp_x + 34, gt_x - 6),
        "genotype": (gt_x - 6, gt_x + 30),
        "numbers":  (gt_x + 30, dt_x - 6),
        "date":     (dt_x - 6, 9999),
    }


def _name_split(pages, lo, hi):
    """Find where the official-name column ends and the common-name one begins.

    Some years print two name columns with no header on the data pages. Read as
    one column they interleave whenever both wrap, turning High Level Community
    Pond / High Level Town Park Pond into "High Level Community High Level Town
    Park Pond Pond". A column boundary is a vertical strip no character ever
    crosses, with text on both sides, so look for the widest such gap.
    """
    lo, hi = int(lo), int(hi)
    if hi <= lo:
        return None
    coverage = [0] * (hi - lo + 1)
    for page in pages:
        for ch in page.chars:
            a, b = int(max(ch["x0"], lo)), int(min(ch["x1"], hi))
            for x in range(a, b + 1):
                coverage[x - lo] += 1
    total = sum(coverage)
    if not total:
        return None

    best, run_start = None, None
    for i, count in enumerate(coverage + [1]):        # sentinel closes a final run
        if count == 0:
            if run_start is None:
                run_start = i
            continue
        if run_start is not None:
            width = i - run_start
            left, right = sum(coverage[:run_start]), sum(coverage[i:])
            # A real boundary has substantial text on both sides of it.
            if width >= 6 and left > total * 0.15 and right > total * 0.05:
                if best is None or width > best[0]:
                    best = (width, run_start + width // 2 + lo)
            run_start = None
    return best[1] if best else None


def read_pdf_modern(path, year):
    import pdfplumber
    out = []
    with pdfplumber.open(path) as pdf:
        # Measure the name-column split once, across the whole report: a single
        # page may hold too few common names to see the second column.
        probe = next((_modern_columns(pg) for pg in pdf.pages if _modern_columns(pg)), None)
        doc_split = (_name_split(pdf.pages, probe["name"][0], probe["name"][1])
                     if probe else None)
        for page in pdf.pages:
            columns = _modern_columns(page)
            if not columns:
                continue
            split = doc_split if doc_split and columns["name"][0] < doc_split < columns["name"][1] else None
            if split:
                columns = dict(columns)
                columns["name"] = (columns["name"][0], split)
                columns["common"] = (split, columns["ats"][0])
            buckets = {}
            for ch in page.chars:
                buckets.setdefault(round(ch["top"] / 2) * 2, []).append(ch)
            last = None                 # the row a continuation line belongs to
            for top in sorted(buckets):
                cols = _columns_from_chars(buckets[top], columns)
                sp = species_code(cols["species"])
                code = normalize_ats(cols["ats"])

                if _is_footer(" ".join(cols.values())):
                    last = None            # the data table has ended
                    continue

                if not sp or not code:
                    # A true continuation carries only leftover name and strain
                    # text. If the line also has a date or a count it is a data
                    # row we failed to parse, and absorbing it would weld two
                    # different lakes into one name.
                    looks_like_data = bool(cols["date"] or cols["numbers"].strip())
                    has_text = cols["name"] or cols.get("common") or cols["strain"]
                    if last is not None and not looks_like_data and has_text:
                        if cols["name"]:
                            last["_name"] = (last["_name"] + " " + cols["name"]).strip()
                        if cols.get("common"):
                            last["_common"] = (last.get("_common", "") + " " + cols["common"]).strip()
                        if cols["strain"]:
                            last["strain"] = (last["strain"] + " " + cols["strain"]).strip()
                    continue

                # The strain/genotype boundary drifts by a few points between
                # years, which can slice "AF2N" into "...A" and "F2N". Rejoin
                # the two columns and take the genotype off the end.
                merged = f"{cols['strain']} {cols['genotype']}".strip()
                gt = re.search(r"(A?F?[23]N[A-Z]*)\s*$", merged)
                if gt:
                    cols["genotype"] = gt.group(1)
                    cols["strain"] = merged[:gt.start()].strip()

                nums = re.findall(r"[\d,]+(?:\.\d+)?", cols["numbers"])
                if not nums:
                    continue
                number = to_int(nums[-1])
                length = to_float(nums[0]) if len(nums) > 1 else None
                if not number or number <= 0:
                    continue
                date, precision = parse_date(cols["date"], year)
                row = _row(year, path.name, ats=code, species=sp,
                           strain=cols["strain"], genotype=cols["genotype"],
                           length_cm=length, number=number,
                           date=date, date_precision=precision)
                row["_name"] = cols["name"]
                row["_common"] = cols.get("common", "")
                out.append(row)
                last = row

    # Names arrive as "Wildhorse Lakes Upper Wildhorse Lake" — the report drops
    # the brackets its own spreadsheets use. Keep the whole thing as the name.
    for row in out:
        name = re.sub(r"\s+", " ", row.pop("_name", "")).strip()
        common = re.sub(r"\s+", " ", row.pop("_common", "") or "").strip()
        paren = re.match(r"^(?P<main>.*?)\s*\((?P<alt>[^()]+)\)\s*$", name)
        if not common and paren:
            name, common = paren.group("main").strip(), paren.group("alt").strip()
        row["official_name"] = name
        row["common_name"] = common
    return out


# ─────────────────────────────────────────────────────────────────────────
# Which file to read for each year
# ─────────────────────────────────────────────────────────────────────────
YEAR_SOURCES = {
    2011: ("pdf_early",    "aep-alberta-fish-stocking-report-2011.pdf"),
    2012: ("csv",          "fish-stocking-report-2012.csv"),
    2013: ("csv",          "fish-stocking-report-2013.csv"),
    2014: ("csv",          "fish-stocking-report-2014.csv"),
    2015: ("pdf_district", "aep-alberta-fish-stocking-report-2015.pdf"),
    2016: ("csv",          "fish-stocking-report-2016.csv"),
    2017: ("csv",          "fish-stocking-report-2017.csv"),
    2018: ("csv",          "fish-stocking-report-2018.csv"),
    2019: ("csv",          "fish-stocking-report-2019.csv"),
    2020: ("csv",          "fish-stocking-report-2020.csv"),
    2021: ("xlsx",         "fish-stocking-report-2021.xlsx"),
    2022: ("xlsx",         "fish-stocking-report-2022.xlsx"),
    2023: ("xlsx",         "fish-stocking-report-2023.xlsx"),
    2024: ("xlsx",         "fish-stocking-report-2024.xlsx"),
    2025: ("pdf_modern",   "epa-alberta-fish-stocking-report-2025.pdf"),
    2026: ("pdf_modern",   "epa-alberta-fish-stocking-report-2026.pdf"),
}

# The 2026 season is still in progress; Alberta updates the report again in October.
PROVISIONAL_YEARS = {2026}

READERS = {
    "csv": read_csv_year,
    "xlsx": read_xlsx_year,
    "pdf_early": read_pdf_early,
    "pdf_district": read_pdf_district,
    "pdf_modern": read_pdf_modern,
}


def read_year(year):
    kind, filename = YEAR_SOURCES[year]
    return READERS[kind](RAW_DIR / filename, year)


def read_all_years(years=None):
    return {y: read_year(y) for y in (years or sorted(YEAR_SOURCES))}


if __name__ == "__main__":
    print(f"{'year':>5} {'rows':>6} {'trout':>6} {'lakes':>6} {'id':>4} {'coord':>6} {'ats':>5} {'date':>6}  source")
    for year in sorted(YEAR_SOURCES):
        rows = read_year(year)
        trout = [r for r in rows if r["species"] in TROUT_SPECIES]
        keys = {r["waterbody_id"] or r["ats"] or r["official_name"] for r in trout}
        print(f"{year:>5} {len(rows):>6} {len(trout):>6} {len(keys):>6} "
              f"{sum(1 for r in trout if r['waterbody_id']):>4} "
              f"{sum(1 for r in trout if r['lat'] is not None):>6} "
              f"{sum(1 for r in trout if r['ats']):>5} "
              f"{sum(1 for r in trout if r['date']):>6}  {YEAR_SOURCES[year][1]}")
