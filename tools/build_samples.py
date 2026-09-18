"""build_samples.py - builds the sample projects under engine/tests/sample_projects/.

Usage: python tools/build_samples.py [A_minimal F_capital F_capital_known D_dosing]
The generated input files are checked in, so the tests never depend on this tool; run it only
when a sample has to change. Everything a sample contains is written down in this file, so a
reviewer can read what the engine is tested against. Samples are invented; none is real.
"""
import io
import os
import sys
import tarfile
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, "engine", "tests", "sample_projects")
FOLDERS = {"canon": "1_Methodology", "package": "2_Model_Package", "doc": "3_Model_Documentation"}


# ------------------------------------------------------------------ writers
def write_bytes(sample, corner, name, data):
    folder = os.path.join(SAMPLES, sample, "Inputs", FOLDERS[corner])
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name), "wb") as handle:
        handle.write(data if isinstance(data, bytes) else data.encode("utf-8"))


def tarball(package_name, files):
    """A .tar.gz with one top folder, fixed times and owners, so the same content gives the same bytes."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for path in sorted(files):
            data = files[path] if isinstance(files[path], bytes) else files[path].encode("utf-8")
            member = tarfile.TarInfo("%s/%s" % (package_name, path))
            member.size, member.mtime, member.mode = len(data), 1767225600, 0o644
            archive.addfile(member, io.BytesIO(data))
    import gzip
    packed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=packed, mtime=0) as handle:
        handle.write(raw.getvalue())
    return packed.getvalue()


def r_data(objects, single=False):
    """Stored R data written without R, by the writer of the `rdata` package (fixture route c)."""
    import rdata
    path = os.path.join(ROOT, "tmp_rdata.bin")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if single:
            rdata.write_rds(path, objects)
        else:
            rdata.write_rda(path, objects)
    with open(path, "rb") as handle:
        data = handle.read()
    os.remove(path)
    return data


def docx_file(parts):
    """parts: ("h", level, text) | ("p", text) | ("li", text) | ("table", caption, rows) | ("eq", omml xml)
    | ("image", caption)"""
    import docx
    from docx.oxml import parse_xml
    document = docx.Document()
    for part in parts:
        if part[0] == "h":
            document.add_heading(part[2], level=part[1])
        elif part[0] == "p":
            document.add_paragraph(part[1])
        elif part[0] == "li":
            document.add_paragraph(part[1], style="List Bullet")
        elif part[0] == "table":
            document.add_paragraph(part[1], style="Caption")
            table = document.add_table(rows=len(part[2]), cols=len(part[2][0]))
            table.style = "Table Grid"
            for row, cells in zip(table.rows, part[2]):
                for cell, text in zip(row.cells, cells):
                    cell.text = text
        elif part[0] == "eq":
            paragraph = document.add_paragraph()
            paragraph._p.append(parse_xml(part[1]))
        elif part[0] == "image":
            document.add_picture(io.BytesIO(tiny_png()))
            document.add_paragraph(part[1], style="Caption")
    raw = io.BytesIO()
    document.save(raw)
    return raw.getvalue()


def pdf_file(parts):
    """parts as for docx_file; headings are bold and larger, tables are drawn with a grid."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    styles, story, raw = getSampleStyleSheet(), [], io.BytesIO()
    for part in parts:
        if part[0] == "h":
            story.append(Paragraph(part[2], styles["Heading%d" % min(3, part[1])]))
        elif part[0] in ("p", "li"):
            story.append(Paragraph(part[1], styles["BodyText"]))
        elif part[0] == "table":
            story.append(Paragraph(part[1], styles["BodyText"]))
            story.append(Table(part[2], style=TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)])))
        story.append(Spacer(1, 8))
    SimpleDocTemplate(raw, pagesize=A4, invariant=1).build(story)
    return raw.getvalue()


def tiny_png():
    import base64
    return base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def omml(inner):
    return ('<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">%s</m:oMath>' % inner)


def run(text):
    return "<m:r><m:t>%s</m:t></m:r>" % text


# ------------------------------------------------------------------ sample A_minimal (neutral flavour)
A_METHODOLOGY = """<?xml version="1.0" encoding="UTF-8"?>
<document>
 <title>Parcel pricing method</title>
 <section><title>1. Purpose and scope</title>
  <p>This method sets out how the price of a parcel is determined from its size, its weight and its destination zone.</p>
  <p>It applies to every parcel handed in at a counter. Pallets and letters are outside its scope.</p>
  <p>The method is reviewed once a year by the pricing committee.</p>
 </section>
 <section><title>2. Definitions</title>
  <list>
   <item>Actual weight (AW) is the weight of the parcel in kilograms as shown by the scale.</item>
   <item>Dimensional weight (DW) is a weight derived from the volume of the parcel.</item>
   <item>Chargeable weight (CW) is the weight on which the price is based.</item>
   <item>The zone is the destination area of the parcel: Local, National or Abroad.</item>
  </list>
 </section>
 <section><title>3. Weights</title>
  <section><title>3.1 Dimensional weight</title>
   <p>The dimensional weight is obtained from the length L, the width W and the height H of the parcel, measured in centimetres.</p>
   <equation><math xmlns="http://www.w3.org/1998/Math/MathML"><mi>DW</mi><mo>=</mo><mfrac><mrow><mi>L</mi><mo>&#xD7;</mo><mi>W</mi><mo>&#xD7;</mo><mi>H</mi></mrow><mn>5000</mn></mfrac></math></equation>
   <p>The divisor of 5000 is fixed and is not varied by zone.</p>
  </section>
  <section><title>3.2 Chargeable weight</title>
   <p>The chargeable weight is the larger of the actual weight and the dimensional weight: CW = max(AW, DW).</p>
   <p>The chargeable weight is never taken below 0.5 kilograms.</p>
   <p>Weights are not rounded before the price is calculated.</p>
  </section>
 </section>
 <section><title>4. Price</title>
  <section><title>4.1 Zone rates</title>
   <p>Each zone has a base rate and a rate per kilogram, as set out in Table 1.</p>
   <table><caption>Table 1. Rates by zone</caption>
    <tr><th>Zone</th><th>Base rate</th><th>Rate per kg</th></tr>
    <tr><td>Local</td><td>3.20</td><td>0.85</td></tr>
    <tr><td>National</td><td>4.90</td><td>1.10</td></tr>
    <tr><td>Abroad</td><td>9.50</td><td>2.75</td></tr>
   </table>
   <p>Rates are stated in the currency of the counter and exclude tax.</p>
  </section>
  <section><title>4.2 Price before surcharge</title>
   <p>The price before surcharge is the base rate plus the rate per kilogram times the chargeable weight: P = B + R * CW.</p>
   <p>B and R are taken from Table 1 for the zone of the parcel.</p>
  </section>
  <section><title>4.3 Fuel surcharge</title>
   <p>A fuel surcharge of 12.5% is added to the price before surcharge: S = P * (1 + 0.125).</p>
   <p>The surcharge rate is set by the pricing committee and is the same for all zones.</p>
  </section>
  <section><title>4.4 Volume discount</title>
   <p>A customer who hands in n parcels at once receives a discount rate of 1% per parcel, capped at 20%: D = min(0.2, 0.01 * n).</p>
   <p>The discount is applied to the price after surcharge.</p>
   <figure><img src="discount_curve.png" alt="Discount rate against number of parcels"/><caption>Figure 1. Discount rate by number of parcels</caption></figure>
  </section>
  <section><title>4.5 Minimum price</title>
   <p>The final price is never below 4.50, whatever the zone and the discount.</p>
   <p>Final prices are rounded to 2 decimals.</p>
  </section>
 </section>
 <section><title>5. Governance</title>
  <p>Changes to Table 1 are approved by the pricing committee and recorded in the change log.</p>
  <p>Questions about this method are answered by the pricing office.</p>
 </section>
</document>
"""

A_PACKAGE = {
    "DESCRIPTION": "Package: parcelcost\nTitle: Parcel Pricing\nVersion: 1.2.0\nDescription: Prices parcels by zone\n    and chargeable weight.\nLicense: MIT\nEncoding: UTF-8\n",
    "NAMESPACE": "export(dim_weight)\nexport(chargeable_weight)\nexport(parcel_price)\nexport(volume_discount)\n",
    "R/weights.R": """#' Dimensional weight
#'
#' Weight derived from the volume of a parcel: \\deqn{DW = \\frac{L \\cdot W \\cdot H}{5000}}
#' @param l length in centimetres
#' @param w width in centimetres
#' @param h height in centimetres
#' @param divisor the fixed divisor, 5000
#' @export
dim_weight <- function(l, w, h, divisor = 5000) {
  stopifnot(is.numeric(l), is.numeric(w), is.numeric(h))
  l * w * h / divisor
}

#' Chargeable weight
#'
#' The larger of actual weight and dimensional weight, never below 0.5 kilograms.
#' @param aw actual weight in kilograms
#' @param dw dimensional weight in kilograms
#' @export
chargeable_weight <- function(aw, dw) {
  cw <- pmax(aw, dw)
  pmax(cw, 0.5)
}
""",
    "R/price.R": """#' Price of a parcel
#'
#' Base rate plus rate per kilogram times chargeable weight, with the fuel surcharge of 12.5%,
#' the volume discount and the minimum price of 4.50.
#' @param zone destination zone: Local, National or Abroad
#' @param cw chargeable weight in kilograms
#' @param n number of parcels handed in at once
#' @export
parcel_price <- function(zone, cw, n = 1) {
  if (!zone %in% zone_rates$zone) stop("unknown zone")
  base <- zone_rates[zone_rates$zone == zone, "base_rate"]
  rate <- zone_rates[zone_rates$zone == zone, "rate_per_kg"]
  price <- base + rate * cw
  with_fuel <- price * (1 + 0.125)
  discounted <- with_fuel * (1 - volume_discount(n))
  round(pmax(discounted, 4.50), 2)
}

#' Volume discount
#'
#' Discount rate of 1% per parcel, capped at 20%.
#' @param n number of parcels handed in at once
#' @export
volume_discount <- function(n) {
  pmin(0.2, 0.01 * n)
}

# Helper used when printing a price list.
format_price <- function(x) {
  paste0(format(x, nsmall = 2), " per parcel")
}
""",
    "R/data.R": """#' Rates by zone
#'
#' Base rate and rate per kilogram for each destination zone.
#' @format A data frame with 3 rows and 3 columns:
#' \\describe{
#'   \\item{zone}{destination zone}
#'   \\item{base_rate}{base rate per parcel}
#'   \\item{rate_per_kg}{rate per kilogram of chargeable weight}
#' }
"zone_rates"
""",
    "man/dim_weight.Rd": """% Generated by roxygen2: do not edit by hand
% Please edit documentation in R/weights.R
\\name{dim_weight}
\\alias{dim_weight}
\\title{Dimensional weight}
\\usage{
dim_weight(l, w, h, divisor = 5000)
}
\\arguments{
\\item{l}{length in centimetres}
\\item{w}{width in centimetres}
\\item{h}{height in centimetres}
\\item{divisor}{the fixed divisor, 5000}
}
\\description{
Weight derived from the volume of a parcel.
}
""",
    "man/chargeable_weight.Rd": """% Generated by roxygen2: do not edit by hand
% Please edit documentation in R/weights.R
\\name{chargeable_weight}
\\alias{chargeable_weight}
\\title{Chargeable weight}
\\usage{
chargeable_weight(aw, dw)
}
\\arguments{
\\item{aw}{actual weight in kilograms}
\\item{dw}{dimensional weight in kilograms}
}
""",
    "man/parcel_price.Rd": """% Generated by roxygen2: do not edit by hand
% Please edit documentation in R/price.R
\\name{parcel_price}
\\alias{parcel_price}
\\title{Price of a parcel}
\\usage{
parcel_price(zone, cw, n = 1)
}
\\arguments{
\\item{zone}{destination zone: Local, National or Abroad}
\\item{cw}{chargeable weight in kilograms}
\\item{n}{number of parcels handed in at once}
}
""",
    "man/volume_discount.Rd": """% Generated by roxygen2: do not edit by hand
% Please edit documentation in R/price.R
\\name{volume_discount}
\\alias{volume_discount}
\\title{Volume discount}
\\usage{
volume_discount(n)
}
\\arguments{
\\item{n}{number of parcels handed in at once}
}
""",
    "tests/testthat.R": "library(testthat)\nlibrary(parcelcost)\ntest_check(\"parcelcost\")\n",
    "tests/testthat/test-price.R": """test_that("dimensional weight follows the divisor", {
  expect_equal(dim_weight(50, 40, 30), 12)
})

test_that("the minimum price holds", {
  expect_equal(parcel_price("Local", 0.5), 4.50)
})
""",
}

A_DOCUMENTATION = [
    ("h", 1, "1 Overview"),
    ("p", "This document describes how the parcelcost package implements the parcel pricing method."),
    ("p", "The package is maintained by the pricing office and released once a year."),
    ("h", 1, "2 Weights"),
    ("p", "The function dim_weight derives the dimensional weight from length, width and height with the fixed divisor of 5000."),
    ("p", "The function chargeable_weight returns the larger of actual weight and dimensional weight and never returns less than 0.5 kilograms."),
    ("h", 1, "3 Price"),
    ("p", "The function parcel_price looks up the base rate and the rate per kilogram of the zone in the table zone_rates."),
    ("table", "Table A. Rates held in the package", [["Zone", "Base rate", "Rate per kg"], ["Local", "3.20", "0.85"],
                                                     ["National", "4.90", "1.10"], ["Abroad", "9.50", "2.75"]]),
    ("p", "The price before surcharge equals the base rate plus the rate per kilogram times the chargeable weight."),
    ("p", "A fuel surcharge of 12.5% is added to the price before surcharge."),
    ("p", "The volume discount is 1% per parcel and is capped at 20%."),
    ("p", "The final price is never below 4.50 and is rounded to 2 decimals."),
    ("h", 1, "4 Testing"),
    ("p", "Unit tests cover the dimensional weight and the minimum price."),
    ("p", "The tests are run before every release."),
    ("h", 1, "5 Contacts"),
    ("p", "Questions are answered by the pricing office."),
    ("image", "Figure A. Release calendar"),
]


def build_a_minimal():
    import pandas
    sample = "A_minimal"
    write_bytes(sample, "canon", "parcel_pricing_method.xml", A_METHODOLOGY)
    rates = pandas.DataFrame({"zone": ["Local", "National", "Abroad"], "base_rate": [3.20, 4.90, 9.50],
                              "rate_per_kg": [0.85, 1.10, 2.75]})
    files = dict(A_PACKAGE)
    files["data/zone_rates.rda"] = r_data({"zone_rates": rates})
    write_bytes(sample, "package", "parcelcost_1.2.0.tar.gz", tarball("parcelcost", files))
    write_bytes(sample, "doc", "parcelcost_documentation.docx", docx_file(A_DOCUMENTATION))


BUILDERS = {"A_minimal": build_a_minimal}

if __name__ == "__main__":
    for name in (sys.argv[1:] or list(BUILDERS)):
        BUILDERS[name]()
        print("built", name)
