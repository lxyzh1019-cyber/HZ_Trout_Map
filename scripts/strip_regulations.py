"""Cut the sportfishing regulations down to the pages that carry regulations.

Why this exists: the published guide is 112 pages and 25 MB, and almost all of
that weight is full-page photographs — watershed maps and advertisements. The
map repository is cloned by anyone who wants to rebuild the data, and one
tourism advert should not cost them 25 MB forever.

What is dropped is only ever a page with no regulatory text on it. Every page
kept is kept because something on it is parsed or is needed to audit the parse:

    definitions          the meaning of "Bait ban" and the other table terms
    stocked lakes list   the put-and-take waterbodies, which govern most of the
                         lakes this map cares about
    possession limits    the province-wide fallback the tables refer to
    watershed defaults   what applies when a waterbody is not listed
    regulation tables    the site-specific rows, lakes and rivers both

Because this removes pages from a legal document, the result records where it
came from: the source file name, its SHA-256, its page count, and the original
page number of every page kept. Anyone can check the stripped copy against the
published guide, and re-running this script on the same input must reproduce it.

Usage:
    python3 strip_regulations.py <source.pdf> <destination.pdf>
"""

import hashlib
import json
import re
import sys
from pathlib import Path

import pdfplumber
from pdfplumber.page import Page
from pypdf import PdfReader, PdfWriter

ATS = r"(?:NE|NW|SE|SW)?\s*\d{1,2}-\d{1,3}-\d{1,2}-W\d"


def classify(pdf, page_number):
    """Why a page is worth keeping, or an empty list if it is not.

    The regulation tables are typeset sideways, so they have to be read with the
    page rotated; everything else reads normally. See regulations.py for the
    full story on that.
    """
    page = pdf.pages[page_number - 1]
    if not page.chars:
        return []                      # a photograph: a map or an advertisement

    reasons = []
    flat = page.extract_text() or ""

    if re.search(r"Bait\s+–\s+An attractant", flat):
        reasons.append("definitions")
    if re.search(r"managed as put", flat) or (
        re.search(r"Watershed Unit\s+(ES|NB|PP)[1-4]", flat)
        and len(re.findall(ATS, flat)) > 20
    ):
        reasons.append("stocked-list")
    if re.search(r"General Sportfishing Restrictions", flat):
        reasons.append("possession-limits")
    if re.search(r"(ES[1-4]|NB[1-4]|PP[12]) WATERSHED UNIT REGULATIONS", flat):
        reasons.append("watershed-defaults")

    page.page_obj.rotate = 90
    turned = Page(pdf, page.page_obj, page_number=page_number, initial_doctop=0)
    sideways = turned.extract_text() or ""
    if re.search(r"Waterbody\s+Waterbody Detail\s+Season", sideways):
        reasons.append("regulation-table")
    return reasons


def strip(source: Path, destination: Path):
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    with pdfplumber.open(str(source)) as pdf:
        total = len(pdf.pages)
        kept = [(n, classify(pdf, n)) for n in range(1, total + 1)]
    kept = [(n, why) for n, why in kept if why]

    reader = PdfReader(str(source))
    writer = PdfWriter()
    for number, _ in kept:
        writer.add_page(reader.pages[number - 1])
    writer.add_metadata({
        "/Title": "2026 Alberta Guide to Sportfishing Regulations (regulation pages only)",
        "/Subject": f"Pages carrying regulations, extracted from {source.name}",
    })
    with destination.open("wb") as handle:
        writer.write(handle)

    provenance = {
        "source_file": source.name,
        "source_sha256": digest,
        "source_pages": total,
        "kept_pages": len(kept),
        "pages": [{"source_page": n, "kept_for": why} for n, why in kept],
    }
    (destination.with_suffix(".provenance.json")).write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return provenance


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    record = strip(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"kept {record['kept_pages']} of {record['source_pages']} pages")
    counts = {}
    for page in record["pages"]:
        for why in page["kept_for"]:
            counts[why] = counts.get(why, 0) + 1
    for why, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>3}  {why}")
