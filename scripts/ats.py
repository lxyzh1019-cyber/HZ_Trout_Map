"""
ats.py — Alberta Township System (ATS) code → latitude/longitude.

An ATS code such as ``SW4-36-8-W5`` names a quarter-section on the Dominion
Land Survey grid: quarter-section-township-range-meridian. This module returns
the approximate centre of that quarter-section.

  - Meridians: W4 = 110°W, W5 = 114°W, W6 = 118°W
  - Townships are numbered north from 49°N (the US border)
  - Ranges are numbered west from each meridian
  - Sections are a 6x6 grid of 1-mile squares, numbered in boustrophedon
    ("snake") order starting at the SOUTH-EAST corner
  - Quarters are the NE/NW/SE/SW corners of each section

Accuracy
--------
Validated against 256 hand-verified lake coordinates in
``profiles/mywildalberta_profiles.csv``: median error 0.53 km, and 252 of 256
within 1.5 km. A quarter-section is 0.8 km across, so that is about as close as
a grid centroid can get to a point inside it.

History
-------
The previous implementation (``extract_alberta_trout_v2.ats_to_latlng``) had a
median error of 6.08 km because of three bugs, all fixed here:

  1. **Mirrored section columns.** The column index was computed correctly with
     column 0 as the WEST column, but was then used as an offset measured west
     from the meridian — which treats it as an offset from the EAST edge. Every
     lake in the west column of a township (sections 6, 7, 18, 19, 30, 31) was
     plotted a full 6 miles from where it belongs.
  2. **Road allowances ignored.** Alberta's survey inserts a one-chain (66 ft)
     road allowance on every mile line north-south, and on every second mile
     line east-west. A range is therefore 6.075 miles wide and a township
     6.0375 miles tall, not 6.0. Over 25 ranges that error reaches 3 km.
  3. **Longitude scaled at the wrong latitude.** Ranges are laid out along base
     lines every 4 townships (24 miles) and the range lines run true north from
     there, so a range's width in degrees of longitude is set at its base line,
     not at the latitude of the point itself.
"""

import math
import re

MERIDIAN_LON = {"W4": -110.0, "W5": -114.0, "W6": -118.0}

KM_PER_MILE = 1.609344
KM_PER_DEG_LAT = 111.2

# One chain = 66 ft. Road allowances run on every mile line north-south
# (6 per range) and every second mile line east-west (3 per township).
_CHAIN_MI = 66 / 5280
RANGE_WIDTH_MI = 6 + 6 * _CHAIN_MI     # 6.075
TOWNSHIP_HEIGHT_MI = 6 + 3 * _CHAIN_MI  # 6.0375

# Fraction of a section, measured from its SOUTH-WEST corner:
# (east-ward fraction, north-ward fraction).
QUARTER_OFFSETS = {
    "NE": (0.75, 0.75),
    "NW": (0.25, 0.75),
    "SE": (0.75, 0.25),
    "SW": (0.25, 0.25),
}

ATS_RE = re.compile(r"^(NE|NW|SE|SW)(\d+)-(\d+)-(\d+)-(W[456])$")
# The 2011-2013 reports print the land description without its quarter-section
# letter. That still pins the lake to a one-mile section, so use its centre.
ATS_PARTIAL_RE = re.compile(r"^(\d+)-(\d+)-(\d+)-(W[456])$")

# Base lines are surveyed every 4 townships; range lines run true north
# from the base line below (townships 1-2 of each block) or south from the
# one above (townships 3-4).
TOWNSHIPS_PER_BLOCK = 4


def section_grid_xy(section):
    """Return (x, y) of a section within its township.

    x is the column with 0 = WEST edge, 5 = EAST edge.
    y is the row with 0 = SOUTH edge, 5 = NORTH edge.

    Section 1 sits in the south-east corner and numbering snakes west along
    row 0, east along row 1, and so on.
    """
    s = section - 1
    row = s // 6
    pos_in_row = s % 6
    x = 5 - pos_in_row if row % 2 == 0 else pos_in_row
    return x, row


def _base_line_latitude(township):
    """Latitude of the base line governing this township's range widths."""
    block = (township - 1) // TOWNSHIPS_PER_BLOCK
    from_below = ((township - 1) % TOWNSHIPS_PER_BLOCK) < 2
    base_township = block * TOWNSHIPS_PER_BLOCK + (0 if from_below else TOWNSHIPS_PER_BLOCK)
    miles_north = base_township * TOWNSHIP_HEIGHT_MI
    return 49.0 + miles_north * KM_PER_MILE / KM_PER_DEG_LAT


def ats_to_latlng(ats):
    """Convert an ATS code to (lat, lon), or (None, None) if unparseable.

    Accepts the full form (NE10-2-28-W4) and the partial form printed by the
    2011-2013 reports (10-2-28-W4), which names the section but not the
    quarter. A section is one mile across, so its centre is within about
    800 m of wherever in it the lake actually sits.
    """
    text = (ats or "").strip().upper()
    m = ATS_RE.match(text)
    if m:
        quarter, section, township, rng, meridian = m.groups()
        qx, qy = QUARTER_OFFSETS[quarter]
    else:
        m = ATS_PARTIAL_RE.match(text)
        if not m:
            return None, None
        section, township, rng, meridian = m.groups()
        qx, qy = 0.5, 0.5                      # centre of the section
    section, township, rng = int(section), int(township), int(rng)
    if not 1 <= section <= 36:
        return None, None

    x, y = section_grid_xy(section)

    # Latitude: stack whole townships north from 49°N, then the section row
    # and quarter within this township.
    miles_north = (township - 1) * TOWNSHIP_HEIGHT_MI + (y + qy) * (TOWNSHIP_HEIGHT_MI / 6)
    lat = 49.0 + miles_north * KM_PER_MILE / KM_PER_DEG_LAT

    # Longitude: walk west from the meridian. Within the range, measure west
    # from its east edge, so column 5 (east) is closest to the meridian.
    miles_from_range_east_edge = (5 - x + (1 - qx)) * (RANGE_WIDTH_MI / 6)
    miles_west = (rng - 1) * RANGE_WIDTH_MI + miles_from_range_east_edge
    km_per_deg_lon = KM_PER_DEG_LAT * math.cos(math.radians(_base_line_latitude(township)))
    lon = MERIDIAN_LON[meridian] - miles_west * KM_PER_MILE / km_per_deg_lon

    return round(lat, 5), round(lon, 5)


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in kilometres."""
    radius = 6371.0
    to_rad = math.radians
    dlat = to_rad(lat2 - lat1)
    dlon = to_rad(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(to_rad(lat1)) * math.cos(to_rad(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * radius * math.asin(math.sqrt(a))
