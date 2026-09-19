"""fixture_package.py - a tarball laid out the way a real package sometimes is and the built-in
tests do not expect: R code under inst/ rather than R/, a table of values as a .csv in a folder
the data tests do not reach, a help page outside man/, and a member of no known kind at all.

Every one of these is content the reader loses quietly today: a file with no reader becomes two
thousand characters of running text and the rest of it reaches nothing.
"""
import io
import os
import sys
import tarfile
import time

HELPERS = '''round_up_quarter <- function(hours) {
  ceiling(hours * 4) / 4
}

shift_total <- function(hours, base_rate) {
  round_up_quarter(hours) * base_rate
}
'''

HELP_PAGE = '''\\name{round_up_quarter}
\\alias{round_up_quarter}
\\title{Round hours up to the nearest quarter}
\\arguments{
\\item{hours}{length of the shift in hours}
}
'''

RATES_CSV = "zone,rate_per_km\ninner,0.20\nouter,0.40\n"

MYSTERY = "Compiled with settings 7f3a. Do not edit by hand.\n" * 3

CALCULATIONS = '''night_premium <- function(base, starts_after_ten) {
  if (starts_after_ten) base * 0.25 else 0
}

distance_pay <- function(km, zone) {
  rates <- c(inner = 0.2, outer = 0.4)
  min(km * unname(rates[zone]), 40)
}

total_pay <- function(hours, km, zone, starts_after_ten) {
  base <- shift_total(hours, 9)
  base + distance_pay(km, zone) + night_premium(base, starts_after_ten)
}
'''

MEMBERS = {
    "DESCRIPTION": "Package: oddly\nTitle: An Oddly Laid Out Package\nVersion: 0.1.0\nLicense: MIT\nEncoding: UTF-8\n",
    "NAMESPACE": "export(shift_total)\n",
    "R/main.R": "#' Pay for a shift\n#' @param hours length of the shift\n#' @export\npay <- function(hours) hours * 9\n",
    "inst/extra/helpers.R": HELPERS,                 # R code where the tests do not look
    "inst/doc/round_up_quarter.Rd": HELP_PAGE,       # a help page outside man/
    "inst/rates/zone_rates.csv": RATES_CSV,          # a table of values the data tests do not reach
    "tools/build.notes": MYSTERY,                    # a member of no known kind
    "tools/calculations.R": CALCULATIONS,            # R code in a folder the tests do not reach at all
}


def tarball(members=None):
    """The fixture as tarball bytes, with fixed times so the bytes are the same every run."""
    members = members or MEMBERS
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz", format=tarfile.GNU_FORMAT) as archive:
        for path in sorted(members):
            data = members[path].encode("utf-8")
            info = tarfile.TarInfo("oddly/" + path)
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            archive.addfile(info, io.BytesIO(data))
    return raw.getvalue()


UNPLACED = ("inst/doc/round_up_quarter.Rd", "tools/build.notes", "tools/calculations.R")
